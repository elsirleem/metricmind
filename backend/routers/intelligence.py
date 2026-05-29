import base64
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import Explanation, Profile, ReasoningReport, Snapshot
from backend.metrics.catalog import STANDARD_METRICS
from backend.pipeline.call0_context import run_call0
from backend.pipeline.call2_reason import run_call2
from backend.pipeline.call3_explain import run_call3
from backend.pipeline.snapshot import build_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")


def parse_jira_url(url: str) -> tuple[str | None, str | None]:
    """Extract (base_url, project_key) from a user-pasted Jira URL.

    Supports common Atlassian URL shapes:
      - https://x.atlassian.net/jira/software/c/projects/KEY/...
      - https://x.atlassian.net/jira/software/projects/KEY/...
      - https://x.atlassian.net/projects/KEY/board
      - https://x.atlassian.net/browse/KEY-1234
      - https://x.atlassian.net/secure/RapidBoard.jspa?projectKey=KEY

    Returns (None, None) when the input is not a usable Jira URL.
    """
    if not url:
        return None, None
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None, None
    if not parsed.scheme or not parsed.netloc:
        return None, None

    base = f"{parsed.scheme}://{parsed.netloc}"

    # 1. /projects/{KEY}/...
    m = re.search(r"/projects/([A-Z][A-Z0-9_]+)(?:/|$)", parsed.path)
    if m:
        return base, m.group(1)

    # 2. /browse/{KEY}-1234
    m = re.search(r"/browse/([A-Z][A-Z0-9_]+)-\d+", parsed.path)
    if m:
        return base, m.group(1)

    # 3. ?projectKey=KEY  (RapidBoard, legacy)
    qs = parse_qs(parsed.query)
    pk = qs.get("projectKey") or qs.get("project")
    if pk and pk[0]:
        return base, pk[0]

    # No project key found — return base only so the caller can warn the user.
    return base, None


class ExploreRequest(BaseModel):
    # Platform is inferred from base URL when omitted (github.com → github, else gitlab).
    platform: Optional[str] = None

    # GitLab fields (kept for backward compatibility)
    gitlab_base_url: Optional[str] = None
    gitlab_project_id: Optional[str] = None

    # GitHub fields — repo slug in "owner/repo" format (e.g. "vercel/next.js")
    github_base_url: Optional[str] = None
    github_repo_slug: Optional[str] = None

    # Jira (shared, optional)
    jira_base_url: Optional[str] = None
    jira_project_key: Optional[str] = None

    # Explore window — how far back to fetch commits/PRs for Call 0.
    # explore_days: preset (30 | 60 | 90).
    # explore_since: custom ISO date string "YYYY-MM-DD" (takes precedence).
    # When both absent, fetches latest 30 commits (legacy behaviour).
    explore_days: Optional[int] = None
    explore_since: Optional[str] = None


@router.post("/explore")
async def explore_project(body: ExploreRequest):
    """
    Call 0 — stateless project intelligence.
    Supports GitLab and GitHub via the adapter pattern.
    Fetches recent commits and MRs/PRs, passes them to the LLM,
    and returns North Star metric recommendations.
    Nothing is saved to the database.
    """
    from backend.ingestion.factory import get_git_adapter

    # Determine platform — explicit field wins, then infer from base URL
    platform = body.platform
    if not platform:
        check_url = body.gitlab_base_url or body.github_base_url or ""
        platform = "github" if "github.com" in check_url else "gitlab"

    if platform == "github":
        project_id = body.github_repo_slug or ""
        base_url = body.github_base_url or "https://github.com"
    else:
        project_id = body.gitlab_project_id or ""
        base_url = body.gitlab_base_url or "https://gitlab.com"

    if not project_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "No project ID provided — pass gitlab_project_id or github_repo_slug"},
        )

    # Resolve explore window → ISO datetime string or None
    explore_since: str | None = None
    if body.explore_since:
        explore_since = body.explore_since + "T00:00:00Z"
    elif body.explore_days:
        explore_since = (
            datetime.now(timezone.utc) - timedelta(days=body.explore_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch git data via adapter
    adapter = get_git_adapter(platform, base_url)
    try:
        git_data = await adapter.explore(project_id, since=explore_since)
    except PermissionError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except LookupError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": f"Project exploration failed: {str(e)}"})

    commit_messages = git_data["commit_messages"]
    mr_summaries = git_data["mr_summaries"]

    # Parse the user-pasted Jira URL into (base, project_key).
    # The frontend sends the whole URL as jira_base_url; we extract the project
    # key from it here so the user doesn't need to know about Jira API shapes.
    jira_base, jira_key = parse_jira_url(body.jira_base_url or "")
    if jira_base and not jira_key:
        # User supplied a Jira URL but we couldn't pull a project key from it.
        # Surface this so the LLM doesn't silently flag "no Jira" as a concern
        # when the real problem is a URL the parser didn't recognise.
        logger.warning(
            "Jira URL provided but project key could not be extracted: %s. "
            "Expected /projects/KEY/, /browse/KEY-123, or ?projectKey=KEY.",
            body.jira_base_url,
        )
    # Fall back to body.jira_project_key when the URL didn't carry one
    # (e.g. user pastes just the Atlassian host and supplies the key separately).
    if not jira_key:
        jira_key = body.jira_project_key

    # Fetch Jira tickets (optional — failure is non-fatal)
    issue_summaries: list[str] = []
    if jira_base and jira_key:
        if not (JIRA_EMAIL and JIRA_TOKEN):
            logger.warning(
                "Jira URL provided (%s, project=%s) but JIRA_EMAIL / JIRA_TOKEN "
                "are not configured — request will be sent unauthenticated and "
                "will likely fail for private instances.",
                jira_base, jira_key,
            )
        try:
            # Auth is optional — public Jira instances (e.g. Apache) work without credentials
            jira_headers: dict = {"Content-Type": "application/json"}
            if JIRA_EMAIL and JIRA_TOKEN:
                jira_auth = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()
                jira_headers["Authorization"] = f"Basic {jira_auth}"

            async with httpx.AsyncClient(timeout=30) as client:
                # Atlassian retired /rest/api/2/search and /rest/api/3/search
                # (returns 410 Gone). The replacement is the enhanced JQL
                # search endpoint, accepting the same JQL payload.
                jira_resp = await client.post(
                    f"{jira_base.rstrip('/')}/rest/api/3/search/jql",
                    headers=jira_headers,
                    json={
                        "jql": f"project={jira_key} ORDER BY created DESC",
                        "maxResults": 20,
                        "fields": ["summary"],
                    },
                )
                jira_resp.raise_for_status()
                issues = jira_resp.json().get("issues", [])
                issue_summaries = [i["fields"]["summary"] for i in issues]
                logger.info(
                    "Jira: fetched %d issues from %s (project=%s) for Call 0",
                    len(issue_summaries), jira_base, jira_key,
                )
        except Exception as e:
            logger.warning("Jira fetch failed (non-fatal): %s", e)

    # Run Call 0 LLM
    try:
        result = await run_call0(
            commit_messages=commit_messages,
            mr_summaries=mr_summaries,
            issue_summaries=issue_summaries,
            catalog=STANDARD_METRICS,
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail={"error": "LLM response invalid", "raw": str(e)})

    # Return platform-specific identifiers for frontend pre-fill
    result["platform"] = platform
    if platform == "github":
        result["github_repo_slug"] = project_id
        result["github_base_url"] = base_url
        result["gitlab_project_id"] = ""
        result["gitlab_base_url"] = ""
    else:
        result["gitlab_project_id"] = project_id
        result["gitlab_base_url"] = base_url
        result["github_repo_slug"] = ""
        result["github_base_url"] = ""

    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _profile_to_dict(profile: Profile) -> dict:
    return {
        "id": profile.id,
        "team_name": profile.team_name,
        "team_type": profile.team_type,
        "stakeholder_role": profile.stakeholder_role,
        "primary_goal": profile.primary_goal,
        "secondary_goal": profile.secondary_goal,
        "business_criticality": profile.business_criticality,
        "decision_type": profile.decision_type,
        "time_horizon": profile.time_horizon,
        "data_sources": json.loads(profile.data_sources),
        "sustainability_focus": json.loads(profile.sustainability_focus),
        "declared_kpis": json.loads(profile.declared_kpis),
        "confirmed": bool(profile.confirmed),
    }


@router.post("/reason/{profile_id}")
async def run_reasoning(
    profile_id: str,
    period_days: int = Query(default=14),
    db: Session = Depends(get_db),
):
    """Build snapshot → run Call 2 → save and return ReasoningReport."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    if not profile.confirmed:
        raise HTTPException(
            status_code=400,
            detail={"error": "Profile must be confirmed before running analysis"},
        )

    # Build and save snapshot
    try:
        snapshot = build_snapshot(profile_id, period_days, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    snapshot_dict = snapshot.model_dump()
    snap_row = Snapshot(
        profile_id=profile_id,
        snapshot_json=json.dumps(snapshot_dict),
        created_at=_now_iso(),
    )
    db.add(snap_row)
    db.flush()  # get snap_row.id before commit

    # Run Call 2
    profile_dict = _profile_to_dict(profile)
    try:
        report = await run_call2(profile_dict, snapshot_dict)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail={"error": "LLM response invalid", "raw": str(e)})

    # Save reasoning report
    report_row = ReasoningReport(
        profile_id=profile_id,
        snapshot_id=snap_row.id,
        report_json=json.dumps(report),
        overall_health=report.get("overall_health", "amber"),
        created_at=_now_iso(),
    )
    db.add(report_row)
    db.commit()

    return report


@router.post("/explain/{profile_id}")
async def run_explanation(profile_id: str, db: Session = Depends(get_db)):
    """Run Call 3 using the latest reasoning report → save and return ExplanationOutput."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    report_row = (
        db.query(ReasoningReport)
        .filter(ReasoningReport.profile_id == profile_id)
        .order_by(ReasoningReport.created_at.desc())
        .first()
    )
    if not report_row:
        raise HTTPException(
            status_code=404,
            detail={"error": "No reasoning report found — run /reason first"},
        )

    report = json.loads(report_row.report_json)
    declared_kpis = json.loads(profile.declared_kpis)

    try:
        explanation = await run_call3(profile.stakeholder_role, report, declared_kpis)
    except ValueError as e:
        raise HTTPException(status_code=502, detail={"error": "LLM response invalid", "raw": str(e)})

    exp_row = Explanation(
        profile_id=profile_id,
        reasoning_report_id=report_row.id,
        stakeholder_role=profile.stakeholder_role,
        explanation_json=json.dumps(explanation),
        created_at=_now_iso(),
    )
    db.add(exp_row)
    db.commit()

    return explanation


@router.get("/{profile_id}/latest")
def get_latest_explanation(profile_id: str, db: Session = Depends(get_db)):
    """Fetch the latest saved explanation for a profile."""
    row = (
        db.query(Explanation)
        .filter(Explanation.profile_id == profile_id)
        .order_by(Explanation.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"error": "No explanation found — run /explain first"},
        )
    return json.loads(row.explanation_json)


@router.get("/{profile_id}/latest-report")
def get_latest_reasoning_report(profile_id: str, db: Session = Depends(get_db)):
    """Fetch the latest saved reasoning report for a profile.

    Used by the Intelligence page on mount so that the conflicts panel and
    other report-derived UI elements survive a profile close / re-open.
    """
    row = (
        db.query(ReasoningReport)
        .filter(ReasoningReport.profile_id == profile_id)
        .order_by(ReasoningReport.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"error": "No reasoning report found — run /reason first"},
        )
    return json.loads(row.report_json)
