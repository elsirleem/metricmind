import logging

import httpx

from backend.ingestion.base import GitAdapter, clean_commit_message
from backend.ingestion.normaliser import (
    normalise_github_pipeline,
    normalise_github_mr,
    normalise_github_commit,
    normalise_github_release,
)

logger = logging.getLogger(__name__)

# Max individual PR detail calls per project (to stay well within GitHub rate limits).
# PRs beyond this cap use list data — changed_files will be None for those.
MAX_PR_DETAIL_CALLS = 50


class GitHubRepoNotFoundError(Exception):
    pass


class GitHubAdapter(GitAdapter):
    """
    GitHub implementation of GitAdapter.

    project_id format: "owner/repo"  (e.g. "facebook/react")

    Supports public GitHub (github.com) and GitHub Enterprise (self-hosted).
    GitHub Enterprise API lives at {host}/api/v3 instead of api.github.com.
    """

    def _headers(self) -> dict:
        h = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _api_base(self, repo_slug: str) -> str:
        """Return the repos/{owner}/{repo} API prefix for the configured host."""
        # Public GitHub: base_url is "https://github.com" → use api.github.com
        # GHE: base_url is "https://github.mycompany.com" → use {host}/api/v3
        if self.base_url in ("https://github.com", "http://github.com"):
            return f"https://api.github.com/repos/{repo_slug}"
        return f"{self.base_url}/api/v3/repos/{repo_slug}"

    async def fetch_all(self, profile_id: str, project_id: str, since: str) -> list[dict]:
        """project_id must be 'owner/repo' (e.g. 'vercel/next.js')."""
        api = self._api_base(project_id)
        headers = self._headers()
        events: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Confirm repo is accessible
            check = await client.get(api, headers=headers)
            if check.status_code == 404:
                raise GitHubRepoNotFoundError(project_id)
            if check.status_code == 401:
                raise PermissionError(f"GitHub authentication failed for {project_id} — check GITHUB_TOKEN")
            check.raise_for_status()

            # --- GitHub Actions workflow runs (pipeline equivalent) ---
            runs_resp = await client.get(
                f"{api}/actions/runs",
                params={"created": f">{since}", "per_page": 100},
                headers=headers,
            )
            if runs_resp.status_code == 200:
                for run in runs_resp.json().get("workflow_runs", []):
                    events.append(normalise_github_pipeline(run, profile_id, project_id))
            else:
                # GitHub Actions may not be enabled — non-fatal
                logger.warning(
                    "GitHub Actions runs unavailable for %s (HTTP %s) — pipeline metrics will be empty",
                    project_id,
                    runs_resp.status_code,
                )

            # --- Pull requests ---
            prs_resp = await client.get(
                f"{api}/pulls",
                params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 100},
                headers=headers,
            )
            prs_resp.raise_for_status()
            prs_list = prs_resp.json()

            # Fetch individual PR detail for the most recent N PRs to get changed_files.
            # PRs beyond the cap use the list-only data (changed_files will be None).
            detailed: list[dict] = []
            for pr in prs_list[:MAX_PR_DETAIL_CALLS]:
                try:
                    d = await client.get(f"{api}/pulls/{pr['number']}", headers=headers)
                    detailed.append(d.json() if d.status_code == 200 else pr)
                except Exception:
                    detailed.append(pr)

            for pr in prs_list[MAX_PR_DETAIL_CALLS:]:
                detailed.append(pr)

            for pr in detailed:
                events.append(normalise_github_mr(pr, profile_id, project_id))

            # --- Commits ---
            commits_resp = await client.get(
                f"{api}/commits",
                params={"since": since, "per_page": 100},
                headers=headers,
            )
            commits_resp.raise_for_status()
            for c in commits_resp.json():
                events.append(normalise_github_commit(c, profile_id, project_id))

            # --- Releases (= production deployment signal for tag-based teams) ---
            releases_resp = await client.get(
                f"{api}/releases",
                params={"per_page": 100},
                headers=headers,
            )
            if releases_resp.status_code == 200:
                for rel in releases_resp.json():
                    if rel.get("draft"):
                        continue   # skip draft releases
                    events.append(normalise_github_release(rel, profile_id, project_id))
            else:
                logger.info(
                    "GitHub Releases endpoint returned %s for %s — releases not ingested",
                    releases_resp.status_code, project_id,
                )

        return events

    async def explore(self, project_id: str, since: str | None = None) -> dict:
        """Fetch recent commits + PRs for LLM-based project exploration."""
        api = self._api_base(project_id)
        headers = self._headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                commit_params: dict = {"per_page": 100} if since else {"per_page": 30}
                if since:
                    commit_params["since"] = since
                resp = await client.get(
                    f"{api}/commits",
                    params=commit_params,
                    headers=headers,
                )
                if resp.status_code == 401:
                    raise PermissionError("GitHub authentication failed — check GITHUB_TOKEN")
                if resp.status_code == 404:
                    raise LookupError(f"GitHub repository not found — check owner/repo: {project_id}")
                resp.raise_for_status()
                commits_raw = resp.json()
            except (PermissionError, LookupError):
                raise
            except Exception as e:
                raise RuntimeError(f"GitHub request failed: {e}") from e

            commit_messages = [
                clean_commit_message(c.get("commit", {}).get("message") or "")
                for c in commits_raw
            ]

            try:
                resp = await client.get(
                    f"{api}/pulls",
                    params={"state": "all", "per_page": 20},
                    headers=headers,
                )
                resp.raise_for_status()
                prs_raw = resp.json()
            except Exception as e:
                logger.warning("GitHub PR fetch failed (non-fatal): %s", e)
                prs_raw = []

            mr_summaries = [
                f"{pr['title']} — {(pr.get('body') or '')[:150]}"
                for pr in prs_raw
            ]

        return {"commit_messages": commit_messages, "mr_summaries": mr_summaries}
