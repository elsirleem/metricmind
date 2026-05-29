import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_CET = ZoneInfo("Europe/Berlin")  # handles CET (UTC+1) and CEST (UTC+2) automatically


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_after_hours(iso_timestamp: str) -> bool:
    """Return True if the commit falls outside normal working hours (CET/CEST).
    Working hours: 09:00–17:00 Monday–Friday (Europe/Berlin).
    Weekends (Saturday=5, Sunday=6) are always after-hours regardless of time.
    """
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        local = dt.astimezone(_CET)
        if local.weekday() >= 5:          # Saturday or Sunday
            return True
        return local.hour < 9 or local.hour >= 17
    except Exception:
        return False


# ---------------------------------------------------------------------------
# GitLab normalisers
# ---------------------------------------------------------------------------

def normalise_gitlab_pipeline(raw: dict, profile_id: str, project_id: str) -> dict:
    return {
        "profile_id": profile_id,
        "source": "gitlab",
        "entity_type": "pipeline",
        "entity_id": str(raw["id"]),
        "project_id": str(project_id),
        "timestamp": raw["created_at"],
        "attributes": json.dumps({
            "status": raw.get("status"),
            "ref": raw.get("ref"),
            "sha": raw.get("sha"),
        }),
        "ingested_at": _now_iso(),
    }


def normalise_gitlab_mr(raw: dict, profile_id: str, project_id: str) -> dict:
    author = raw.get("author") or {}
    # PR size: prefer the lines_changed value injected by the connector
    # (computed from the MR's /changes diff). If absent — for MRs beyond
    # the per-MR detail cap — fall back to None rather than the list
    # endpoint's changes_count, which is a file count, not lines.
    changes_count = raw.get("lines_changed")
    if isinstance(changes_count, (int, float)):
        changes_count = int(changes_count) if changes_count > 0 else None
    else:
        changes_count = None

    return {
        "profile_id": profile_id,
        "source": "gitlab",
        "entity_type": "mr",
        "entity_id": str(raw["iid"]),
        "project_id": str(project_id),
        "timestamp": raw["created_at"],
        "attributes": json.dumps({
            "merged_at": raw.get("merged_at"),
            "closed_at": raw.get("closed_at"),
            "state": raw.get("state"),
            "title": raw.get("title"),
            "changes_count": changes_count,
            "source_branch": raw.get("source_branch"),
            "target_branch": raw.get("target_branch"),
            "author_id": author.get("id"),
        }),
        "ingested_at": _now_iso(),
    }


def normalise_gitlab_release(raw: dict, profile_id: str, project_id: str) -> dict:
    """A GitLab release wraps a git tag. We record tag name + release date."""
    timestamp = raw.get("released_at") or raw.get("created_at") or ""
    return {
        "profile_id": profile_id,
        "source": "gitlab",
        "entity_type": "release",
        "entity_id": str(raw.get("tag_name") or raw.get("name") or ""),
        "project_id": str(project_id),
        "timestamp": timestamp,
        "attributes": json.dumps({
            "tag_name": raw.get("tag_name"),
            "name": raw.get("name"),
            "released_at": raw.get("released_at"),
            "created_at": raw.get("created_at"),
            "commit_sha": (raw.get("commit") or {}).get("id"),
        }),
        "ingested_at": _now_iso(),
    }


def normalise_gitlab_commit(raw: dict, profile_id: str, project_id: str) -> dict:
    timestamp = raw.get("created_at") or raw.get("committed_date", "")
    return {
        "profile_id": profile_id,
        "source": "gitlab",
        "entity_type": "commit",
        "entity_id": str(raw["id"]),  # SHA
        "project_id": str(project_id),
        "timestamp": timestamp,
        "attributes": json.dumps({
            "author_email": raw.get("author_email"),
            "author_name": raw.get("author_name"),
            "after_hours": _is_after_hours(timestamp),
        }),
        "ingested_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# GitHub normalisers
# ---------------------------------------------------------------------------

# Maps GitHub Actions conclusion → GitLab-equivalent status string
GITHUB_CONCLUSION_MAP: dict[str | None, str] = {
    "success": "success",
    "failure": "failed",
    "timed_out": "failed",
    "cancelled": "cancelled",
    "skipped": "success",
    "neutral": "success",
    "stale": "cancelled",
    "action_required": "pending",
    None: "running",   # workflow still in progress
}


def normalise_github_pipeline(raw: dict, profile_id: str, project_id: str) -> dict:
    conclusion = raw.get("conclusion")
    status = GITHUB_CONCLUSION_MAP.get(conclusion, "failed")
    timestamp = raw.get("created_at", "")
    return {
        "profile_id": profile_id,
        "source": "github",
        "entity_type": "pipeline",
        "entity_id": str(raw["id"]),
        "project_id": str(project_id),
        "timestamp": timestamp,
        "attributes": json.dumps({
            "status": status,
            "ref": raw.get("head_branch"),
            "sha": raw.get("head_sha"),
        }),
        "ingested_at": _now_iso(),
    }


def normalise_github_mr(raw: dict, profile_id: str, project_id: str) -> dict:
    # GitHub state: "open" | "closed"; merged when state=="closed" and merged_at is set
    state = raw.get("state", "")
    merged_at = raw.get("merged_at")
    if state == "closed" and merged_at:
        norm_state = "merged"
    elif state == "open":
        norm_state = "opened"
    else:
        norm_state = "closed"

    user = raw.get("user") or {}
    # PR size = lines changed (additions + deletions). These fields are only
    # populated by the per-PR detail endpoint, not the /pulls list endpoint,
    # so PRs beyond MAX_PR_DETAIL_CALLS will have changes_count=None. We
    # deliberately do NOT fall back to changed_files (file count) — file
    # count and line count are different units and conflating them under
    # one "lines" label was the source of an earlier measurement bug.
    additions = raw.get("additions")
    deletions = raw.get("deletions")
    if additions is not None or deletions is not None:
        total = (additions or 0) + (deletions or 0)
        changes_count = total if total > 0 else None
    else:
        changes_count = None

    return {
        "profile_id": profile_id,
        "source": "github",
        "entity_type": "mr",
        "entity_id": str(raw["number"]),
        "project_id": str(project_id),
        "timestamp": raw.get("created_at", ""),
        "attributes": json.dumps({
            "merged_at": merged_at,
            "closed_at": raw.get("closed_at"),
            "state": norm_state,
            "title": raw.get("title"),
            "changes_count": changes_count,
            "source_branch": (raw.get("head") or {}).get("ref"),
            "target_branch": (raw.get("base") or {}).get("ref"),
            "author_id": user.get("id"),
        }),
        "ingested_at": _now_iso(),
    }


def normalise_github_release(raw: dict, profile_id: str, project_id: str) -> dict:
    """A GitHub release wraps a git tag. We record tag name + published_at date."""
    timestamp = raw.get("published_at") or raw.get("created_at") or ""
    return {
        "profile_id": profile_id,
        "source": "github",
        "entity_type": "release",
        "entity_id": str(raw.get("tag_name") or raw.get("name") or ""),
        "project_id": str(project_id),
        "timestamp": timestamp,
        "attributes": json.dumps({
            "tag_name": raw.get("tag_name"),
            "name": raw.get("name"),
            "published_at": raw.get("published_at"),
            "created_at": raw.get("created_at"),
            "target_commitish": raw.get("target_commitish"),
            "draft": raw.get("draft"),
            "prerelease": raw.get("prerelease"),
        }),
        "ingested_at": _now_iso(),
    }


def normalise_github_commit(raw: dict, profile_id: str, project_id: str) -> dict:
    commit_data = raw.get("commit", {})
    author = commit_data.get("author") or {}
    # GitHub commit author date is the authored time; committer date is push time
    timestamp = author.get("date") or (commit_data.get("committer") or {}).get("date", "")
    return {
        "profile_id": profile_id,
        "source": "github",
        "entity_type": "commit",
        "entity_id": str(raw["sha"]),
        "project_id": str(project_id),
        "timestamp": timestamp,
        "attributes": json.dumps({
            "author_email": author.get("email"),
            "author_name": author.get("name"),
            "after_hours": _is_after_hours(timestamp),
        }),
        "ingested_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Jira normaliser
# ---------------------------------------------------------------------------

def normalise_jira_issue(raw: dict, profile_id: str, project_key: str) -> dict:
    fields = raw.get("fields", {})
    status_name = (fields.get("status") or {}).get("name", "")
    issue_type = (fields.get("issuetype") or {}).get("name", "")
    priority_obj = fields.get("priority") or {}
    resolved_at = fields.get("resolutiondate")

    story_points = fields.get("story_points") or fields.get("customfield_10016")

    return {
        "profile_id": profile_id,
        "source": "jira",
        "entity_type": "issue",
        "entity_id": raw["key"],
        "project_id": project_key,
        "timestamp": fields.get("created", ""),
        "attributes": json.dumps({
            "resolved_at": resolved_at,
            "status": status_name,
            "issue_type": issue_type,
            "priority": priority_obj.get("name"),
            "story_points": story_points,
            "in_progress": status_name in ("In Progress", "In Review", "In Development"),
            "is_incident": issue_type in ("Bug", "Incident", "Service Request"),
            "is_resolved": resolved_at is not None,
        }),
        "ingested_at": _now_iso(),
    }
