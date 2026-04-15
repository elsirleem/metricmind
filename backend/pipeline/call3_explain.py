"""Step 10 — LLM Call 3: stakeholder-adapted explanation generation."""

import json
import logging

from pydantic import ValidationError

from backend.pipeline.llm_client import call_llm, _strip_fences
from backend.schemas.reasoning import ExplanationOutput

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_CALL3 = """
You are a communication layer for a decision intelligence system.
Translate the reasoning report into a stakeholder-appropriate explanation.

Adapt to stakeholder_role:
- engineering_lead: use metric codes and values, explain root causes, be direct about severity.
- product_owner: frame as sprint/delivery risk, avoid deep technical detail.
- cto_vp_engineering: frame as business risk, reference declared KPI thresholds explicitly.
- business_stakeholder: no metric codes, plain language only, max 3 key points.

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
- Never use metric codes when stakeholder_role is business_stakeholder.
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
        profile_id = report.get("profile_id", "")
        from datetime import datetime, timezone
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        output = ExplanationOutput(
            profile_id=profile_id,
            stakeholder_role=stakeholder_role,
            sections=data if "summary" in data else data.get("sections", data),
            generated_at=generated_at,
        )
        return output.model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error("Call 3 response failed validation: %s\nRaw: %s", e, raw)
        raise ValueError(f"Call 3 response failed schema validation: {e}")
