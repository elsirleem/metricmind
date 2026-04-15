"""Step 9 — LLM Call 1: profile interpretation from free-text description."""

import json
import logging

from backend.pipeline.llm_client import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_CALL1 = """
You are a DevOps metrics assistant helping configure a decision intelligence system.
Your only task is to map the user's description onto the provided JSON profile schema.

Rules:
- Only use values defined in the schema enums. Do not invent new field values.
- If a field cannot be determined from the description, set it to null.
- Return only valid JSON. No explanation, no preamble, no markdown fences.
- Always return declared_kpis as empty array [].
- Always set confirmed to false.
- business_criticality should be mission_critical if the system serves a large user base (10,000+ users), if failures cause significant reputational or operational damage, or if the system is critical infrastructure even if non-commercial. Open source projects with large user bases qualify as mission_critical. Do not default to business_important for widely-used public software.
"""

USER_PROMPT_CALL1 = """
Profile schema (use only these enum values):
{schema_json}

Use case description:
"{free_text}"

Return the populated profile as JSON only.
"""

USER_PROMPT_CALL1_WITH_ANSWERS = """
Profile schema (use only these enum values):
{schema_json}

Original description: "{free_text}"

I asked you these clarifying questions:
{questions_formatted}

The user answered:
{answers_formatted}

Now populate the full profile schema using both the description
and the answers. Return only valid JSON, no markdown fences.
"""

SYSTEM_PROMPT_CALL1A = """
You are configuring a DevOps decision intelligence system.
Given a use case description, do two things:

1. Extract what you can determine with HIGH confidence into
   a partial profile JSON. Set uncertain fields to null.

2. Generate exactly 2-3 clarifying questions to resolve the
   most important null fields. Prioritise in this order:
   - stakeholder_role (critical for explanation generation)
   - business_criticality (critical for severity scoring)
   - decision_type (critical for metric selection)

Rules:
- Ask only what you cannot determine from the description
- Questions must be specific and answerable in one sentence
- Do not ask about data sources
- Return JSON with exactly two keys:
  "questions": array of 2-3 question strings
  "partial_profile": profile object with null for uncertain fields
- No markdown fences, no preamble, no explanation

CRITICAL LENGTH RULES:
- Each question must be maximum 15 words long
- Keep questions concise and direct
- Do not explain or elaborate on questions
- Total response must fit within 500 tokens
- No markdown fences, no preamble, no explanation text outside the JSON

Example of correct question length:
"Who will read this analysis — engineering lead or CTO?"
"What happens to the business when the system goes down?"

Example of WRONG question length (too long):
"Are there any specific KPIs or metrics that the lead maintainer
currently uses or would like to use to assess release readiness?"
"""

USER_PROMPT_CALL1A = """
Profile schema (use only these enum values):
{schema_json}

Use case description:
"{free_text}"

Return JSON with questions and partial_profile only.
"""

# Schema hint sent to the LLM — enum values only, no descriptions
PROFILE_SCHEMA_HINT = {
    "team_name": "string",
    "team_type": ["platform_team", "product_team", "infrastructure_team", "security_team"],
    "stakeholder_role": ["engineering_lead", "product_owner", "cto_vp_engineering", "business_stakeholder"],
    "primary_goal": ["maximize_reliability", "maximize_delivery_speed", "reduce_operational_cost",
                     "improve_developer_wellbeing", "improve_security_posture", "increase_feature_adoption"],
    "secondary_goal": ["maximize_reliability", "maximize_delivery_speed", "reduce_operational_cost",
                       "improve_developer_wellbeing", "improve_security_posture", "increase_feature_adoption", None],
    "business_criticality": ["mission_critical", "business_important", "internal_tooling"],
    "decision_type": ["release_readiness", "incident_response", "sprint_planning",
                      "team_health_review", "stakeholder_reporting"],
    "time_horizon": ["immediate", "short_term", "strategic"],
    "data_sources": ["gitlab", "jira"],
    "sustainability_focus": "list of focus areas as strings",
    "declared_kpis": [],
    "confirmed": False,
}


async def run_call1(free_text: str, questions: list = None, answers: list = None) -> dict:
    """
    Call 1: interpret a free-text use-case description into a profile dict.
    If questions and answers are provided, incorporates them into the prompt.
    Returns an unconfirmed profile dict (not saved to DB).
    Retries once on invalid JSON. Raises ValueError if both attempts fail.
    """
    if questions and answers:
        questions_formatted = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        answers_formatted = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers))
        user_prompt = USER_PROMPT_CALL1_WITH_ANSWERS.format(
            schema_json=json.dumps(PROFILE_SCHEMA_HINT, indent=2),
            free_text=free_text,
            questions_formatted=questions_formatted,
            answers_formatted=answers_formatted,
        )
    else:
        user_prompt = USER_PROMPT_CALL1.format(
            schema_json=json.dumps(PROFILE_SCHEMA_HINT, indent=2),
            free_text=free_text,
        )

    for attempt in range(2):
        raw = await call_llm(SYSTEM_PROMPT_CALL1, user_prompt, max_tokens=1000)
        from backend.pipeline.llm_client import _strip_fences
        clean = _strip_fences(raw)
        try:
            data = json.loads(clean)
            # Ensure required defaults
            data.setdefault("declared_kpis", [])
            data.setdefault("confirmed", False)
            data.setdefault("data_sources", [])
            data.setdefault("sustainability_focus", [])
            data.setdefault("data_source_config", {
                "gitlab_base_url": "https://gitlab.com",
                "gitlab_project_ids": [],
                "jira_base_url": None,
                "jira_project_keys": [],
            })
            return data
        except json.JSONDecodeError as e:
            if attempt == 1:
                logger.error("Call 1 returned invalid JSON after retry: %s\nRaw: %s", e, raw)
                raise ValueError("Call 1 returned invalid JSON after retry")
            logger.warning("Call 1 JSON parse failed on attempt 1, retrying")


async def run_call1a(free_text: str) -> dict:
    """
    Call 1a: return clarifying questions and a partial profile from a free-text description.
    Returns {"questions": [...], "partial_profile": {...}}.
    Retries once on invalid JSON. Raises ValueError if both attempts fail.
    """
    user_prompt = USER_PROMPT_CALL1A.format(
        schema_json=json.dumps(PROFILE_SCHEMA_HINT, indent=2),
        free_text=free_text,
    )

    for attempt in range(2):
        raw = await call_llm(SYSTEM_PROMPT_CALL1A, user_prompt, max_tokens=1500)
        from backend.pipeline.llm_client import _strip_fences
        clean = _strip_fences(raw)
        try:
            data = json.loads(clean)
            if "questions" not in data or "partial_profile" not in data:
                raise ValueError("Missing required keys: questions and partial_profile")
            # Ensure partial_profile has required defaults
            partial = data["partial_profile"]
            partial.setdefault("declared_kpis", [])
            partial.setdefault("confirmed", False)
            partial.setdefault("data_sources", [])
            partial.setdefault("sustainability_focus", [])
            partial.setdefault("data_source_config", {
                "gitlab_base_url": "https://gitlab.com",
                "gitlab_project_ids": [],
                "jira_base_url": None,
                "jira_project_keys": [],
            })
            return data
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 1:
                logger.error("Call 1a returned invalid JSON after retry: %s\nRaw: %s", e, raw)
                raise ValueError("Call 1a returned invalid JSON after retry")
            logger.warning("Call 1a JSON parse failed on attempt 1, retrying")
