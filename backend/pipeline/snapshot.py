"""
Step 7 — Snapshot assembler.
Reads the latest computed and manual metrics for a profile, applies threshold
checks and trend computation, and returns a fully populated MetricSnapshot.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import Profile, ComputedMetric, ManualMetric
from backend.metrics.selection import select_metrics, get_all_codes
from backend.metrics.threshold import check_threshold
from backend.schemas.snapshot import MetricRecord, MetricSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric metadata catalogue
# code → name, group, tier, sustainability_dimension, higher_is_better, source
# ---------------------------------------------------------------------------
METRIC_METADATA: dict[str, dict] = {
    # Computed — DevOps
    "CFR":  {"name": "Change Failure Rate",       "group": "delivery",     "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": False, "source": "gitlab"},
    "DF":   {"name": "Deployment Frequency",      "group": "delivery",     "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": True,  "source": "gitlab"},
    "MTTR": {"name": "Mean Time to Recover",      "group": "reliability",  "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": False, "source": "jira"},
    "LTfC": {"name": "Lead Time for Changes",     "group": "delivery",     "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": False, "source": "gitlab"},
    "PRCT": {"name": "Pull Request Cycle Time",   "group": "delivery",     "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": False, "source": "gitlab"},
    "PRSi": {"name": "Pull Request Size",         "group": "delivery",     "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": False, "source": "gitlab"},
    "TWiP": {"name": "Team Work in Progress",     "group": "flow",         "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": False, "source": "jira"},
    "CQI":  {"name": "Code Quality Index",        "group": "quality",      "tier": "devops",          "sustainability_dimension": None,         "higher_is_better": True,  "source": "gitlab"},
    # Computed — Sustainability
    "BUR":  {"name": "Burnout Rate",              "group": "wellbeing",    "tier": "sustainability",  "sustainability_dimension": "individual", "higher_is_better": False, "source": "gitlab"},
    "MIC":  {"name": "Maintainability Issue Count","group": "quality",     "tier": "sustainability",  "sustainability_dimension": "technical",  "higher_is_better": False, "source": "jira"},
    # Manual — Business
    "CSAT_MANUAL":  {"name": "Customer Satisfaction Score", "group": "customer",  "tier": "business",       "sustainability_dimension": None,         "higher_is_better": True,  "source": "manual"},
    "SLA_MANUAL":   {"name": "SLA Compliance",              "group": "reliability","tier": "business",       "sustainability_dimension": None,         "higher_is_better": True,  "source": "manual"},
    "VEL_MANUAL":   {"name": "Sprint Velocity",             "group": "delivery",  "tier": "business",       "sustainability_dimension": None,         "higher_is_better": True,  "source": "manual"},
    "WIV_MANUAL":   {"name": "Work Item Volume",            "group": "delivery",  "tier": "business",       "sustainability_dimension": None,         "higher_is_better": True,  "source": "manual"},
    "TCO_MANUAL":   {"name": "Total Cost of Ownership",     "group": "cost",      "tier": "business",       "sustainability_dimension": None,         "higher_is_better": False, "source": "manual"},
    "GOAL_MANUAL":  {"name": "Goal Completion Rate",        "group": "delivery",  "tier": "business",       "sustainability_dimension": None,         "higher_is_better": True,  "source": "manual"},
    # Manual — Sustainability
    "DSAT_MANUAL":  {"name": "Developer Satisfaction Score","group": "wellbeing", "tier": "sustainability",  "sustainability_dimension": "individual", "higher_is_better": True,  "source": "manual"},
    # Added (Change 1 / snapshot registration)
    "BF":   {"name": "Bus Factor",               "group": "wellbeing",  "tier": "sustainability", "sustainability_dimension": "individual", "higher_is_better": False, "source": "gitlab"},
    "BLDS": {"name": "Build Count",              "group": "delivery",   "tier": "devops",         "sustainability_dimension": None,         "higher_is_better": True,  "source": "gitlab"},
    "PR":   {"name": "Pull Request Count",       "group": "delivery",   "tier": "devops",         "sustainability_dimension": None,         "higher_is_better": True,  "source": "gitlab"},
    "AHCR": {"name": "After-Hours Commit Rate",  "group": "wellbeing",  "tier": "sustainability", "sustainability_dimension": "individual", "higher_is_better": False, "source": "gitlab"},
}

TREND_THRESHOLD = 0.02  # 2% change required to call improving/degrading


def _compute_trend(current: float, previous: float | None, higher_is_better: bool) -> str:
    if previous is None or previous == 0:
        return "stable"
    pct_change = (current - previous) / abs(previous)
    if higher_is_better:
        if pct_change > TREND_THRESHOLD:
            return "improving"
        if pct_change < -TREND_THRESHOLD:
            return "degrading"
    else:
        if pct_change < -TREND_THRESHOLD:
            return "improving"
        if pct_change > TREND_THRESHOLD:
            return "degrading"
    return "stable"


def build_snapshot(profile_id: str, period_days: int, db: Session) -> MetricSnapshot:
    """Assemble a MetricSnapshot for the given profile from the DB."""
    profile: Profile | None = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ValueError(f"Profile {profile_id} not found")

    declared_kpis: list = json.loads(profile.declared_kpis)

    # Metric selection
    selection = select_metrics(profile.primary_goal, profile.decision_type, profile.business_criticality)
    codes = get_all_codes(selection)

    # Latest computed metrics (one per code)
    computed_rows = (
        db.query(ComputedMetric)
        .filter(ComputedMetric.profile_id == profile_id)
        .order_by(ComputedMetric.computed_at.desc())
        .all()
    )
    computed_lookup: dict[str, ComputedMetric] = {}
    for row in computed_rows:
        if row.metric_code not in computed_lookup:
            computed_lookup[row.metric_code] = row

    # Latest manual metrics (one per code)
    manual_rows = (
        db.query(ManualMetric)
        .filter(ManualMetric.profile_id == profile_id)
        .order_by(ManualMetric.entered_at.desc())
        .all()
    )
    manual_lookup: dict[str, ManualMetric] = {}
    for row in manual_rows:
        if row.metric_code not in manual_lookup:
            manual_lookup[row.metric_code] = row

    metrics: list[MetricRecord] = []

    for code in codes:
        meta = METRIC_METADATA.get(code)
        if not meta:
            logger.warning("Unknown metric code %s — skipped", code)
            continue

        is_manual = code.endswith("_MANUAL")

        if is_manual:
            if code not in manual_lookup:
                logger.warning("%s not provided — excluded from snapshot", code)
                continue
            row = manual_lookup[code]
            current_value = row.current_value
            previous_value = row.previous_value
            unit = row.unit
        else:
            if code not in computed_lookup:
                logger.warning("Computed metric %s not found — excluded from snapshot", code)
                continue
            row = computed_lookup[code]
            if row.current_value is None:
                logger.warning("Computed metric %s has null current_value — excluded", code)
                continue
            current_value = row.current_value
            previous_value = row.previous_value
            unit = row.unit

        trend = _compute_trend(current_value, previous_value, meta["higher_is_better"])
        period_days = row.period_days if not is_manual else None
        threshold = check_threshold(code, current_value, declared_kpis, period_days=period_days)

        metrics.append(MetricRecord(
            code=code,
            name=meta["name"],
            current_value=current_value,
            previous_value=previous_value,
            unit=unit,
            trend=trend,
            threshold_status=threshold["status"],
            threshold_value=threshold["threshold_value"],
            threshold_source=threshold["threshold_source"],
            group=meta["group"],
            tier=meta["tier"],
            sustainability_dimension=meta["sustainability_dimension"],
            source=meta["source"],
        ))

    return MetricSnapshot(
        profile_id=profile_id,
        snapshot_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        period_days=period_days,
        metrics=metrics,
        declared_kpis=declared_kpis,
    )
