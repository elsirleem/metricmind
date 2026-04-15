import os
import base64
import logging
from datetime import datetime, timedelta, timezone

import httpx

from backend.ingestion.normaliser import normalise_jira_issue
from backend.schemas.profile import DataSourceConfig

logger = logging.getLogger(__name__)

JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")


class JiraProjectNotFoundError(Exception):
    pass


def _auth_header() -> dict:
    """Basic auth header encoded from JIRA_EMAIL:JIRA_TOKEN."""
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


async def fetch_jira_data(
    profile_id: str,
    period_days: int,
    config: DataSourceConfig,
) -> list[dict]:
    """
    Loop over all configured Jira project keys.
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
                profile_id, period_days, project_key, config.jira_base_url
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
    period_days: int,
    project_key: str,
    base_url: str,
) -> list[dict]:
    headers = _auth_header()
    search_url = f"{base_url.rstrip('/')}/rest/api/2/search"
    events: list[dict] = []

    # Fetch bugs and incidents
    incident_issues = await _jql_search(
        search_url,
        headers,
        jql=f"project={project_key} AND issuetype in (Bug, Incident) AND created >= -{period_days}d",
        project_key=project_key,
    )

    # Fetch all issues (for TWiP, velocity, etc.)
    all_issues = await _jql_search(
        search_url,
        headers,
        jql=f"project={project_key} AND created >= -{period_days}d",
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
    data = response.json()
    return data.get("issues", [])
