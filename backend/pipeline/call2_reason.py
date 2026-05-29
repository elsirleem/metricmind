"""Step 8 — LLM Call 2: trade-off reasoning (most critical call)."""

import json
import logging
import re

from pydantic import ValidationError

from backend.pipeline.llm_client import call_llm
from backend.schemas.reasoning import ReasoningReport

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_CALL2 = """
You are a decision intelligence engine for software engineering teams.
You receive structured, pre-validated metric data. You do not compute metrics.

Analyse the snapshot and return a structured reasoning report as JSON.

Steps:
1. THRESHOLD ASSESSMENT — record threshold_status for each metric.
2. CONFLICT DETECTION — identify metric pairs in tension given stated goals.
   Conflict types: speed_stability | throughput_sustainability | cost_reliability | key_person_risk | other
   key_person_risk: high BF (>40%) combined with high MTTR — team is dangerously dependent on one
   contributor, which increases recovery time and individual sustainability risk.
3. SEVERITY SCORING — assign LOW/MEDIUM/HIGH/CRITICAL based on:
   business_criticality (mission_critical raises severity by one level),
   threshold_status (breach = higher), trend (degrading = higher),
   declared business_impact strings if present.
   For each declared_kpis entry, compare current_value to target_value:
   reference the gap explicitly in evidence (e.g. "Allocation Accuracy is 84%
   versus a 90% target — a 6-point shortfall"). Treat declared KPIs as
   first-class signals alongside computed metrics.
4. RECOMMENDATIONS — for HIGH or CRITICAL conflicts only, pick ONE code from:
   reduce_deployment_pace | invest_in_test_coverage | address_technical_debt |
   review_team_capacity | escalate_to_stakeholder | accept_risk_with_mitigation |
   investigate_incident_pattern | reduce_work_in_progress
5. SUSTAINABILITY FLAGS — always check BUR, DSAT_MANUAL, BF (individual dimension)
   and CQI, MIC (technical dimension). Flag any with warning or breach status.
6. OVERALL HEALTH — green if no HIGH/CRITICAL conflicts, amber if HIGH exists,
   red if CRITICAL exists or sustainability breach exists.

Return only valid JSON. No prose. No markdown fences.

CRITICAL JSON RULES:
- Return ONLY raw JSON — no markdown fences, no backticks
- Use exactly these root keys:
  profile_id, snapshot_timestamp, overall_health,
  threshold_assessments, conflicts, recommendations,
  sustainability_flags
- conflicts items must have: metric_a, metric_b,
  conflict_type, severity, evidence
- recommendations items must have: code, target_metrics, priority
- Do not add any extra root keys outside this list
"""

USER_PROMPT_CALL2 = """
Confirmed profile:
{profile_json}

Metric snapshot:
{snapshot_json}

Return the reasoning report as JSON only.
"""


def clean_llm_json(raw: str) -> str:
    raw = raw.strip()
    # Remove opening fence
    raw = re.sub(r'^```(?:json)?\s*\n?', '', raw)
    # Remove closing fence
    raw = re.sub(r'\n?```\s*$', '', raw)
    return raw.strip()


def normalise_report(data: dict, profile_id: str) -> dict:
    # Ensure profile_id is set
    data["profile_id"] = profile_id

    # Normalise conflicts field name
    if "conflict_detection" in data and "conflicts" not in data:
        raw_conflicts = data.pop("conflict_detection")
        normalised = []
        for c in raw_conflicts:
            metrics = c.get("metrics_in_tension",
                           c.get("metrics_involved", []))
            normalised.append({
                "metric_a": metrics[0] if len(metrics) > 0 else "",
                "metric_b": metrics[1] if len(metrics) > 1 else "",
                "conflict_type": c.get("type", "other"),
                "severity": c.get("severity",
                           c.get("final_severity", "LOW")),
                "evidence": c.get("description", "")[:200]
            })
        data["conflicts"] = normalised

    # Normalise recommendations field
    if "recommendations" in data:
        normalised_recs = []
        for r in data["recommendations"]:
            code = r.get("recommendation_code", r.get("code", ""))
            normalised_recs.append({
                "code": code,
                "target_metrics": r.get("metrics_in_tension",
                                       r.get("target_metrics", [])),
                "priority": r.get("priority", "this_sprint")
            })
        data["recommendations"] = normalised_recs

    # Normalise threshold_assessments field name
    if "threshold_assessment" in data and \
       "threshold_assessments" not in data:
        data["threshold_assessments"] = data.pop("threshold_assessment")

    if "threshold_assessments" in data:
        for item in data["threshold_assessments"]:
            # LLMs commonly emit "code"; schema expects "metric_code"
            if "metric_code" not in item and "code" in item:
                item["metric_code"] = item.pop("code")
            # Claude uses threshold_status, schema expects status
            if "status" not in item and "threshold_status" in item:
                item["status"] = item.pop("threshold_status")
            # Ensure current_value exists
            if "current_value" not in item:
                item["current_value"] = item.get("value", 0.0)
            # Ensure threshold_value exists
            if "threshold_value" not in item:
                item["threshold_value"] = None

    if "sustainability_flags" in data:
        # Filter out non-standard flag codes the LLM occasionally invents
        # (e.g. "CFR_REWORK", "KPI_*") — schema requires metric_code to be
        # a real code, and the downstream UI matches by code.
        valid_flags = []
        for flag in data["sustainability_flags"]:
            # LLMs commonly emit "code"; schema expects "metric_code"
            if "metric_code" not in flag and "code" in flag:
                flag["metric_code"] = flag.pop("code")
            # Ensure dimension field exists
            if "dimension" not in flag or flag.get("dimension") not in ("individual", "technical"):
                # Infer from metric code
                individual_metrics = [
                    "BUR", "DSAT_MANUAL", "HAP", "DSAT",
                    "AR", "RR", "BF"
                ]
                code = flag.get("metric_code", "")
                flag["dimension"] = (
                    "individual"
                    if code in individual_metrics
                    else "technical"
                )
            # Ensure status field exists
            if "status" not in flag:
                flag["status"] = flag.get(
                    "flag_status", "warning"
                )
            # Ensure consecutive_periods exists
            if "consecutive_periods" not in flag:
                flag["consecutive_periods"] = 1
            valid_flags.append(flag)
        data["sustainability_flags"] = valid_flags

    # Normalise recommendation priorities — LLMs sometimes emit
    # 'critical' / 'high' / 'medium' / 'low' instead of the allowed
    # 'immediate' / 'this_sprint' / 'strategic' set. Map them.
    if "recommendations" in data:
        priority_map = {
            "critical": "immediate",
            "high": "immediate",
            "medium": "this_sprint",
            "low": "strategic",
            "p1": "immediate", "p2": "this_sprint",
            "p3": "strategic", "p4": "strategic",
        }
        allowed_priority = {"immediate", "this_sprint", "strategic"}
        for r in data["recommendations"]:
            p = (r.get("priority") or "").lower()
            if p in priority_map:
                r["priority"] = priority_map[p]
            elif p not in allowed_priority:
                r["priority"] = "this_sprint"
            # Strip any rationale/explanation fields not in the schema —
            # they belong in Call 3 output, not Call 2.
            for extra in ("rationale", "explanation", "reason"):
                r.pop(extra, None)

    # Remove extra fields not in schema
    allowed = {"profile_id", "snapshot_timestamp", "overall_health",
               "threshold_assessments", "conflicts",
               "recommendations", "sustainability_flags"}
    for key in list(data.keys()):
        if key not in allowed:
            data.pop(key)

    # Ensure snapshot_timestamp exists
    if "snapshot_timestamp" not in data:
        from datetime import datetime, timezone
        data["snapshot_timestamp"] = datetime.now(
            timezone.utc).isoformat()

    return data


async def run_call2(profile: dict, snapshot: dict) -> dict:
    """
    Call 2: trade-off reasoning.
    Validates response against ReasoningReport schema.
    Raises ValueError on validation failure.
    """
    profile_id = profile.get("id", "")
    user_prompt = USER_PROMPT_CALL2.format(
        profile_json=json.dumps(profile, indent=2),
        snapshot_json=json.dumps(snapshot, indent=2),
    )
    raw = await call_llm(SYSTEM_PROMPT_CALL2, user_prompt, max_tokens=4000)
    clean = clean_llm_json(raw)

    try:
        data = json.loads(clean)
        data = normalise_report(data, profile_id)
        return ReasoningReport(**data).model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error("Call 2 response failed validation: %s\nRaw: %s", e, raw)
        raise ValueError(f"Call 2 response failed schema validation: {e}")
