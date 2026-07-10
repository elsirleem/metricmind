"""
Threshold checker (Section 11).

Priority order for a given metric:
  1. If the metric code appears in profile.declared_kpis → use declared value + threshold_type
  2. Else if code is in DORA_THRESHOLDS → use DORA benchmark
  3. Else if code is in GENERAL_THRESHOLDS → use general benchmark
  4. Else → status='within', threshold_value=None, source='none'

Range-check algorithm for DORA/GENERAL thresholds:
  Check 'breach' range first (lo <= value < hi), then 'warning', then default to 'within'.
  This correctly handles open-ended "best" ranges (e.g. CQI=100 → 'within').
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DORA benchmark thresholds (source: DORA State of DevOps report)
# ---------------------------------------------------------------------------

DORA_THRESHOLDS: dict[str, dict] = {
    # CFR is computed as percent (0–100), so thresholds are on the same scale.
    # DORA 2022 boundaries: High 0–15%, Medium 16–30%, Low 46–60% (we collapse
    # 30–46 into the breach band).
    "CFR":  {"within": (0, 15),     "warning": (15, 30),     "breach": (30, 100),    "unit": "%"},
    "DF":   {"within": (1, 9999),   "warning": (0.5, 1),     "breach": (0, 0.5),     "unit": "deployments/day"},
    "MTTR": {"within": (0, 24),     "warning": (24, 168),    "breach": (168, 9999),  "unit": "hours"},
    "LTfC": {"within": (0, 24),     "warning": (24, 168),    "breach": (168, 9999),  "unit": "hours"},
}

# ---------------------------------------------------------------------------
# General thresholds for non-DORA metrics
# ---------------------------------------------------------------------------

GENERAL_THRESHOLDS: dict[str, dict] = {
    "BUR":  {"within": (0, 10),    "warning": (10, 25),   "breach": (25, 100),  "unit": "%"},
    "MIC":  {"within": (0, 5),     "warning": (5, 15),    "breach": (15, 9999), "unit": "issues"},
    "CQI":  {"within": (80, 100),  "warning": (60, 80),   "breach": (0, 60),    "unit": "%"},
    "PRCT": {"within": (0, 48),    "warning": (48, 120),  "breach": (120, 9999),"unit": "hours"},
    "PRSi": {"within": (0, 400),   "warning": (400, 800), "breach": (800, 9999),"unit": "lines"},
    "TWiP": {"within": (0, 5),     "warning": (5, 10),    "breach": (10, 9999), "unit": "issues"},
    # Bus Factor: >40% = warning (key person risk), >60% = breach (critical dependency)
    "BF":   {"within": (0, 40),    "warning": (40, 60),   "breach": (60, 100),  "unit": "%"},
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_range(value: float, thresholds: dict) -> str:
    """
    Determine threshold status from a range dict with 'breach'/'warning'/'within' keys.
    Checks breach first, then warning, defaults to 'within'.
    This handles open-ended best ranges (e.g. CQI=100 where within=(80,100)).
    """
    for status in ("breach", "warning"):
        lo, hi = thresholds[status]
        if lo <= value < hi:
            return status
    return "within"


def _check_declared(
    value: float,
    threshold_value: float,
    threshold_type: str,
) -> str:
    """
    Evaluate status against a user-declared KPI threshold.

    minimum → target is to be AT LEAST threshold_value
      within:  value >= threshold_value
      warning: value >= threshold_value * 0.9  (within 10% below target)
      breach:  value <  threshold_value * 0.9

    maximum → target is to be AT MOST threshold_value
      within:  value <= threshold_value
      warning: value <= threshold_value * 1.1  (within 10% above target)
      breach:  value >  threshold_value * 1.1

    target → value should be approximately equal to threshold_value
      within:  |diff| <= 5%
      warning: 5% < |diff| <= 20%
      breach:  |diff| > 20%
    """
    if threshold_value == 0:
        # Avoid division by zero; treat 0-threshold as a simple equality check
        return "within" if value == 0 else "breach"

    if threshold_type == "minimum":
        if value >= threshold_value:
            return "within"
        if value >= threshold_value * 0.9:
            return "warning"
        return "breach"

    if threshold_type == "maximum":
        if value <= threshold_value:
            return "within"
        if value <= threshold_value * 1.1:
            return "warning"
        return "breach"

    if threshold_type == "target":
        diff_pct = abs(value - threshold_value) / threshold_value
        if diff_pct <= 0.05:
            return "within"
        if diff_pct <= 0.20:
            return "warning"
        return "breach"

    # Unknown threshold_type — log and default to within
    logger.warning("Unknown threshold_type '%s' for declared KPI — defaulting to 'within'", threshold_type)
    return "within"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_threshold(
    metric_code: str,
    current_value: float,
    declared_kpis: Optional[list] = None,
    period_days: Optional[int] = None,
) -> dict:
    """
    Return threshold assessment for a single metric.

    period_days: the reporting window length backing current_value. Required
    to classify DF correctly — DF is reported as a raw release count over
    the period, but its DORA benchmark is defined as a rate (deployments/day).
    Without it, DF falls back to comparing the raw count against the rate
    thresholds, which over-credits any repo with at least one release.

    Returns:
        {
            "status":           "within" | "warning" | "breach",
            "threshold_value":  float | None,
            "threshold_source": "declared" | "dora_benchmark" | "periodic_system" | "none",
        }
    """
    declared_kpis = declared_kpis or []

    # --- 1. Check declared KPIs ---
    for kpi in declared_kpis:
        # kpi may be a DeclaredKPI Pydantic model or a plain dict
        if isinstance(kpi, dict):
            name = kpi.get("name")
            # Accept new `target_value` field, fall back to legacy `value` for old profiles
            target = kpi.get("target_value", kpi.get("value"))
            threshold_type = kpi.get("threshold_type")
        else:
            name = kpi.name
            target = getattr(kpi, "target_value", None) or getattr(kpi, "value", None)
            threshold_type = kpi.threshold_type

        # Match by metric code OR by name (declared KPIs may use metric codes as names)
        if name == metric_code or name.upper().replace(" ", "_") == metric_code:
            status = _check_declared(current_value, float(target), threshold_type)
            return {
                "status": status,
                "threshold_value": float(target),
                "threshold_source": "declared",
            }

    # --- 2. DORA benchmark ---
    if metric_code in DORA_THRESHOLDS:
        thresholds = DORA_THRESHOLDS[metric_code]
        # Use the boundary between 'within' and 'warning' as the displayed threshold value
        threshold_value = thresholds["warning"][0]

        if metric_code == "DF" and period_days:
            # DF's benchmark is a rate (deployments/day) but current_value is
            # a raw release count over the period — convert to a rate for
            # classification, then scale the boundary back to a period count
            # so threshold_value stays comparable to current_value.
            status = _check_range(current_value / period_days, thresholds)
            threshold_value = threshold_value * period_days
        else:
            status = _check_range(current_value, thresholds)

        return {
            "status": status,
            "threshold_value": threshold_value,
            "threshold_source": "dora_benchmark",
        }

    # --- 3. General benchmark ---
    if metric_code in GENERAL_THRESHOLDS:
        status = _check_range(current_value, GENERAL_THRESHOLDS[metric_code])
        threshold_value = GENERAL_THRESHOLDS[metric_code]["warning"][0]
        return {
            "status": status,
            "threshold_value": threshold_value,
            "threshold_source": "periodic_system",
        }

    # --- 4. No threshold available ---
    return {
        "status": "within",
        "threshold_value": None,
        "threshold_source": "none",
    }
