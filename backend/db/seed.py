"""
Step 13 — Mock data seed script.
Populates the database with synthetic data for a fictional team, enabling
thesis evaluation and demos without live API credentials.
"""

import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.db.models import ComputedMetric, ManualMetric, Profile, RawEvent

# Rolling window of synthetic commit/pipeline/MR events, ending "today" —
# feeds /api/metrics/{id}/event-series (the Trends page charts), which reads
# directly from raw_events and has no other source for the seed profile.
EVENT_WINDOW_DAYS = 84
SEED_PROJECT_ID = "seed-project"

# ---------------------------------------------------------------------------
# Seed data (Section 15)
# ---------------------------------------------------------------------------

SEED_PROFILE = {
    "id": "seed-profile-001",
    "team_name": "Platform Engineering Team Alpha",
    "team_type": "platform_team",
    "stakeholder_role": "engineering_lead",
    "primary_goal": "maximize_reliability",
    "secondary_goal": "improve_developer_wellbeing",
    "business_criticality": "mission_critical",
    "decision_type": "release_readiness",
    "time_horizon": "short_term",
    "data_sources": ["gitlab", "jira"],
    "sustainability_focus": ["developer_wellbeing", "cognitive_load"],
    "declared_kpis": [
        {
            "name": "System uptime target",
            "value": 99.9,
            "unit": "%",
            "threshold_type": "minimum",
            "business_impact": "Each hour of downtime results in contract penalty and customer churn risk",
        }
    ],
    "data_source_config": {
        "gitlab_base_url": "https://gitlab.com",
        "gitlab_project_ids": [],
        "jira_base_url": None,
        "jira_project_keys": [],
    },
    "confirmed": True,
}

# Intentionally degrading values — produces rich reasoning output
# Expected: overall_health=red, speed_stability conflict HIGH,
# throughput_sustainability conflict CRITICAL, BUR sustainability flag breach
SEED_METRICS = [
    {"metric_code": "CFR",  "current_value": 0.22, "previous_value": 0.14, "unit": "%",           "period_days": 14},
    {"metric_code": "DF",   "current_value": 3.2,  "previous_value": 4.1,  "unit": "deployments", "period_days": 14},
    {"metric_code": "MTTR", "current_value": 38.0, "previous_value": 22.0, "unit": "hours",       "period_days": 14},
    {"metric_code": "LTfC", "current_value": 31.0, "previous_value": 28.0, "unit": "hours",       "period_days": 14},
    {"metric_code": "PRCT", "current_value": 52.0, "previous_value": 44.0, "unit": "hours",       "period_days": 14},
    {"metric_code": "PRSi", "current_value": 620,  "previous_value": 410,  "unit": "lines",       "period_days": 14},
    {"metric_code": "TWiP", "current_value": 9,    "previous_value": 6,    "unit": "issues",      "period_days": 14},
    {"metric_code": "BUR",  "current_value": 28.0, "previous_value": 15.0, "unit": "%",            "period_days": 14},
    {"metric_code": "CQI",  "current_value": 78.0, "previous_value": 86.0, "unit": "%",            "period_days": 14},
    {"metric_code": "MIC",  "current_value": 11,   "previous_value": 7,    "unit": "issues",       "period_days": 14},
    # New metrics (Change 5)
    {"metric_code": "BF",   "current_value": 58.0, "previous_value": 45.0, "unit": "%",            "period_days": 14},
    {"metric_code": "BLDS", "current_value": 87.0, "previous_value": 102.0,"unit": "builds",       "period_days": 14},
    {"metric_code": "PR",   "current_value": 24.0, "previous_value": 31.0, "unit": "pull_requests","period_days": 14},
]

# Historical seed data — 8 weekly snapshots going back from 2026-03-19 (week before today)
# Used to populate the /history endpoint for trend charts.
SEED_HISTORY_TIMESTAMPS = [
    "2026-01-29T00:00:00Z",  # 8 weeks ago
    "2026-02-05T00:00:00Z",  # 7 weeks ago
    "2026-02-12T00:00:00Z",  # 6 weeks ago
    "2026-02-19T00:00:00Z",  # 5 weeks ago
    "2026-02-26T00:00:00Z",  # 4 weeks ago
    "2026-03-05T00:00:00Z",  # 3 weeks ago
    "2026-03-12T00:00:00Z",  # 2 weeks ago
    "2026-03-19T00:00:00Z",  # 1 week ago
]

# Values shown oldest → newest; CFR/BUR/MIC/BF degrade, DF/BLDS stable
SEED_HISTORY_VALUES: dict[str, dict] = {
    "CFR":  {"values": [0.08, 0.09, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20], "unit": "%",             "period_days": 7},
    "DF":   {"values": [4.0,  3.8,  4.2,  3.7,  4.1,  3.9,  3.6,  3.8],  "unit": "deployments",  "period_days": 7},
    "MTTR": {"values": [16.0, 18.0, 20.0, 23.0, 26.0, 30.0, 33.0, 36.0], "unit": "hours",        "period_days": 7},
    "BUR":  {"values": [6.0,  8.0,  10.0, 13.0, 16.0, 20.0, 24.0, 26.0], "unit": "%",             "period_days": 7},
    "MIC":  {"values": [3.0,  4.0,  4.0,  5.0,  6.0,  7.0,  8.0,  10.0], "unit": "issues",       "period_days": 7},
    "BF":   {"values": [35.0, 38.0, 40.0, 43.0, 46.0, 50.0, 54.0, 56.0], "unit": "%",             "period_days": 7},
    "BLDS": {"values": [98.0, 102.0, 97.0, 100.0, 99.0, 96.0, 93.0, 91.0],"unit": "builds",      "period_days": 7},
}

# Manual metrics for UC1 selection (CSAT_MANUAL, SLA_MANUAL, DSAT_MANUAL)
# Also intentionally degrading
SEED_MANUAL_METRICS = [
    {"metric_code": "CSAT_MANUAL",  "current_value": 7.2,  "previous_value": 8.1,  "unit": "score"},
    {"metric_code": "SLA_MANUAL",   "current_value": 99.1, "previous_value": 99.8, "unit": "%"},
    {"metric_code": "DSAT_MANUAL",  "current_value": 5.8,  "previous_value": 7.2,  "unit": "score"},
]


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------

def _seed_raw_events(db: Session, now_iso: str) -> None:
    """Synthetic commit/pipeline/MR events over a rolling window ending today.
    Deterministic (fixed seed) so re-seeding produces a stable-looking chart.
    """
    rng = random.Random(42)
    now = datetime.now(timezone.utc)

    for days_ago in range(EVENT_WINDOW_DAYS, -1, -1):
        day = now - timedelta(days=days_ago)
        if day.weekday() >= 5:
            continue  # quiet weekends, matches a typical team's rhythm

        for i in range(rng.randint(2, 6)):
            ts = day.replace(hour=rng.randint(9, 18), minute=rng.randint(0, 59))
            db.add(RawEvent(
                profile_id=SEED_PROFILE["id"], source="gitlab", entity_type="commit",
                entity_id=f"seed-commit-{days_ago}-{i}", project_id=SEED_PROJECT_ID,
                timestamp=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                attributes=json.dumps({
                    "author_email": "dev@example.com",
                    "author_name": "Seed Dev",
                    "after_hours": False,
                }),
                ingested_at=now_iso,
            ))

        for i in range(rng.randint(1, 3)):
            ts = day.replace(hour=rng.randint(9, 18), minute=rng.randint(0, 59))
            status = "success" if rng.random() > 0.2 else "failed"
            db.add(RawEvent(
                profile_id=SEED_PROFILE["id"], source="gitlab", entity_type="pipeline",
                entity_id=f"seed-pipeline-{days_ago}-{i}", project_id=SEED_PROJECT_ID,
                timestamp=ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                attributes=json.dumps({"status": status, "ref": "main", "sha": f"sha{days_ago}{i}"}),
                ingested_at=now_iso,
            ))

        if day.weekday() == 0 and rng.random() > 0.3:
            merged_day = day + timedelta(days=rng.randint(1, 3))
            is_merged = merged_day <= now
            db.add(RawEvent(
                profile_id=SEED_PROFILE["id"], source="gitlab", entity_type="mr",
                entity_id=f"seed-mr-{days_ago}", project_id=SEED_PROJECT_ID,
                timestamp=day.strftime("%Y-%m-%dT%H:%M:%SZ"),
                attributes=json.dumps({
                    "merged_at": merged_day.strftime("%Y-%m-%dT%H:%M:%SZ") if is_merged else None,
                    "closed_at": None,
                    "state": "merged" if is_merged else "open",
                    "title": f"Seed MR {days_ago}",
                    "changes_count": rng.randint(20, 400),
                    "source_branch": f"feature/seed-{days_ago}",
                    "target_branch": "main",
                    "author_id": 1,
                }),
                ingested_at=now_iso,
            ))


def seed_database(db: Session) -> None:
    """Insert (or replace) seed profile and metrics into the database."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Upsert profile
    existing = db.query(Profile).filter(Profile.id == SEED_PROFILE["id"]).first()
    if existing:
        db.delete(existing)
        db.flush()

    profile = Profile(
        id=SEED_PROFILE["id"],
        team_name=SEED_PROFILE["team_name"],
        team_type=SEED_PROFILE["team_type"],
        stakeholder_role=SEED_PROFILE["stakeholder_role"],
        primary_goal=SEED_PROFILE["primary_goal"],
        secondary_goal=SEED_PROFILE["secondary_goal"],
        business_criticality=SEED_PROFILE["business_criticality"],
        decision_type=SEED_PROFILE["decision_type"],
        time_horizon=SEED_PROFILE["time_horizon"],
        data_sources=json.dumps(SEED_PROFILE["data_sources"]),
        sustainability_focus=json.dumps(SEED_PROFILE["sustainability_focus"]),
        declared_kpis=json.dumps(SEED_PROFILE["declared_kpis"]),
        data_source_config=json.dumps(SEED_PROFILE["data_source_config"]),
        confirmed=1,
        created_at=now,
    )
    db.add(profile)

    # Delete existing metrics/events for seed profile
    db.query(ComputedMetric).filter(ComputedMetric.profile_id == SEED_PROFILE["id"]).delete()
    db.query(ManualMetric).filter(ManualMetric.profile_id == SEED_PROFILE["id"]).delete()
    db.query(RawEvent).filter(RawEvent.profile_id == SEED_PROFILE["id"]).delete()
    db.flush()

    _seed_raw_events(db, now)

    # Insert computed metrics
    for m in SEED_METRICS:
        db.add(ComputedMetric(
            profile_id=SEED_PROFILE["id"],
            metric_code=m["metric_code"],
            current_value=m["current_value"],
            previous_value=m["previous_value"],
            unit=m["unit"],
            period_days=m["period_days"],
            computed_at=now,
        ))

    # Insert manual metrics
    for m in SEED_MANUAL_METRICS:
        db.add(ManualMetric(
            profile_id=SEED_PROFILE["id"],
            metric_code=m["metric_code"],
            current_value=m["current_value"],
            previous_value=m["previous_value"],
            unit=m["unit"],
            entered_at=now,
        ))

    # Insert 8-week historical data for trend charts (Change 5)
    for code, info in SEED_HISTORY_VALUES.items():
        for i, (ts, value) in enumerate(zip(SEED_HISTORY_TIMESTAMPS, info["values"])):
            db.add(ComputedMetric(
                profile_id=SEED_PROFILE["id"],
                metric_code=code,
                current_value=value,
                previous_value=info["values"][i - 1] if i > 0 else None,
                unit=info["unit"],
                period_days=info["period_days"],
                computed_at=ts,
            ))

    db.commit()
