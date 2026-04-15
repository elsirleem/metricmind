import os
import json
import re
import logging
from backend.pipeline.llm_client import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_CALL0 = """
You are a project intelligence assistant for MetricMind,
an AI-supported decision intelligence system that bridges
three domains that are typically measured in isolation:
DevOps performance, business outcomes, and developer
sustainability.

The gap you help address: organisations track DevOps metrics,
business KPIs, and sustainability indicators separately with
no integration. Engineers like the ones on this project often
lack full visibility into what matters most — even experienced
engineers sometimes do not understand which metrics are most
critical for their specific project context.

Your task is to read recent project activity and cross-reference
it with the available metric catalog to identify the North Star
metrics — the most important signals — for this specific project.

A North Star metric set should:
- Be grounded in what the project actually does and cares about
- Cover all three dimensions: DevOps, Business, Sustainability
- Be small enough to focus attention (maximum 6 metrics)
- Be directly computable from the available data sources

Return a JSON object with exactly these keys:

project_summary: string
  3-4 sentences describing what the team has been working on,
  what their apparent priorities are, and what the project
  appears to do based on the activity patterns.

north_star_metrics: array of objects, maximum 6 items
  Ordered by importance — most critical first.
  Always include at least one sustainability metric.
  Always include at least one from each tier where possible.
  Each object:
  {
    "code": "metric code from catalog — must exist in catalog",
    "name": "metric name",
    "tier": "devops | business | sustainability",
    "why": "one sentence — why this is critical for THIS project",
    "evidence": "specific pattern from activity that supports this"
  }

inferred_concerns: array of strings, maximum 4 items
  Risks or concerns implied by the activity that metrics
  alone may not fully capture.

suggested_kpis: array of objects, maximum 3 items
  Business KPIs this team should consider declaring:
  {
    "name": "KPI name",
    "why": "why this matters for this specific project"
  }

business_context: string
  1-2 sentences on what business outcomes this technical
  work appears to be serving.

confidence: "LOW" | "MEDIUM" | "HIGH"
  LOW = fewer than 10 activity items available
  MEDIUM = 10-25 activity items
  HIGH = 25+ activity items

Rules:
- Only recommend metrics that exist in the provided catalog
- Base ALL inferences on actual activity provided
- Do not invent specifics not in the data
- If data is sparse, acknowledge this honestly in summary
- Return only valid JSON — no markdown fences, no preamble
"""

USER_PROMPT_CALL0 = """
Recent commit messages (last 30):
{commit_messages}

Recent merge request titles and descriptions (last 20):
{mr_summaries}

Recent Jira ticket titles (if available):
{issue_summaries}

Available metric catalog:
{catalog_json}

Analyse this project and identify the North Star metrics.
Return JSON only.
"""


async def run_call0(
    commit_messages: list,
    mr_summaries: list,
    issue_summaries: list,
    catalog: dict
) -> dict:
    """
    Run Call 0 — Project Intelligence.
    Returns North Star metric recommendations from project activity.
    Does not require a profile — fully stateless.
    """
    commit_text = "\n".join([
        f"- {c}" for c in commit_messages[:30]
    ]) or "No commit messages available"

    mr_text = "\n".join([
        f"- {m}" for m in mr_summaries[:20]
    ]) or "No merge requests available"

    issue_text = "\n".join([
        f"- {i}" for i in issue_summaries[:20]
    ]) or "No Jira tickets available"

    # Pass only standard metrics to keep prompt focused
    catalog_summary = json.dumps([
        {
            "code": code,
            "name": info["name"],
            "tier": info["tier"],
            "data_source": info.get("source", info.get("data_source", "")),
            "formula": info.get("formula", "")
        }
        for code, info in catalog.items()
    ], indent=2)

    user_prompt = USER_PROMPT_CALL0.format(
        commit_messages=commit_text,
        mr_summaries=mr_text,
        issue_summaries=issue_text,
        catalog_json=catalog_summary
    )

    raw = await call_llm(
        SYSTEM_PROMPT_CALL0,
        user_prompt,
        max_tokens=2000
    )

    # Clean markdown fences
    clean = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    clean = re.sub(r'\n?```\s*$', '', clean).strip()

    try:
        result = json.loads(clean)
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Call 0 JSON parse failed: {e}\nRaw: {raw}")
        raise ValueError(f"Call 0 returned invalid JSON: {e}")
