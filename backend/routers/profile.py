import json
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import (
    ComputedMetric, Explanation, ManualMetric,
    Profile, RawEvent, ReasoningReport, Snapshot,
)
from backend.pipeline.call1_interpret import run_call1, run_call1a
from backend.schemas.profile import DataSourceConfig, ProfileCreate, ProfileResponse

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _orm_to_response(profile: Profile, last_analysis_at: str = None) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        team_name=profile.team_name,
        team_type=profile.team_type,
        stakeholder_role=profile.stakeholder_role,
        primary_goal=profile.primary_goal,
        secondary_goal=profile.secondary_goal,
        business_criticality=profile.business_criticality,
        decision_type=profile.decision_type,
        time_horizon=profile.time_horizon,
        data_sources=json.loads(profile.data_sources),
        sustainability_focus=json.loads(profile.sustainability_focus),
        declared_kpis=json.loads(profile.declared_kpis),
        data_source_config=DataSourceConfig(**json.loads(profile.data_source_config)),
        confirmed=bool(profile.confirmed),
        created_at=profile.created_at,
        last_analysis_at=last_analysis_at,
    )


from pydantic import BaseModel


class ClarifyBody(BaseModel):
    free_text: str


class InterpretBody(BaseModel):
    free_text: str
    questions: list = []
    answers: list = []


@router.post("/clarify")
async def clarify_profile(body: ClarifyBody):
    """Call 1a — return clarifying questions and partial profile from free-text."""
    try:
        result = await run_call1a(body.free_text)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail={"error": "LLM response invalid", "raw": str(e)})


@router.post("/interpret")
async def interpret_profile(body: InterpretBody):
    """Call 1 — interpret free-text description into an unconfirmed profile dict."""
    try:
        questions = body.questions if body.questions else None
        answers = body.answers if body.answers else None
        result = await run_call1(body.free_text, questions, answers)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail={"error": "LLM response invalid", "raw": str(e)})


@router.post("", response_model=ProfileResponse)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)):
    """Save a confirmed profile to the database."""
    profile_id = str(uuid.uuid4())
    profile = Profile(
        id=profile_id,
        team_name=body.team_name,
        team_type=body.team_type.value,
        stakeholder_role=body.stakeholder_role.value,
        primary_goal=body.primary_goal.value,
        secondary_goal=body.secondary_goal.value if body.secondary_goal else None,
        business_criticality=body.business_criticality.value,
        decision_type=body.decision_type.value,
        time_horizon=body.time_horizon.value,
        data_sources=json.dumps(body.data_sources),
        sustainability_focus=json.dumps(body.sustainability_focus),
        declared_kpis=json.dumps([kpi.model_dump() for kpi in body.declared_kpis]),
        data_source_config=json.dumps(body.data_source_config.model_dump()),
        confirmed=1 if body.confirmed else 0,
        created_at=_now_iso(),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _orm_to_response(profile)


@router.get("/all", response_model=List[ProfileResponse])
def list_profiles(db: Session = Depends(get_db)):
    """List all profiles with the most recent analysis timestamp."""
    profiles = db.query(Profile).order_by(Profile.created_at.desc()).all()
    result = []
    for p in profiles:
        latest = (
            db.query(ReasoningReport)
            .filter(ReasoningReport.profile_id == p.id)
            .order_by(ReasoningReport.created_at.desc())
            .first()
        )
        last_analysis_at = latest.created_at if latest else None
        result.append(_orm_to_response(p, last_analysis_at))
    return result


@router.post("/{profile_id}/confirm", response_model=ProfileResponse)
def confirm_profile(profile_id: str, db: Session = Depends(get_db)):
    """Set confirmed=true on an existing unconfirmed profile."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    profile.confirmed = 1
    db.commit()
    db.refresh(profile)
    return _orm_to_response(profile)


@router.delete("/{profile_id}")
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    """Delete a profile and all associated data."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")

    # Delete in FK-safe order
    db.query(Explanation).filter(Explanation.profile_id == profile_id).delete()
    db.query(ReasoningReport).filter(ReasoningReport.profile_id == profile_id).delete()
    db.query(Snapshot).filter(Snapshot.profile_id == profile_id).delete()
    db.query(ComputedMetric).filter(ComputedMetric.profile_id == profile_id).delete()
    db.query(ManualMetric).filter(ManualMetric.profile_id == profile_id).delete()
    db.query(RawEvent).filter(RawEvent.profile_id == profile_id).delete()
    db.query(Profile).filter(Profile.id == profile_id).delete()
    db.commit()

    return {"status": "deleted", "id": profile_id}


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    """Fetch a single profile by ID."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return _orm_to_response(profile)
