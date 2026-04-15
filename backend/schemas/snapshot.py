from pydantic import BaseModel
from typing import List, Optional


class MetricRecord(BaseModel):
    code: str
    name: str
    current_value: float
    previous_value: Optional[float] = None
    unit: str
    trend: str             # 'improving' | 'stable' | 'degrading'
    threshold_status: str  # 'within' | 'warning' | 'breach'
    threshold_value: Optional[float] = None
    threshold_source: str  # 'declared' | 'dora_benchmark' | 'periodic_system'
    group: str
    tier: str              # 'devops' | 'business' | 'sustainability'
    sustainability_dimension: Optional[str] = None  # 'individual' | 'technical'
    source: str


class MetricSnapshot(BaseModel):
    profile_id: str
    snapshot_timestamp: str
    period_days: int
    metrics: List[MetricRecord]
    declared_kpis: list = []
