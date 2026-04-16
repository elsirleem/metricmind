import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, Depends, HTTPException, Query
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
from backend.schemas.time_window import TimeWindow, get_ingest_since, resolve_time_window

router = APIRouter(tags=["metrics"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class IngestRequest(BaseModel):
    time_window: Optional[TimeWindow] = None


class ComputeRequest(BaseModel):
    time_window: Optional[TimeWindow] = None
    metric_codes: Optional[str] = None


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

@router.post("/api/ingest/{profile_id}")
async def ingest(
    profile_id: str,
    body: IngestRequest = Body(default=IngestRequest()),
    period_days: int = Query(default=30),
    db: Session = Depends(get_db),
):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    config_dict = json.loads(profile.data_source_config)
    config = DataSourceConfig(**config_dict)
    data_sources = json.loads(profile.data_sources)

    # Resolve fetch window
    if body.time_window:
        fetch_since_dt = get_ingest_since(body.time_window)
    else:
        # Fallback: fetch 2× period_days to cover both current and previous periods
        fetch_since_dt = datetime.now(timezone.utc) - timedelta(days=period_days * 2)
    since = fetch_since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    since_date = fetch_since_dt.strftime("%Y-%m-%d")
    until_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_events: list[dict] = []
    errors: list[str] = []

    git_ids = config.git_project_ids  # property — returns the right list for the active platform
    if git_ids:
        try:
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
                events = await fetch_jira_data(profile_id, config, since_date, until_date)
                all_events.extend(events)
            except RuntimeError as e:
                errors.append(str(e))

    if errors and not all_events:
        raise HTTPException(
            status_code=502,
            detail={"error": "All configured data sources failed — check project IDs and credentials"},
        )

    # Replace raw events for this profile (clean re-ingest)
    db.query(RawEvent).filter(RawEvent.profile_id == profile_id).delete()

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
    body: ComputeRequest = Body(default=ComputeRequest()),
    period_days: int = Query(default=30),
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

    # Resolve date ranges — use project_start from earliest raw event for full_history
    if body.time_window:
        project_start = None
        if body.time_window.mode == "full_history" and raw_events:
            timestamps = [e.timestamp for e in raw_events if e.timestamp]
            if timestamps:
                earliest_iso = min(timestamps)
                try:
                    project_start = datetime.fromisoformat(earliest_iso.replace("Z", "+00:00"))
                except Exception:
                    pass
        c_start, c_end, p_start, p_end = resolve_time_window(body.time_window, project_start)
    else:
        # Fallback to period_days
        now = datetime.now(timezone.utc)
        c_end = now
        c_start = now - timedelta(days=period_days)
        p_end = c_start
        p_start = c_start - timedelta(days=period_days)

    effective_period_days = max(1, int((c_end - c_start).days))
    codes_list = [c.strip() for c in (body.metric_codes or metric_codes).split(",") if c.strip()] or None
    results = compute_all(raw_events, c_start, c_end, p_start, p_end, codes=codes_list)

    if not results:
        logger.warning("compute_all returned 0 metrics for profile %s", profile_id)

    now = _now_iso()
    for r in results:
        row = ComputedMetric(
            profile_id=profile_id,
            metric_code=r["metric_code"],
            current_value=r["current_value"],
            previous_value=r["previous_value"],
            unit=r["unit"],
            period_days=effective_period_days,
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


# ---------------------------------------------------------------------------
# Raw event time series (for Trends charts — works from the first ingest)
# ---------------------------------------------------------------------------

@router.get("/api/metrics/{profile_id}/event-series")
def get_event_series(
    profile_id: str,
    days: int = Query(default=90),
    db: Session = Depends(get_db),
):
    """
    Return daily event counts grouped by entity type.
    Unlike /history (which requires multiple compute runs), this reads
    directly from raw_events and works after a single ingest.

    Response shape:
      commits:   [{date, count}]
      pipelines: [{date, success, failed, other}]
      mrs:       [{date, opened, merged, closed}]
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw_events = (
        db.query(RawEvent)
        .filter(
            RawEvent.profile_id == profile_id,
            RawEvent.timestamp >= cutoff,
        )
        .all()
    )

    commits_by_day: dict[str, int] = {}
    pipelines_by_day: dict[str, dict[str, int]] = {}
    mrs_by_day: dict[str, dict[str, int]] = {}

    for event in raw_events:
        ts = event.timestamp
        if not ts or len(ts) < 10:
            continue
        day = ts[:10]  # YYYY-MM-DD

        if event.entity_type == "commit":
            commits_by_day[day] = commits_by_day.get(day, 0) + 1

        elif event.entity_type == "pipeline":
            if day not in pipelines_by_day:
                pipelines_by_day[day] = {"success": 0, "failed": 0, "other": 0}
            try:
                attrs = json.loads(event.attributes) if isinstance(event.attributes, str) else {}
            except Exception:
                attrs = {}
            status = attrs.get("status", "")
            if status == "success":
                pipelines_by_day[day]["success"] += 1
            elif status in ("failed", "failure"):
                pipelines_by_day[day]["failed"] += 1
            else:
                pipelines_by_day[day]["other"] += 1

        elif event.entity_type == "mr":
            if day not in mrs_by_day:
                mrs_by_day[day] = {"opened": 0, "merged": 0, "closed": 0}
            try:
                attrs = json.loads(event.attributes) if isinstance(event.attributes, str) else {}
            except Exception:
                attrs = {}
            state = attrs.get("state", "open")
            if state == "merged":
                # Use merged_at date when available so bar lands on the right day
                merged_at = attrs.get("merged_at")
                merge_day = merged_at[:10] if merged_at and len(merged_at) >= 10 else day
                if merge_day not in mrs_by_day:
                    mrs_by_day[merge_day] = {"opened": 0, "merged": 0, "closed": 0}
                mrs_by_day[merge_day]["merged"] += 1
            elif state == "closed":
                mrs_by_day[day]["closed"] += 1
            else:
                mrs_by_day[day]["opened"] += 1

    return {
        "commits": [
            {"date": d, "count": c}
            for d, c in sorted(commits_by_day.items())
        ],
        "pipelines": [
            {"date": d, **v}
            for d, v in sorted(pipelines_by_day.items())
        ],
        "mrs": [
            {"date": d, **v}
            for d, v in sorted(mrs_by_day.items())
        ],
    }
