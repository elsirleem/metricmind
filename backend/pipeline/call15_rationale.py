"""LLM Call 15: generate per-metric rationales for a given profile context."""

import json
import logging

from backend.pipeline.llm_client import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_CALL15 = """
You are explaining metric selections to a software engineering stakeholder.
Given a use case profile and selected metrics, write a one-sentence
rationale for each metric explaining WHY it matters for this specific context.

Rules:
- Each rationale must reference the stakeholder's stated goal or
  decision type specifically — not a generic description
- Maximum 20 words per rationale
- Plain language — no jargon or metric codes in rationale text
- Return JSON array: [{"code": "string", "rationale": "string"}]
- No markdown fences, no preamble
"""


async def run_call15(profile: dict, selected_metrics: list[dict]) -> list[dict]:
    """
    Generate one-sentence rationales for each selected metric given the profile context.
    Returns list of {"code": str, "rationale": str}.
    """
    user_prompt = json.dumps({
        "profile": {
            "primary_goal": profile.get("primary_goal"),
            "decision_type": profile.get("decision_type"),
            "stakeholder_role": profile.get("stakeholder_role"),
            "business_criticality": profile.get("business_criticality"),
        },
        "metrics": [
            {"code": m["code"], "name": m["name"], "tier": m["tier"]}
            for m in selected_metrics
        ],
    }, indent=2)

    for attempt in range(2):
        raw = await call_llm(SYSTEM_PROMPT_CALL15, user_prompt, max_tokens=1500)
        from backend.pipeline.llm_client import _strip_fences
        clean = _strip_fences(raw)
        try:
            data = json.loads(clean)
            if not isinstance(data, list):
                raise ValueError("Expected JSON array")
            return data
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 1:
                logger.error("Call 15 returned invalid JSON after retry: %s\nRaw: %s", e, raw)
                raise ValueError("Call 15 returned invalid JSON after retry")
            logger.warning("Call 15 JSON parse failed on attempt 1, retrying")
