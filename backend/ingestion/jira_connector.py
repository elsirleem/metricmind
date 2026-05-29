import os
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from backend.ingestion.normaliser import normalise_jira_issue
from backend.schemas.profile import DataSourceConfig

logger = logging.getLogger(__name__)

JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")


def _normalise_base_url(raw: str) -> str:
    """Reduce a user-pasted Jira URL to its origin (scheme + host).

    Users sometimes paste a full board URL like
    ``https://x.atlassian.net/jira/software/c/projects/BBT/boards/1338`` into
    the Jira base URL field; that path then breaks API construction. We
    defensively strip everything past the netloc.
    """
    if not raw:
        return raw
    try:
        p = urlparse(raw.strip())
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return raw


class JiraProjectNotFoundError(Exception):
    pass


def _auth_header() -> dict:
    """
    Build request headers for Jira.
    If JIRA_EMAIL and JIRA_TOKEN are set, send Basic auth (Atlassian Cloud / private Jira).
    If not set, send no Authorization header so public Jira instances (e.g. Apache's
    issues.apache.org/jira) work without credentials.
    """
    headers: dict = {"Content-Type": "application/json"}
    if JIRA_EMAIL and JIRA_TOKEN:
        token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    return headers


async def fetch_jira_data(
    profile_id: str,
    config: DataSourceConfig,
    since_date: str,
    until_date: str,
) -> list[dict]:
    """
    Loop over all configured Jira project keys.

    since_date / until_date — ISO date strings ("YYYY-MM-DD") used in JQL.
    Skips missing projects with a warning.
    Raises RuntimeError if every configured project fails.
    """
    if not config.jira_project_keys:
        raise ValueError(
            "No Jira project keys configured — add at least one in the profile data source settings"
        )

    if not config.jira_base_url:
        raise ValueError("Jira base URL is required when Jira project keys are configured")

    all_events: list[dict] = []
    failed = 0

    for project_key in config.jira_project_keys:
        try:
            events = await _fetch_single_project(
                profile_id, project_key, config.jira_base_url, since_date, until_date
            )
            all_events.extend(events)
        except JiraProjectNotFoundError:
            logger.warning("Jira project %s not found — skipping", project_key)
            failed += 1
        except Exception as exc:
            logger.warning("Jira project %s failed (%s) — skipping", project_key, exc)
            failed += 1

    if failed == len(config.jira_project_keys):
        raise RuntimeError(
            "All configured data sources failed — check project IDs and credentials"
        )

    return all_events


async def _fetch_single_project(
    profile_id: str,
    project_key: str,
    base_url: str,
    since_date: str,
    until_date: str,
) -> list[dict]:
    headers = _auth_header()
    if not (JIRA_EMAIL and JIRA_TOKEN):
        logger.warning(
            "Jira request for project %s will be sent unauthenticated — "
            "set JIRA_EMAIL and JIRA_TOKEN in .env for private instances",
            project_key,
        )
    normalised_base = _normalise_base_url(base_url)
    # Atlassian retired /rest/api/2/search and /rest/api/3/search (returns 410
    # Gone). The replacement is the enhanced JQL search endpoint, which takes
    # the same JQL payload but uses cursor pagination instead of startAt/total.
    search_url = f"{normalised_base.rstrip('/')}/rest/api/3/search/jql"
    events: list[dict] = []

    # Fetch bugs and incidents
    incident_issues = await _jql_search(
        search_url,
        headers,
        jql=(
            f"project={project_key} AND issuetype in (Bug, Incident) "
            f'AND created >= "{since_date}" AND created <= "{until_date}"'
        ),
        project_key=project_key,
    )

    # Fetch all issues (for TWiP, velocity, etc.)
    all_issues = await _jql_search(
        search_url,
        headers,
        jql=(
            f"project={project_key} "
            f'AND created >= "{since_date}" AND created <= "{until_date}"'
        ),
        project_key=project_key,
    )

    # Deduplicate by key (all_issues is a superset of incident_issues)
    seen: set[str] = set()
    for issue in all_issues:
        key = issue["key"]
        if key not in seen:
            seen.add(key)
            events.append(normalise_jira_issue(issue, profile_id, project_key))

    return events


async def _jql_search(
    url: str,
    headers: dict,
    jql: str,
    project_key: str,
    max_results: int = 100,
) -> list[dict]:
    """POST to /search with JQL. Raises JiraProjectNotFoundError on 400/404."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers=headers,
            json={
                "jql": jql,
                "maxResults": max_results,
                "fields": [
                    "created",
                    "resolutiondate",
                    "status",
                    "issuetype",
                    "priority",
                    "story_points",
                    "customfield_10016",
                ],
            },
        )

    if response.status_code in (400, 404):
        # 400 can mean the project key is invalid
        raise JiraProjectNotFoundError(project_key)

    response.raise_for_status()

    # Jira may return HTML (a login redirect) with a 200 status when the
    # token is missing or expired. Detect that explicitly so the error
    # surfaces as "auth issue" rather than a confusing JSON parse failure.
    ctype = response.headers.get("content-type", "")
    if "application/json" not in ctype:
        snippet = response.text[:120].replace("\n", " ")
        raise RuntimeError(
            f"Jira returned non-JSON response (content-type={ctype!r}). "
            f"Most likely the token is invalid or missing (private Jira instances "
            f"redirect unauthenticated API requests to a login page). "
            f"Check JIRA_EMAIL / JIRA_TOKEN in .env. Response snippet: {snippet!r}"
        )
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        snippet = response.text[:120].replace("\n", " ")
        raise RuntimeError(
            f"Jira response was advertised as JSON but did not parse "
            f"(status={response.status_code}, error={e}). Snippet: {snippet!r}"
        ) from e
    return data.get("issues", [])
