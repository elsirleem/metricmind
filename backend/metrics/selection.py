"""
Metric selection engine.
Looks up the relevant metric subset for a given profile using a predefined matrix.
Key: (primary_goal, decision_type, business_criticality)
Value: {"devops": [...], "business": [...], "sustainability": [...]}

Metrics with suffix _MANUAL are not computed from source data.
They are provided as declared_kpis or manual input, and included in the snapshot
if present — skipped with a logged warning if absent.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Selection matrix (Section 10)
# ---------------------------------------------------------------------------

SELECTION_MATRIX: dict[tuple[str, str, str], dict[str, list[str]]] = {
    # UC1 — Release readiness, reliability focus, mission critical
    ("maximize_reliability", "release_readiness", "mission_critical"): {
        "devops":         ["CFR", "DF", "MTTR", "CQI"],
        "business":       ["CSAT_MANUAL", "SLA_MANUAL"],
        "sustainability": ["BUR", "DSAT_MANUAL", "MIC", "BF"],
    },

    # UC1b — Release readiness, reliability focus, business important
    ("maximize_reliability", "release_readiness", "business_important"): {
        "devops":         ["CFR", "DF", "MTTR", "CQI"],
        "business":       ["CSAT_MANUAL", "SLA_MANUAL"],
        "sustainability": ["BUR", "DSAT_MANUAL", "MIC", "BF"],
    },

    # UC2 — Sprint planning, delivery speed focus
    ("maximize_delivery_speed", "sprint_planning", "business_important"): {
        "devops":         ["LTfC", "PRCT", "PRSi", "TWiP", "DF"],
        "business":       ["VEL_MANUAL", "WIV_MANUAL"],
        "sustainability": ["BUR", "MIC"],
    },

    # UC3 — Team health review, wellbeing focus
    ("improve_developer_wellbeing", "team_health_review", "business_important"): {
        "devops":         ["MTTR", "CFR", "PRCT"],
        "business":       ["GOAL_MANUAL"],
        "sustainability": ["BUR", "DSAT_MANUAL", "MIC", "BF"],
    },

    # UC4 — Stakeholder reporting, CTO audience
    ("maximize_reliability", "stakeholder_reporting", "mission_critical"): {
        "devops":         ["DF", "CFR", "MTTR", "LTfC"],
        "business":       ["CSAT_MANUAL", "SLA_MANUAL", "TCO_MANUAL"],
        "sustainability": ["DSAT_MANUAL", "BUR", "MIC"],
    },

    # UC5 — Security posture review
    ("improve_security_posture", "release_readiness", "mission_critical"): {
        "devops":         ["CFR", "CQI", "MIC", "PRCT"],
        "business":       ["SLA_MANUAL", "CSAT_MANUAL"],
        "sustainability": ["BUR", "MIC"],
    },
}

# Fallback for unrecognised profile combinations
DEFAULT_SELECTION: dict[str, list[str]] = {
    "devops":         ["CFR", "DF", "MTTR", "LTfC"],
    "business":       ["CSAT_MANUAL"],
    "sustainability": ["BUR", "DSAT_MANUAL"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_metrics(
    primary_goal: str,
    decision_type: str,
    business_criticality: str,
) -> dict[str, list[str]]:
    """
    Return the metric selection dict for the given profile triple.
    Falls back to DEFAULT_SELECTION and logs a warning for unknown combinations.
    """
    key = (primary_goal, decision_type, business_criticality)
    selection = SELECTION_MATRIX.get(key)

    if selection is None:
        logger.warning(
            "No selection matrix entry for (%s, %s, %s) — using default selection",
            primary_goal, decision_type, business_criticality,
        )
        return DEFAULT_SELECTION

    return selection


def get_manual_codes(selection: dict[str, list[str]]) -> list[str]:
    """Return all _MANUAL metric codes from a selection dict."""
    manual = []
    for codes in selection.values():
        for code in codes:
            if code.endswith("_MANUAL") and code not in manual:
                manual.append(code)
    return manual


def get_computed_codes(selection: dict[str, list[str]]) -> list[str]:
    """Return all non-_MANUAL metric codes from a selection dict."""
    computed = []
    for codes in selection.values():
        for code in codes:
            if not code.endswith("_MANUAL") and code not in computed:
                computed.append(code)
    return computed


def get_all_codes(selection: dict[str, list[str]]) -> list[str]:
    """Return all metric codes (manual + computed) from a selection dict."""
    return get_computed_codes(selection) + get_manual_codes(selection)
