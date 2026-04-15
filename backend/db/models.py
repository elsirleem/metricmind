from sqlalchemy import Column, Integer, Text, Float, ForeignKey
from backend.db.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Text, primary_key=True)                   # UUID string
    team_name = Column(Text, nullable=False)
    team_type = Column(Text, nullable=False)              # enum value as string
    stakeholder_role = Column(Text, nullable=False)
    primary_goal = Column(Text, nullable=False)
    secondary_goal = Column(Text, nullable=True)
    business_criticality = Column(Text, nullable=False)
    decision_type = Column(Text, nullable=False)
    time_horizon = Column(Text, nullable=False)
    data_sources = Column(Text, nullable=False)           # JSON array as string
    sustainability_focus = Column(Text, nullable=False)   # JSON array as string
    declared_kpis = Column(Text, nullable=False)          # JSON array as string
    data_source_config = Column(Text, nullable=False, default="{}")  # JSON object as string
    confirmed = Column(Integer, nullable=False, default=0)  # 0=false, 1=true
    created_at = Column(Text, nullable=False)             # ISO 8601


class RawEvent(Base):
    __tablename__ = "raw_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Text, ForeignKey("profiles.id"), nullable=False)
    source = Column(Text, nullable=False)       # 'gitlab' | 'jira'
    entity_type = Column(Text, nullable=False)  # 'commit' | 'pipeline' | 'mr' | 'issue'
    entity_id = Column(Text, nullable=False)
    project_id = Column(Text, nullable=False)   # GitLab project ID or Jira project key
    timestamp = Column(Text, nullable=False)    # ISO 8601
    attributes = Column(Text, nullable=False)   # full JSON blob as string
    ingested_at = Column(Text, nullable=False)  # ISO 8601


class ComputedMetric(Base):
    __tablename__ = "computed_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Text, ForeignKey("profiles.id"), nullable=False)
    metric_code = Column(Text, nullable=False)   # e.g. 'CFR', 'DF'
    current_value = Column(Float, nullable=True)
    previous_value = Column(Float, nullable=True)
    unit = Column(Text, nullable=False)
    period_days = Column(Integer, nullable=False)
    computed_at = Column(Text, nullable=False)   # ISO 8601


class ManualMetric(Base):
    __tablename__ = "manual_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Text, ForeignKey("profiles.id"), nullable=False)
    metric_code = Column(Text, nullable=False)
    current_value = Column(Float, nullable=False)
    previous_value = Column(Float, nullable=True)
    unit = Column(Text, nullable=False)
    entered_at = Column(Text, nullable=False)    # ISO 8601


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Text, ForeignKey("profiles.id"), nullable=False)
    snapshot_json = Column(Text, nullable=False)  # full MetricSnapshot JSON as string
    created_at = Column(Text, nullable=False)      # ISO 8601


class ReasoningReport(Base):
    __tablename__ = "reasoning_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Text, ForeignKey("profiles.id"), nullable=False)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False)
    report_json = Column(Text, nullable=False)    # full ReasoningReport JSON as string
    overall_health = Column(Text, nullable=False) # 'green' | 'amber' | 'red'
    created_at = Column(Text, nullable=False)     # ISO 8601


class Explanation(Base):
    __tablename__ = "explanations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Text, ForeignKey("profiles.id"), nullable=False)
    reasoning_report_id = Column(Integer, ForeignKey("reasoning_reports.id"), nullable=False)
    stakeholder_role = Column(Text, nullable=False)
    explanation_json = Column(Text, nullable=False)  # full ExplanationOutput JSON as string
    created_at = Column(Text, nullable=False)         # ISO 8601
