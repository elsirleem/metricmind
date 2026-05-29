"""Step 10 — LLM Call 3: stakeholder-adapted explanation generation."""

import json
import logging
import re

from pydantic import ValidationError

from backend.pipeline.llm_client import call_llm, _strip_fences
from backend.schemas.reasoning import ExplanationOutput

logger = logging.getLogger(__name__)

# Strip raw conflict_type identifiers if the LLM leaks them into the human text.
# Matches "(key_person_risk)", "  (speed_stability) ", etc.
_CONFLICT_CODE_INLINE = re.compile(
    r"\s*\((?:key_person_risk|speed_stability|throughput_sustainability|cost_reliability|other)\)",
    re.IGNORECASE,
)


def _strip_conflict_codes(text: str | None) -> str | None:
    """Remove any inline (conflict_type) identifiers from human-facing text."""
    if not isinstance(text, str):
        return text
    return _CONFLICT_CODE_INLINE.sub("", text)

SYSTEM_PROMPT_CALL3 = """
You are a communication layer for a decision intelligence system.
Translate the reasoning report into a stakeholder-appropriate explanation.

Adapt to stakeholder_role:
- engineer: use metric codes and values; focus on what the individual contributor
  or their squad can act on in the next sprint (concrete code, review, testing,
  or workflow changes). Explain root causes at the code/process level. Avoid
  team-management framing — engineers do not set headcount or sprint scope.
- engineering_lead: use metric codes and values, explain root causes, be direct
  about severity. Frame recommendations as team-level decisions the lead owns
  (capacity, prioritisation, process changes).
- product_owner: frame as sprint/delivery risk, avoid deep technical detail.
- cto_vp_engineering: frame as business risk, reference declared KPI thresholds explicitly.
- business_analyst: plain language only (no metric codes), but more depth than an
  executive summary. Use plain-language quantities ("the team shipped 12 releases
  this month" instead of "DF = 12"). Allow longer key findings and richer narrative
  because analysts produce write-ups, not single-pane dashboards.

Return a JSON object with exactly these keys:
- summary: 2 sentences max, overall health and primary concern
- key_findings: markdown, one paragraph per HIGH/CRITICAL conflict only
- sustainability_note: markdown, always present. If no flags: confirm indicators are healthy.
- recommended_actions: markdown ordered list, highest priority first. For each recommendation
  in the reasoning report include:
  - A one-sentence explanation of why this specific recommendation applies to this team's context
  - One concrete first action the team could take this sprint
  - The risk of not acting on this recommendation given the current metric trend
- tradeoff_explanation: markdown, what happens if top recommendation is followed vs not

Rules:
- Do not invent data not present in the reasoning report.
- Do not soften CRITICAL severity findings.
- Never use metric codes when stakeholder_role is business_analyst.
- Never print the raw conflict_type identifier (e.g. "key_person_risk",
  "speed_stability") in the human-readable text. Use the natural-language
  name only (e.g. "Key Person Risk", "Speed vs. Stability"). The identifier
  is an internal field and must not appear in summary, key_findings,
  sustainability_note, recommended_actions, or tradeoff_explanation.
- Return only valid JSON. No preamble. No markdown fences.
"""

USER_PROMPT_CALL3 = """
Stakeholder role: {stakeholder_role}

Reasoning report:
{report_json}

Declared KPIs for business context:
{declared_kpis_json}

Return the explanation as JSON only.
"""


async def run_call3(stakeholder_role: str, report: dict, declared_kpis: list) -> dict:
    """
    Call 3: explanation generation.
    Validates response against ExplanationOutput schema.
    Raises ValueError on validation failure.
    """
    user_prompt = USER_PROMPT_CALL3.format(
        stakeholder_role=stakeholder_role,
        report_json=json.dumps(report, indent=2),
        declared_kpis_json=json.dumps(declared_kpis, indent=2),
    )
    raw = await call_llm(SYSTEM_PROMPT_CALL3, user_prompt, max_tokens=2000)
    clean = _strip_fences(raw)

    try:
        data = json.loads(clean)
        sections = data if "summary" in data else data.get("sections", data)
        # Defensive cleanup: strip any leaked conflict_type identifiers from
        # the human-facing text fields, regardless of whether the LLM followed
        # the system-prompt rule.
        for key in ("summary", "key_findings", "sustainability_note",
                    "recommended_actions", "tradeoff_explanation"):
            if key in sections:
                sections[key] = _strip_conflict_codes(sections[key])

        profile_id = report.get("profile_id", "")
        from datetime import datetime, timezone
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        output = ExplanationOutput(
            profile_id=profile_id,
            stakeholder_role=stakeholder_role,
            sections=sections,
            generated_at=generated_at,
        )
        return output.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error("Call 3 response failed validation: %s\nRaw: %s", e, raw)
        raise ValueError(f"Call 3 response failed schema validation: {e}")
