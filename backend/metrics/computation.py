"""
Metric computation service.

All individual metric functions now receive explicit date ranges:
  compute_X(events, c_start, c_end, p_start, p_end) -> dict

compute_all() resolves a TimeWindow into date ranges and runs all functions.
Each function returns {"current": float, "previous": float, "unit": str}.

Current period  = [c_start, c_end)
Previous period = [p_start, p_end)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


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
# Individual metric functions
# ---------------------------------------------------------------------------

def compute_cfr(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Change Failure Rate = failed pipelines / total pipelines * 100  (%)"""
    def _cfr(pipes: list[dict]) -> float:
        if not pipes:
            return 0.0
        failed = sum(1 for p in pipes if p["attributes"].get("status") == "failed")
        return (failed / len(pipes)) * 100

    return {
        "current": _cfr(_pipelines(events, c_start, c_end)),
        "previous": _cfr(_pipelines(events, p_start, p_end)),
        "unit": "%",
    }


def compute_df(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Deployment Frequency = count of successful deployments to main/master/trunk/develop."""
    def _df(pipes: list[dict]) -> float:
        return float(sum(
            1 for p in pipes
            if p["attributes"].get("status") == "success"
            and p["attributes"].get("ref") in ("main", "master", "trunk", "develop")
        ))

    return {
        "current": _df(_pipelines(events, c_start, c_end)),
        "previous": _df(_pipelines(events, p_start, p_end)),
        "unit": "deployments",
    }


def compute_mttr(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Mean Time to Recover = avg hours from incident open to resolved."""
    def _mttr(start: datetime, end: datetime) -> float:
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
        return _mean(deltas)

    return {
        "current": _mttr(c_start, c_end),
        "previous": _mttr(p_start, p_end),
        "unit": "hours",
    }


def compute_ltfc(
    events: list[dict],
    c_start: datetime, c_end: datetime,
    p_start: datetime, p_end: datetime,
) -> dict:
    """Lead Time for Changes = avg hours from MR created_at to merged_at.
    Note: GitLab's commits API does not tag commits with branch names, so
    MR created_at is used as the best available proxy for 'first commit on branch'.
    """
    def _ltfc(start: datetime, end: datetime) -> float:
        deltas = []
        for m in _merged_mrs_in(_mrs(events), start, end):
            created_dt = _parse_dt(m["timestamp"])
            merged_dt = _parse_dt(m["attributes"]["merged_at"])
            if created_dt and merged_dt:
                deltas.append((merged_dt - created_dt).total_seconds() / 3600)
        return _mean(deltas)

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
    """Pull Request Cycle Time = avg hours from MR created to merged."""
    def _prct(start: datetime, end: datetime) -> float:
        deltas = []
        for m in _merged_mrs_in(_mrs(events), start, end):
            created_dt = _parse_dt(m["timestamp"])
            merged_dt = _parse_dt(m["attributes"]["merged_at"])
            if created_dt and merged_dt:
                deltas.append((merged_dt - created_dt).total_seconds() / 3600)
        return _mean(deltas)

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
    """Pull Request Size = avg lines changed per merged MR (changes_count proxy)."""
    def _prsi(start: datetime, end: datetime) -> float:
        sizes = [
            m["attributes"]["changes_count"]
            for m in _merged_mrs_in(_mrs(events), start, end)
            if m["attributes"].get("changes_count") is not None
        ]
        return _mean([float(s) for s in sizes])

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
) -> list[dict]:
    """Run metric functions for the given date ranges and return results.

    Each result dict: {metric_code, current_value, previous_value, unit}
    If codes is provided, only those metrics are computed.
    """
    events = parse_events(raw_events)
    results = []
    for code, fn in METRIC_FUNCTIONS.items():
        if codes and code not in codes:
            continue
        try:
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
