"""LLM Call 16: derive a computation formula for an AI-derivable metric."""

import json
import logging

from backend.pipeline.llm_client import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_CALL16 = """
You are a software engineering metrics expert helping operationalise
a DevOps metric for a decision intelligence system.

Given a metric name and available data sources, propose a concrete
computation formula grounded in software engineering research.

Rules:
- Formula must only use data available from the listed sources
- Ground the formula in software engineering research concepts
- Confidence levels:
  HIGH = well-established formula in literature
  MEDIUM = reasonable proxy with research basis
  LOW = speculative — flag clearly
- Return JSON with exactly these keys:
  formula, plain_language, data_fields_required,
  confidence, research_basis
- No markdown fences, no preamble
- plain_language max 30 words
- research_basis max one sentence
"""


async def run_call16(metric_code: str, metric_name: str, available_sources: list[str]) -> dict:
    """
    Propose a computation formula for the given metric using available data sources.
    Returns {"formula", "plain_language", "data_fields_required", "confidence", "research_basis"}.
    """
    user_prompt = json.dumps({
        "metric_code": metric_code,
        "metric_name": metric_name,
        "available_sources": available_sources,
    }, indent=2)

    for attempt in range(2):
        raw = await call_llm(SYSTEM_PROMPT_CALL16, user_prompt, max_tokens=600)
        from backend.pipeline.llm_client import _strip_fences
        clean = _strip_fences(raw)
        try:
            data = json.loads(clean)
            required_keys = {"formula", "plain_language", "data_fields_required", "confidence", "research_basis"}
            missing = required_keys - set(data.keys())
            if missing:
                raise ValueError(f"Missing keys: {missing}")
            return data
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 1:
                logger.error("Call 16 returned invalid JSON after retry: %s\nRaw: %s", e, raw)
                raise ValueError("Call 16 returned invalid JSON after retry")
            logger.warning("Call 16 JSON parse failed on attempt 1, retrying")
