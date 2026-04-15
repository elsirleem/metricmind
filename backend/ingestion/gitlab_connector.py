import logging

import httpx

from backend.ingestion.base import GitAdapter
from backend.ingestion.normaliser import (
    normalise_gitlab_pipeline,
    normalise_gitlab_mr,
    normalise_gitlab_commit,
)

logger = logging.getLogger(__name__)


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

        return events

    async def explore(self, project_id: str) -> dict:
        """Fetch recent commits + MRs for LLM-based project exploration."""
        headers = self._headers()
        api_base = self._api(project_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    f"{api_base}/repository/commits",
                    params={"per_page": 30},
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
                c.get("title") or (c.get("message", "")[:100])
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
