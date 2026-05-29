"""
Metric computation service.

All individual metric functions now receive explicit date ranges:
  compute_X(events, c_start, c_end, p_start, p_end) -> dict

compute_all() resolves a TimeWindow into date ranges and runs all functions.
Each function returns {"current": float, "previous": float, "unit": str}.

Current period  = [c_start, c_end)
Previous period = [p_start, p_end)
"""

import fnmatch
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Default fallback tag pattern when a profile doesn't override it.
DEFAULT_TAG_PATTERN = "v*"

# Re-used regex for detecting revert PRs (used by the merged-PR CFR fallback).
_REVERT_TITLE = re.compile(r'^\s*Revert\s+["\'`]', re.IGNORECASE)

# Hotfix window: a release within this many hours of the previous release
# is treated as a hotfix indicating the previous release shipped broken.
HOTFIX_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_dt(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _in_period(iso: str, start: datetime, end: datetime) -> bool:
    dt = _parse_dt(iso)
    if dt is None:
        return False
    return start <= dt < end


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _mean_or_none(values: list[float]) -> float | None:
    """Like _mean but returns None when the list is empty.
    Used for metrics where 0 is indistinguishable from 'no data'
    (e.g. MTTR, PRCT, LTfC — a 0-hour average is meaningless without events).
    """
    return sum(values) / len(values) if values else None


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

def _pipelines(events: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [
        e for e in events
        if e["entity_type"] == "pipeline" and _in_period(e["timestamp"], start, end)
    ]


def _mrs(events: list[dict]) -> list[dict]:
    return [e for e in events if e["entity_type"] == "mr"]


def _commits(events: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [
        e for e in events
        if e["entity_type"] == "commit" and _in_period(e["timestamp"], start, end)
    ]


def _issues(events: list[dict]) -> list[dict]:
    return [e for e in events if e["entity_type"] == "issue"]


def _merged_mrs_in(mrs: list[dict], start: datetime, end: datetime) -> list[dict]:
    result = []
    for m in mrs:
        merged_at = m["attributes"].get("merged_at")
        if m["attributes"].get("state") == "merged" and merged_at:
            if _in_period(merged_at, start, end):
                result.append(m)
    return result


# ---------------------------------------------------------------------------
# Release / deployment helpers
# ---------------------------------------------------------------------------

def _releases(events: list[dict]) -> list[dict]:
    return [e for e in events if e["entity_type"] == "release"]


def _matches_pattern(tag: str | None, pattern: str) -> bool:
    if not tag:
        return False
    return fnmatch.fnmatchcase(tag, pattern)


def _releases_in_period(
    events: list[dict], start: datetime, end: datetime, pattern: str,
) -> list[dict]:
    out = []
    for r in _releases(events):
        if not _in_period(r["timestamp"], start, end):
            continue
        tag = r["attributes"].get("tag_name") or r["entity_id"]
        if _matches_pattern(tag, pattern):
            out.append(r)
    return out


def _is_hotfix_of(prev_tag: str | None, current_tag: str | None) -> bool:
    """A release is a hotfix of the previous one when they share the same
    major.minor prefix but the current bumps only the patch component.
    e.g. v0.18.0 → v0.18.1 (hotfix); v0.18.5 → v0.19.0 (not a hotfix).
    """
    if not prev_tag or not current_tag:
        return False
    semver = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
    a, b = semver.search(prev_tag), semver.search(current_tag)
    if not a or not b:
        return False
    return a.group(1) == b.group(1) and a.group(2) == b.group(2) and a.group(3) != b.group(3)


def _count_hotfix_releases(releases: list[dict]) -> int:
    """Count releases that are hotfixes of the immediately preceding release
    AND were published within HOTFIX_WINDOW_HOURS of it."""
    if len(releases) < 2:
        return 0
    sorted_rel = sorted(releases, key=lambda r: r["timestamp"])
    hotfixes = 0
    for prev, curr in zip(sorted_rel, sorted_rel[1:]):
        prev_tag = prev["attributes"].get("tag_name") or prev["entity_id"]
        curr_tag = curr["attributes"].get("tag_name") or curr["entity_id"]
        if not _is_hotfix_of(prev_tag, curr_tag):
            continue
        prev_dt, curr_dt = _parse_dt(prev["timestamp"]), _parse_dt(curr["timestamp"])
        if not prev_dt or not curr_dt:
            continue
        if (curr_dt - prev_dt) <= timedelta(hours=HOTFIX_WINDOW_HOURS):
            hotfixes += 1
    return hotfixes


def _has_any_releases(events: list[dict], pattern: str) -> bool:
    """True if at least one matching release exists in the entire event set
    (ignoring period). Used to decide whether to use the release-based or
    merged-PR fallback signal."""
    for r in _releases(events):
        tag = r["attributes"].get("tag_name") or r["entity_id"]
        if _matches_pattern(tag, pattern):
            return True
    return False


def _merged_to_main_in_period(mrs: list[dict], start: datetime, end: datetime) -> list[dict]:
    merged = _merged_mrs_in(mrs, start, end)
    return [m for m in merged if m["attributes"].get("target_branch") in ("main", "master")]


def _is_revert_title(title: str | None) -> bool:
    return bool(title and _REVERT_TITLE.match(title))


# ---------------------------------------------------------------------------
# Individual metric functions
# ---------------------------------------------------------------------------

def compute_cfr(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
    release_tag_pattern: str = DEFAULT_TAG_PATTERN,
) -> dict:
    """Change Failure Rate (%).

    Primary signal: hotfix release detection.
      CFR = (releases that are patch-level bumps of the prior release within
             HOTFIX_WINDOW_HOURS) / (total releases in the period) * 100

    Fallback (no releases ever found in this repo): count revert PRs.
      CFR = (merged PRs to main with title starting with "Revert ...")
            / (total merged PRs to main in the period) * 100
    """
    if _has_any_releases(events, release_tag_pattern):
        def _cfr_releases(rels: list[dict]) -> float:
            if not rels:
                return 0.0
            hotfixes = _count_hotfix_releases(rels)
            return (hotfixes / len(rels)) * 100

        return {
            "current": _cfr_releases(_releases_in_period(events, c_start, c_end, release_tag_pattern)),
            "previous": _cfr_releases(_releases_in_period(events, p_start, p_end, release_tag_pattern)),
            "unit": "%",
        }

    # Fallback: revert PR detection on merged PRs to main
    mrs = _mrs(events)

    def _cfr_merges(period_start: datetime, period_end: datetime) -> float:
        merged = _merged_to_main_in_period(mrs, period_start, period_end)
        if not merged:
            return 0.0
        reverts = sum(1 for m in merged if _is_revert_title(m["attributes"].get("title")))
        return (reverts / len(merged)) * 100

    return {
        "current": _cfr_merges(c_start, c_end),
        "previous": _cfr_merges(p_start, p_end),
        "unit": "%",
    }


def compute_df(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
    release_tag_pattern: str = DEFAULT_TAG_PATTERN,
) -> dict:
    """Deployment Frequency.

    Primary signal: count of releases (tags matching release_tag_pattern) in
    the period — each release = one production-bound deployment.

    Fallback (no releases ever found in this repo): count of PRs merged into
    main/master in the period — for teams using continuous deployment from main.
    """
    if _has_any_releases(events, release_tag_pattern):
        return {
            "current": float(len(_releases_in_period(events, c_start, c_end, release_tag_pattern))),
            "previous": float(len(_releases_in_period(events, p_start, p_end, release_tag_pattern))),
            "unit": "deployments",
        }

    mrs = _mrs(events)
    return {
        "current": float(len(_merged_to_main_in_period(mrs, c_start, c_end))),
        "previous": float(len(_merged_to_main_in_period(mrs, p_start, p_end))),
        "unit": "deployments",
    }


def compute_mttr(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Mean Time to Recover = avg hours from incident open to resolved.
    Returns None when no incidents are found — 0 would be misleading.
    """
    def _mttr(start: datetime, end: datetime) -> float | None:
        resolved = [
            e for e in _issues(events)
            if e["attributes"].get("is_incident")
            and e["attributes"].get("resolved_at")
            and _in_period(e["attributes"]["resolved_at"], start, end)
        ]
        deltas = []
        for issue in resolved:
            created_dt = _parse_dt(issue["timestamp"])
            resolved_dt = _parse_dt(issue["attributes"]["resolved_at"])
            if created_dt and resolved_dt:
                deltas.append((resolved_dt - created_dt).total_seconds() / 3600)
        return _mean_or_none(deltas)

    return {
        "current": _mttr(c_start, c_end),
        "previous": _mttr(p_start, p_end),
        "unit": "hours",
    }


def compute_ltfc(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
    release_tag_pattern: str = DEFAULT_TAG_PATTERN,
) -> dict:
    """Lead Time for Changes — DORA's definition: the time it takes a commit
    to get into production. One of the four DORA key metrics.

    With the data we ingest (PRs/MRs and release tags) the closest faithful
    implementation is: for each PR merged in the period, take the gap
    between PR open time (proxy for "code committed") and the first release
    tag at or after merge time (proxy for "code running in production").
    The mean of those gaps is the period's LTfC.

    If the repo has no release tags matching the configured pattern, we
    cannot measure when changes reach production — so we return None
    rather than falling back to a PR-merge-time formula. Returning None
    causes the metric to be omitted from the snapshot (the report UI hides
    or annotates it accordingly), which is more honest than reporting a
    PRCT-equivalent number under the LTfC label.

    Also returns None when no merged MRs exist in the period.
    """
    if not _has_any_releases(events, release_tag_pattern):
        return {"current": None, "previous": None, "unit": "hours"}

    # Pre-collect release timestamps (ascending) once.
    release_dts: list[datetime] = []
    for r in _releases(events):
        tag = r["attributes"].get("tag_name") or r["entity_id"]
        if not _matches_pattern(tag, release_tag_pattern):
            continue
        dt = _parse_dt(r["timestamp"])
        if dt:
            release_dts.append(dt)
    release_dts.sort()

    def _next_release_after(merged_dt: datetime) -> datetime | None:
        # Linear scan is fine — release counts are small.
        for r_dt in release_dts:
            if r_dt >= merged_dt:
                return r_dt
        return None

    def _ltfc(start: datetime, end: datetime) -> float | None:
        deltas = []
        for m in _merged_mrs_in(_mrs(events), start, end):
            created_dt = _parse_dt(m["timestamp"])
            merged_dt = _parse_dt(m["attributes"]["merged_at"])
            if not (created_dt and merged_dt):
                continue
            shipped_dt = _next_release_after(merged_dt)
            if shipped_dt is None:
                # PR merged but no release has shipped it yet — skip.
                continue
            deltas.append((shipped_dt - created_dt).total_seconds() / 3600)
        return _mean_or_none(deltas)

    return {
        "current": _ltfc(c_start, c_end),
        "previous": _ltfc(p_start, p_end),
        "unit": "hours",
    }


def compute_prct(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Pull Request Cycle Time = avg hours from MR created to merged.
    Returns None when no merged MRs exist in the period.
    """
    def _prct(start: datetime, end: datetime) -> float | None:
        deltas = []
        for m in _merged_mrs_in(_mrs(events), start, end):
            created_dt = _parse_dt(m["timestamp"])
            merged_dt = _parse_dt(m["attributes"]["merged_at"])
            if created_dt and merged_dt:
                deltas.append((merged_dt - created_dt).total_seconds() / 3600)
        return _mean_or_none(deltas)

    return {
        "current": _prct(c_start, c_end),
        "previous": _prct(p_start, p_end),
        "unit": "hours",
    }


def compute_prsi(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Pull Request Size = avg lines changed per merged MR (changes_count proxy).
    Returns None when no merged MRs with size data exist.
    """
    def _prsi(start: datetime, end: datetime) -> float | None:
        sizes = [
            m["attributes"]["changes_count"]
            for m in _merged_mrs_in(_mrs(events), start, end)
            if m["attributes"].get("changes_count") is not None
        ]
        return _mean_or_none([float(s) for s in sizes])

    return {
        "current": _prsi(c_start, c_end),
        "previous": _prsi(p_start, p_end),
        "unit": "lines",
    }


def compute_twip(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Team Work in Progress = count of in-progress issues at reference time."""
    def _twip(reference: datetime) -> float:
        count = 0
        for issue in _issues(events):
            if not issue["attributes"].get("in_progress"):
                continue
            created_dt = _parse_dt(issue["timestamp"])
            if not created_dt or created_dt > reference:
                continue
            resolved_at = issue["attributes"].get("resolved_at")
            if resolved_at is None:
                count += 1
            else:
                resolved_dt = _parse_dt(resolved_at)
                if resolved_dt and resolved_dt > reference:
                    count += 1
        return float(count)

    return {
        "current": _twip(c_end),
        "previous": _twip(p_end),
        "unit": "issues",
    }


def compute_bur(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Burnout Rate proxy = % of active engineers with >3 after-hours commits."""
    def _bur(start: datetime, end: datetime) -> float:
        period_commits = _commits(events, start, end)
        if not period_commits:
            return 0.0
        by_author: dict[str, dict] = {}
        for c in period_commits:
            email = c["attributes"].get("author_email") or "unknown"
            if email not in by_author:
                by_author[email] = {"total": 0, "after_hours": 0}
            by_author[email]["total"] += 1
            if c["attributes"].get("after_hours"):
                by_author[email]["after_hours"] += 1
        total = len(by_author)
        at_risk = sum(1 for s in by_author.values() if s["after_hours"] > 3)
        return (at_risk / total) * 100

    return {
        "current": _bur(c_start, c_end),
        "previous": _bur(p_start, p_end),
        "unit": "%",
    }


def compute_cqi(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Code Quality Index proxy = pipeline success rate (%)."""
    def _cqi(pipes: list[dict]) -> float:
        if not pipes:
            return 0.0
        successful = sum(1 for p in pipes if p["attributes"].get("status") == "success")
        return (successful / len(pipes)) * 100

    return {
        "current": _cqi(_pipelines(events, c_start, c_end)),
        "previous": _cqi(_pipelines(events, p_start, p_end)),
        "unit": "%",
    }


def compute_mic(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Maintainability Issue Count = open bugs older than 14 days."""
    def _mic(reference: datetime) -> float:
        cutoff = reference - timedelta(days=14)
        count = 0
        for issue in _issues(events):
            if issue["attributes"].get("issue_type") != "Bug":
                continue
            if issue["attributes"].get("resolved_at") is not None:
                continue
            created_dt = _parse_dt(issue["timestamp"])
            if created_dt and created_dt < cutoff:
                count += 1
        return float(count)

    return {
        "current": _mic(c_end),
        "previous": _mic(p_end),
        "unit": "issues",
    }


# ---------------------------------------------------------------------------
# Added metrics (Change 1)
# ---------------------------------------------------------------------------

def compute_bf(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """
    Bus Factor — individual sustainability (individual dimension).
    Formula: % of total commits authored by the single top contributor.
    A high % means the team depends heavily on one person — sustainability risk.
    Source: GitLab commits (entity_type='commit')
    """
    def _bf(start: datetime, end: datetime) -> float:
        period_commits = _commits(events, start, end)
        if not period_commits:
            return 0.0
        by_author: dict[str, int] = {}
        for c in period_commits:
            email = c["attributes"].get("author_email") or "unknown"
            by_author[email] = by_author.get(email, 0) + 1
        total = sum(by_author.values())
        if total == 0:
            return 0.0
        top = max(by_author.values())
        return (top / total) * 100

    return {
        "current": _bf(c_start, c_end),
        "previous": _bf(p_start, p_end),
        "unit": "%",
    }


def compute_pr_count(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """
    Pull Request Count — activity metric.
    Formula: count of MRs created in period, split by state (open/merged/closed).
    Source: GitLab MRs (entity_type='mr')
    """
    def _pr_count(start: datetime, end: datetime) -> tuple[float, dict]:
        period_mrs = [
            e for e in events
            if e["entity_type"] == "mr" and _in_period(e["timestamp"], start, end)
        ]
        breakdown: dict[str, int] = {"open": 0, "merged": 0, "closed": 0}
        for m in period_mrs:
            state = m["attributes"].get("state", "open")
            if state in breakdown:
                breakdown[state] += 1
            else:
                breakdown["open"] += 1
        return float(len(period_mrs)), breakdown

    c_count, c_breakdown = _pr_count(c_start, c_end)
    p_count, _ = _pr_count(p_start, p_end)
    return {
        "current": c_count,
        "previous": p_count,
        "unit": "pull_requests",
        "breakdown": c_breakdown,
    }


def compute_ahcr(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """
    After-Hours Commit Rate — % of all commits made outside 07:00–20:00 CET/CEST.
    Complements BUR: BUR tells you which fraction of the *team* is at risk;
    AHCR tells you what fraction of *all commit activity* happens after hours.
    Returns None when there are no commits in the period.
    """
    def _ahcr(start: datetime, end: datetime) -> float | None:
        period_commits = _commits(events, start, end)
        if not period_commits:
            return None
        after = sum(1 for c in period_commits if c["attributes"].get("after_hours"))
        return (after / len(period_commits)) * 100

    return {
        "current": _ahcr(c_start, c_end),
        "previous": _ahcr(p_start, p_end),
        "unit": "%",
    }


def compute_blds(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """
    Build Count — pipeline execution volume.
    Formula: count of all pipeline executions in period.
    Source: GitLab pipelines (entity_type='pipeline')
    """
    return {
        "current": float(len(_pipelines(events, c_start, c_end))),
        "previous": float(len(_pipelines(events, p_start, p_end))),
        "unit": "builds",
    }


def compute_pipeline_status_breakdown(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """
    Pipeline Status Breakdown — for trend chart visualisation.
    Formula: count of pipelines per status (success/failed/canceled) per day.
    Source: GitLab pipelines (entity_type='pipeline')
    Note: not registered in METRIC_FUNCTIONS; call directly for chart data.
    """
    all_pipes = _pipelines(events, c_start, c_end)

    by_day: dict[str, dict[str, int]] = {}
    for p in all_pipes:
        dt = _parse_dt(p["timestamp"])
        if dt:
            day_str = dt.strftime("%Y-%m-%d")
            if day_str not in by_day:
                by_day[day_str] = {"success": 0, "failed": 0, "canceled": 0}
            status = p["attributes"].get("status", "")
            if status in ("success", "failed", "canceled"):
                by_day[day_str][status] += 1

    daily_breakdown = [
        {"date": day, **counts}
        for day, counts in sorted(by_day.items())
    ]

    return {
        "current": float(len(all_pipes)),
        "previous": float(len(_pipelines(events, p_start, p_end))),
        "unit": "pipelines",
        "daily_breakdown": daily_breakdown,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

METRIC_FUNCTIONS: dict[str, Any] = {
    "CFR":  compute_cfr,
    "DF":   compute_df,
    "MTTR": compute_mttr,
    "LTfC": compute_ltfc,
    "PRCT": compute_prct,
    "PRSi": compute_prsi,
    "TWiP": compute_twip,
    "BUR":  compute_bur,
    "CQI":  compute_cqi,
    "MIC":  compute_mic,
    # Added (Change 1)
    "BF":   compute_bf,
    "BLDS": compute_blds,
    "PR":   compute_pr_count,
    # After-hours activity
    "AHCR": compute_ahcr,
}


def parse_events(raw_events: list) -> list[dict]:
    """Convert RawEvent ORM objects (or raw dicts) into computation-ready dicts.
    Parses the JSON attributes string into a dict.
    """
    result = []
    for e in raw_events:
        if hasattr(e, "__dict__"):
            # SQLAlchemy ORM object
            row = {
                "entity_type": e.entity_type,
                "source": e.source,
                "entity_id": e.entity_id,
                "project_id": e.project_id,
                "timestamp": e.timestamp,
                "attributes": json.loads(e.attributes),
            }
        else:
            # Already a dict (e.g. from normaliser)
            row = dict(e)
            if isinstance(row.get("attributes"), str):
                row["attributes"] = json.loads(row["attributes"])
        result.append(row)
    return result


def compute_all(
    raw_events: list,
    c_start: datetime,
    c_end: datetime,
    p_start: datetime,
    p_end: datetime,
    codes: list[str] = None,
    release_tag_pattern: str = DEFAULT_TAG_PATTERN,
) -> list[dict]:
    """Run metric functions for the given date ranges and return results.

    Each result dict: {metric_code, current_value, previous_value, unit}
    If codes is provided, only those metrics are computed.
    release_tag_pattern is forwarded to DF/CFR (which use it to detect releases).
    """
    events = parse_events(raw_events)
    results = []
    # Metrics that accept the optional release_tag_pattern kwarg.
    tag_aware = {"CFR", "DF", "LTfC"}
    for code, fn in METRIC_FUNCTIONS.items():
        if codes and code not in codes:
            continue
        try:
            if code in tag_aware:
                out = fn(events, c_start, c_end, p_start, p_end, release_tag_pattern=release_tag_pattern)
            else:
                out = fn(events, c_start, c_end, p_start, p_end)
            results.append({
                "metric_code": code,
                "current_value": out["current"],
                "previous_value": out["previous"],
                "unit": out["unit"],
            })
        except Exception as exc:
            logger.warning("compute_%s failed: %s", code, exc)
    return results
