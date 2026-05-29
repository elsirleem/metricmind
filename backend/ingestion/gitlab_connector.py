import logging

import httpx

from backend.ingestion.base import GitAdapter, clean_commit_message
from backend.ingestion.normaliser import (
    normalise_gitlab_pipeline,
    normalise_gitlab_mr,
    normalise_gitlab_commit,
    normalise_gitlab_release,
)

logger = logging.getLogger(__name__)

# Cap per-MR detail calls to avoid blowing through rate limits on busy projects.
# MRs beyond the cap will have lines_changed=None (excluded from PRSi average).
MAX_MR_DETAIL_CALLS = 50


class GitLabProjectNotFoundError(Exception):
    pass


class GitLabAdapter(GitAdapter):
    """GitLab implementation of GitAdapter."""

    def _headers(self) -> dict:
        return {"PRIVATE-TOKEN": self.token} if self.token else {}

    def _api(self, project_id: str) -> str:
        return f"{self.base_url}/api/v4/projects/{project_id}"

    async def fetch_all(self, profile_id: str, project_id: str, since: str) -> list[dict]:
        headers = self._headers()
        api_base = self._api(project_id)
        events: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # --- pipelines ---
            pipelines = await self._paginate(
                client,
                f"{api_base}/pipelines",
                {"updated_after": since, "per_page": 100},
                headers,
                project_id,
            )
            for p in pipelines:
                events.append(normalise_gitlab_pipeline(p, profile_id, project_id))

            # --- merge requests ---
            mrs = await self._paginate(
                client,
                f"{api_base}/merge_requests",
                {"state": "all", "updated_after": since, "per_page": 100},
                headers,
                project_id,
            )
            # Enrich the most recent MAX_MR_DETAIL_CALLS MRs with a real
            # line-count by fetching their /changes diff. The list endpoint
            # only gives us a file count; PRSi must be in lines (Cohen).
            for mr in mrs[:MAX_MR_DETAIL_CALLS]:
                mr["lines_changed"] = await self._fetch_mr_lines_changed(
                    client, api_base, mr.get("iid"), headers,
                )
            for mr in mrs:
                events.append(normalise_gitlab_mr(mr, profile_id, project_id))

            # --- commits ---
            commits = await self._paginate(
                client,
                f"{api_base}/repository/commits",
                {"since": since, "per_page": 100},
                headers,
                project_id,
            )
            for c in commits:
                events.append(normalise_gitlab_commit(c, profile_id, project_id))

            # --- releases (production deployment signal for tag-based teams) ---
            try:
                releases = await self._paginate(
                    client,
                    f"{api_base}/releases",
                    {"per_page": 100},
                    headers,
                    project_id,
                )
                for rel in releases:
                    events.append(normalise_gitlab_release(rel, profile_id, project_id))
            except GitLabProjectNotFoundError:
                # Releases endpoint may be unavailable on older GitLab instances — non-fatal
                logger.info("GitLab releases endpoint unavailable for %s — releases not ingested", project_id)

        return events

    async def explore(self, project_id: str, since: str | None = None) -> dict:
        """Fetch recent commits + MRs for LLM-based project exploration."""
        headers = self._headers()
        api_base = self._api(project_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                commit_params: dict = {"per_page": 100} if since else {"per_page": 30}
                if since:
                    commit_params["since"] = since
                resp = await client.get(
                    f"{api_base}/repository/commits",
                    params=commit_params,
                    headers=headers,
                )
                if resp.status_code == 401:
                    raise PermissionError("GitLab authentication failed — check GITLAB_TOKEN")
                if resp.status_code == 404:
                    raise LookupError(f"GitLab project not found — check project ID: {project_id}")
                if resp.status_code >= 500:
                    raise RuntimeError("GitLab server error — try a different project")
                resp.raise_for_status()
                commits_raw = resp.json()
            except (PermissionError, LookupError, RuntimeError):
                raise
            except Exception as e:
                raise RuntimeError(f"GitLab request failed: {e}") from e

            commit_messages = [
                clean_commit_message(c.get("title") or c.get("message", ""))
                for c in commits_raw
            ]

            try:
                resp = await client.get(
                    f"{api_base}/merge_requests",
                    params={"state": "all", "per_page": 20},
                    headers=headers,
                )
                resp.raise_for_status()
                mrs_raw = resp.json()
            except Exception as e:
                logger.warning("Failed to fetch MRs for GitLab project %s: %s", project_id, e)
                mrs_raw = []

            mr_summaries = [
                f"{mr['title']} — {(mr.get('description') or '')[:150]}"
                for mr in mrs_raw
            ]

        return {"commit_messages": commit_messages, "mr_summaries": mr_summaries}

    async def _paginate(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict,
        headers: dict,
        project_id: str,
    ) -> list[dict]:
        """Fetch one page (per_page=100). Raises GitLabProjectNotFoundError on 404."""
        response = await client.get(url, params=params, headers=headers)
        if response.status_code == 404:
            raise GitLabProjectNotFoundError(project_id)
        response.raise_for_status()
        return response.json()

    async def _fetch_mr_lines_changed(
        self,
        client: httpx.AsyncClient,
        api_base: str,
        iid,
        headers: dict,
    ) -> int | None:
        """Fetch a single MR's diff and count added + deleted lines.

        Returns None when the MR is unavailable or has no diff. Lines starting
        with '+' (not '+++') are additions; lines starting with '-' (not '---')
        are deletions. Diff headers are excluded.
        """
        if iid is None:
            return None
        try:
            resp = await client.get(
                f"{api_base}/merge_requests/{iid}/changes",
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception as exc:
            logger.debug("GitLab MR %s line-count fetch failed: %s", iid, exc)
            return None

        additions = 0
        deletions = 0
        for ch in data.get("changes", []):
            for line in (ch.get("diff") or "").splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
        total = additions + deletions
        return total if total > 0 else None
