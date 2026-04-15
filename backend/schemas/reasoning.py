from pydantic import BaseModel
from typing import List, Optional


class ThresholdAssessment(BaseModel):
    metric_code: str
    status: str
    current_value: float
    threshold_value: Optional[float]


class Conflict(BaseModel):
    metric_a: str
    metric_b: str
    conflict_type: str
    severity: str   # 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
    evidence: str


class Recommendation(BaseModel):
    code: str
    target_metrics: List[str]
    priority: str   # 'immediate' | 'this_sprint' | 'strategic'


class SustainabilityFlag(BaseModel):
    dimension: str  # 'individual' | 'technical'
    metric_code: str
    status: str
    consecutive_periods: int = 1


class ReasoningReport(BaseModel):
    profile_id: str
    snapshot_timestamp: str
    overall_health: str  # 'green' | 'amber' | 'red'
    threshold_assessments: List[ThresholdAssessment]
    conflicts: List[Conflict]
    recommendations: List[Recommendation]
    sustainability_flags: List[SustainabilityFlag]


class ExplanationSections(BaseModel):
    summary: str
    key_findings: str
    sustainability_note: str
    recommended_actions: str
    tradeoff_explanation: str


class ExplanationOutput(BaseModel):
    profile_id: str
    stakeholder_role: str
    sections: ExplanationSections
    generated_at: str
