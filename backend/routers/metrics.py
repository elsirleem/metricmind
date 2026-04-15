import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import ComputedMetric, ManualMetric, Profile, RawEvent
from backend.ingestion.factory import get_git_adapter
from backend.ingestion.jira_connector import fetch_jira_data
from backend.metrics.catalog import EXTERNAL_DATA_METRICS, STANDARD_METRICS
from backend.metrics.computation import compute_all, parse_events
from backend.metrics.selection import select_metrics
from backend.pipeline.call15_rationale import run_call15
from backend.pipeline.call16_formula import run_call16
from backend.pipeline.snapshot import build_snapshot
from backend.schemas.profile import DataSourceConfig
from backend.schemas.snapshot import MetricRecord

router = APIRouter(tags=["metrics"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

@router.post("/api/ingest/{profile_id}")
async def ingest(
    profile_id: str,
    period_days: int = Query(default=14),
    db: Session = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    config_dict = json.loads(profile.data_source_config)
    config = DataSourceConfig(**config_dict)
    data_sources = json.loads(profile.data_sources)

    all_events: list[dict] = []
    errors: list[str] = []

    git_ids = config.git_project_ids  # property — returns the right list for the active platform
    if git_ids:
        try:
            since = (datetime.now(timezone.utc) - timedelta(days=period_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
            adapter = get_git_adapter(config.git_platform, config.git_base_url)
            failed_git = 0
            for pid in git_ids:
                try:
                    proj_events = await adapter.fetch_all(profile_id, pid, since)
                    all_events.extend(proj_events)
                except Exception as exc:
                    logger.warning("Git project %s failed (%s) — skipping", pid, exc)
                    failed_git += 1
            if failed_git == len(git_ids):
                errors.append("All configured git projects failed — check project IDs and credentials")
        except Exception as exc:
            errors.append(str(exc))
    elif any(s in data_sources for s in ("gitlab", "github")):
        raise HTTPException(
            status_code=400,
            detail={"error": f"No {config.git_platform} project IDs configured — add at least one in the profile data source settings"},
        )

    if "jira" in data_sources:
        if not config.jira_project_keys:
            logger.warning(
                "WARNING: No Jira project keys configured — "
                "skipping Jira ingestion. MTTR and MIC will return 0."
            )
        else:
            try:
                events = await fetch_jira_data(profile_id, period_days, config)
                all_events.extend(events)
            except RuntimeError as e:
                errors.append(str(e))

    if errors and not all_events:
        raise HTTPException(
            status_code=502,
            detail={"error": "All configured data sources failed — check project IDs and credentials"},
        )

    # Persist raw events
    now = _now_iso()
    for e in all_events:
        row = RawEvent(
            profile_id=e["profile_id"],
            source=e["source"],
            entity_type=e["entity_type"],
            entity_id=e["entity_id"],
            project_id=e["project_id"],
            timestamp=e["timestamp"],
            attributes=e["attributes"],
            ingested_at=e.get("ingested_at", now),
        )
        db.add(row)
    db.commit()

    return {"status": "ok", "events_ingested": len(all_events)}


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

@router.post("/api/metrics/compute/{profile_id}")
def compute_metrics(
    profile_id: str,
    period_days: int = Query(default=14),
    metric_codes: str = Query(default=""),
    db: Session = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    raw_events = (
        db.query(RawEvent)
        .filter(RawEvent.profile_id == profile_id)
        .all()
    )

    codes = [c.strip() for c in metric_codes.split(",") if c.strip()] if metric_codes else None
    results = compute_all(raw_events, period_days, codes=codes)

    if not results:
        import logging
        logging.getLogger(__name__).warning("compute_all returned 0 metrics for profile %s", profile_id)

    now = _now_iso()
    for r in results:
        row = ComputedMetric(
            profile_id=profile_id,
            metric_code=r["metric_code"],
            current_value=r["current_value"],
            previous_value=r["previous_value"],
            unit=r["unit"],
            period_days=period_days,
            computed_at=now,
        )
        db.add(row)
    db.commit()

    return {"status": "ok", "metrics_computed": len(results)}


# ---------------------------------------------------------------------------
# Metric catalog
# ---------------------------------------------------------------------------

@router.get("/api/metrics/catalog")
def get_metric_catalog():
    """Return all three categories from the metric catalog."""
    return {
        "standard": [
            {"code": code, **meta}
            for code, meta in STANDARD_METRICS.items()
        ],
        "external_required": [
            {"code": code, **meta}
            for code, meta in EXTERNAL_DATA_METRICS.items()
        ],
    }


# ---------------------------------------------------------------------------
# Metric prioritisation
# ---------------------------------------------------------------------------

class DeriveFormulaRequest(BaseModel):
    metric_code: str
    metric_name: str
    available_sources: List[str]


@router.post("/api/metrics/derive-formula")
async def derive_formula(body: DeriveFormulaRequest):
    """Call 16 — propose a computation formula for an AI-derivable metric."""
    try:
        result = await run_call16(body.metric_code, body.metric_name, body.available_sources)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail={"error": "LLM response invalid", "raw": str(e)})


@router.post("/api/metrics/prioritise/{profile_id}")
async def prioritise_metrics(profile_id: str, db: Session = Depends(get_db)):
    """
    Load the profile, run the selection matrix to get the initial metric subset,
    then call run_call15 to annotate each metric with a context-specific rationale.
    """
    import json as _json
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    profile_dict = {
        "primary_goal": profile.primary_goal,
        "decision_type": profile.decision_type,
        "business_criticality": profile.business_criticality,
        "stakeholder_role": profile.stakeholder_role,
    }

    selection = select_metrics(
        profile.primary_goal,
        profile.decision_type,
        profile.business_criticality,
    )

    # Build flat list with tier info
    all_selected: list[dict] = []
    priority = 1
    for tier, codes in selection.items():
        for code in codes:
            if code.endswith("_MANUAL"):
                continue
            catalog_entry = STANDARD_METRICS.get(code, {})
            all_selected.append({
                "code": code,
                "name": catalog_entry.get("name", code),
                "tier": tier,
                "priority": priority,
                "formula": catalog_entry.get("formula", ""),
                "data_source": catalog_entry.get("data_source", ""),
                "ai_derived": False,
                "source": "selection_matrix",
            })
            priority += 1

    # Annotate with rationales via LLM
    try:
        rationales = await run_call15(profile_dict, all_selected)
        rationale_map = {r["code"]: r["rationale"] for r in rationales if "code" in r}
    except Exception:
        rationale_map = {}

    for m in all_selected:
        m["rationale"] = rationale_map.get(m["code"], "Selected for this use case context.")

    return {"selected_metrics": all_selected}


# ---------------------------------------------------------------------------
# Fetch metrics (returns MetricRecord list via snapshot assembler)
# ---------------------------------------------------------------------------

@router.get("/api/metrics/{profile_id}", response_model=List[MetricRecord])
def get_metrics(
    profile_id: str,
    period_days: int = Query(default=14),
    db: Session = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    has_computed = db.query(ComputedMetric).filter(ComputedMetric.profile_id == profile_id).first()
    has_manual = db.query(ManualMetric).filter(ManualMetric.profile_id == profile_id).first()

    if not has_computed and not has_manual:
        raise HTTPException(
            status_code=404,
            detail={"error": "No metrics found — run ingestion and computation first"},
        )

    snapshot = build_snapshot(profile_id, period_days, db)
    return snapshot.metrics


# ---------------------------------------------------------------------------
# Manual metrics
# ---------------------------------------------------------------------------

class ManualMetricInput(BaseModel):
    metric_code: str
    current_value: float
    previous_value: Optional[float] = None
    unit: str


class ManualMetricResponse(BaseModel):
    id: int
    metric_code: str
    current_value: float
    previous_value: Optional[float]
    unit: str
    entered_at: str


@router.post("/api/metrics/manual/{profile_id}")
def save_manual_metrics(
    profile_id: str,
    body: List[ManualMetricInput],
    db: Session = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    now = _now_iso()
    for item in body:
        row = ManualMetric(
            profile_id=profile_id,
            metric_code=item.metric_code,
            current_value=item.current_value,
            previous_value=item.previous_value,
            unit=item.unit,
            entered_at=now,
        )
        db.add(row)
    db.commit()

    return {"status": "ok", "saved": len(body)}


@router.get("/api/metrics/manual/{profile_id}", response_model=List[ManualMetricResponse])
def get_manual_metrics(profile_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(ManualMetric)
        .filter(ManualMetric.profile_id == profile_id)
        .order_by(ManualMetric.entered_at.desc())
        .all()
    )
    return [
        ManualMetricResponse(
            id=r.id,
            metric_code=r.metric_code,
            current_value=r.current_value,
            previous_value=r.previous_value,
            unit=r.unit,
            entered_at=r.entered_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Metric history (Change 4)
# ---------------------------------------------------------------------------

@router.get("/api/metrics/{profile_id}/history")
def get_metric_history(
    profile_id: str,
    metric_codes: str = Query(default=""),
    days: int = Query(default=30),
    db: Session = Depends(get_db),
):
    """
    Return time-series history for one or more metric codes.
    Reads from computed_metrics, groups by date, keeps the most recent value
    when multiple rows share the same date.
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    codes = [c.strip() for c in metric_codes.split(",") if c.strip()] if metric_codes else []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    query = (
        db.query(ComputedMetric)
        .filter(
            ComputedMetric.profile_id == profile_id,
            ComputedMetric.computed_at >= cutoff,
        )
        .order_by(ComputedMetric.metric_code, ComputedMetric.computed_at.desc())
    )
    if codes:
        query = query.filter(ComputedMetric.metric_code.in_(codes))

    rows = query.all()

    # Group by code → date → most-recent value (rows are already desc by computed_at)
    by_code: dict[str, dict[str, float]] = {}
    for row in rows:
        code = row.metric_code
        date_str = row.computed_at[:10]  # "YYYY-MM-DD"
        if code not in by_code:
            by_code[code] = {}
        if date_str not in by_code[code]:  # first occurrence = most recent for that date
            by_code[code][date_str] = row.current_value

    result = [
        {
            "metric_code": code,
            "series": [
                {"date": d, "value": v}
                for d, v in sorted(date_values.items())
            ],
        }
        for code, date_values in by_code.items()
    ]

    return result
