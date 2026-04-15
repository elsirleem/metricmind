# MetricMind — Product Requirements Document
**Version:** 0.2 (MVP / Thesis Prototype)
**Status:** Active
**Last updated:** 2026-03

---

## 1. Overview

MetricMind is an AI-supported decision intelligence system that integrates DevOps, business, and sustainability metrics into a unified reasoning pipeline. It enables engineering leads, product owners, and technical stakeholders to understand cross-metric trade-offs and receive stakeholder-appropriate recommendations — going beyond traditional dashboards that display data without reasoning.

This document is written for an AI coding agent. Every section is intended to be directly implementable without ambiguity. Read the entire document before writing any code.

### 1.1 What This System Does
- Accepts a structured use-case profile declared by a stakeholder via an onboarding wizard
- Ingests DevOps metrics from GitLab and Jira REST APIs
- Computes metrics deterministically using defined formulas — no LLM involvement in computation
- Selects a relevant metric subset from a predefined selection matrix based on the profile
- Assembles a structured metric snapshot and passes it to a three-call LLM reasoning pipeline
- Returns stakeholder-adapted explanations, trade-off analysis, and prioritised recommendations

### 1.2 What This System Does NOT Do
- Does not make autonomous decisions or take automated actions
- Does not infer use-case from data — profile is always human-declared and confirmed
- Does not compute metrics inside the LLM — all computation is deterministic
- Does not support real-time streaming (periodic ingestion only)
- Does not cover environmental sustainability metrics
- Does not support multi-tenant or production-grade authentication
- Does not deploy to cloud infrastructure — runs locally only

### 1.3 Build Order for the Agent
Build in this exact sequence to validate core functionality early:

1. Database models and migrations
2. Pydantic schemas
3. Metric catalog (catalog.py)
4. Ingestion service (GitLab + Jira connectors)
5. Metric computation service
6. Metric selection engine
7. Threshold checker
8. Snapshot assembler
9. LLM Call 2 — trade-off reasoning (most critical — validate first)
10. LLM Call 1a — clarification questions
11. LLM Call 1b — profile population with answers
12. LLM Call 1.5 — metric rationale generation
13. LLM Call 1.6 — AI formula derivation
14. LLM Call 3 — explanation generation
15. FastAPI routers and endpoints
16. Next.js frontend pages
17. Mock data seed script

---

## 2. Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Backend | Python, FastAPI | 3.11+, 0.110+ |
| Frontend | React, Next.js (App Router) | 18+, 14+ |
| Database | SQLite via SQLAlchemy ORM | latest |
| LLM API | Anthropic Claude (evaluation) / Google Gemini (development) | `claude-sonnet-4-6` / `gemini-1.5-pro` |
| LLM client | `anthropic` + `google-generativeai` Python SDKs | latest |
| Data validation | Pydantic | v2 |
| HTTP client | `httpx` (async) | latest |
| Environment | `python-dotenv` | latest |
| Frontend HTTP | `axios` or native `fetch` | — |
| Styling | Tailwind CSS | 3+ |

---

## 3. Repository Structure

```
metricmind/
├── backend/
│   ├── main.py
│   ├── db/
│   │   ├── models.py
│   │   ├── database.py
│   │   └── seed.py               # Mock data seeder
│   ├── ingestion/
│   │   ├── gitlab_connector.py
│   │   ├── jira_connector.py
│   │   └── normaliser.py
│   ├── metrics/
│   │   ├── computation.py
│   │   ├── selection.py
│   │   ├── threshold.py
│   │   └── catalog.py           # Full Periodic System metric catalog (3 categories)
│   ├── pipeline/
│   │   ├── snapshot.py
│   │   ├── call1_interpret.py
│   │   ├── call2_reason.py
│   │   └── call3_explain.py
│   ├── routers/
│   │   ├── profile.py
│   │   ├── metrics.py
│   │   └── intelligence.py
│   └── schemas/
│       ├── profile.py
│       ├── snapshot.py
│       └── reasoning.py
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── onboarding/page.tsx
│   │   ├── dashboard/page.tsx
│   │   └── intelligence/page.tsx
│   ├── components/
│   │   ├── MetricCard.tsx          # Supports ai_derived badge
│   │   ├── TradeoffPanel.tsx
│   │   ├── RecommendationPanel.tsx
│   │   ├── SustainabilityNote.tsx
│   │   ├── ProfileWizard.tsx       # 6-step wizard with interactive Call 1
│   │   └── CatalogBrowser.tsx      # Modal catalog with AI formula derivation
│   └── lib/
│       └── api.ts
├── .env.example
├── requirements.txt          # see Section 19
├── package.json              # see Section 19
└── PRD.md
```

---

## 4. Environment Variables

```bash
# .env.example — copy to .env and fill in values
ANTHROPIC_API_KEY=your_key_here

# GitLab — personal access token with read_api scope
# Credentials only — project IDs and base URLs are declared per profile in the UI
GITLAB_TOKEN=your_token_here

# Jira — API token from id.atlassian.net
# Credentials only — project keys and base URLs are declared per profile in the UI
JIRA_EMAIL=your_email@example.com
JIRA_TOKEN=your_token_here

# Database
DATABASE_URL=sqlite:///./metricmind.db

# Frontend (Next.js)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 5. Database Schema

All tables use SQLite via SQLAlchemy ORM. Define all models in `backend/db/models.py`. Use `Integer` primary keys with autoincrement for simplicity. Store all timestamps as ISO 8601 strings.

### Table: `manual_metrics`
```sql
CREATE TABLE manual_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id      TEXT NOT NULL,
    metric_code     TEXT NOT NULL,
    current_value   REAL NOT NULL,
    previous_value  REAL,
    unit            TEXT NOT NULL,
    entered_at      TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);
```

### Table: `raw_events`
```sql
CREATE TABLE raw_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id   TEXT NOT NULL,
    source       TEXT NOT NULL,            -- 'gitlab' | 'jira'
    entity_type  TEXT NOT NULL,            -- 'commit' | 'pipeline' | 'mr' | 'issue'
    entity_id    TEXT NOT NULL,
    project_id   TEXT NOT NULL,            -- GitLab project ID or Jira project key
    timestamp    TEXT NOT NULL,
    attributes   TEXT NOT NULL,            -- full JSON blob as string
    ingested_at  TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);
```
```sql
CREATE TABLE profiles (
    id          TEXT PRIMARY KEY,          -- UUID string
    team_name   TEXT NOT NULL,
    team_type   TEXT NOT NULL,             -- enum value as string
    stakeholder_role TEXT NOT NULL,
    primary_goal TEXT NOT NULL,
    secondary_goal TEXT,
    business_criticality TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    time_horizon TEXT NOT NULL,
    data_sources TEXT NOT NULL,            -- JSON array as string
    sustainability_focus TEXT NOT NULL,    -- JSON array as string
    declared_kpis TEXT NOT NULL,           -- JSON array as string
    confirmed    INTEGER NOT NULL DEFAULT 0, -- 0=false, 1=true
    created_at   TEXT NOT NULL             -- ISO 8601
);
```

### Table: `raw_events`
```sql
CREATE TABLE raw_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id   TEXT NOT NULL,
    source       TEXT NOT NULL,            -- 'gitlab' | 'jira'
    entity_type  TEXT NOT NULL,            -- 'commit' | 'pipeline' | 'mr' | 'issue'
    entity_id    TEXT NOT NULL,
    timestamp    TEXT NOT NULL,            -- ISO 8601
    attributes   TEXT NOT NULL,            -- full JSON blob as string
    ingested_at  TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);
```

### Table: `computed_metrics`
```sql
CREATE TABLE computed_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id      TEXT NOT NULL,
    metric_code     TEXT NOT NULL,         -- e.g. 'CFR', 'DF'
    current_value   REAL,
    previous_value  REAL,
    unit            TEXT NOT NULL,
    period_days     INTEGER NOT NULL,
    computed_at     TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);
```

### Table: `snapshots`
```sql
CREATE TABLE snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id      TEXT NOT NULL,
    snapshot_json   TEXT NOT NULL,         -- full MetricSnapshot JSON as string
    created_at      TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id)
);
```

### Table: `reasoning_reports`
```sql
CREATE TABLE reasoning_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id      TEXT NOT NULL,
    snapshot_id     INTEGER NOT NULL,
    report_json     TEXT NOT NULL,         -- full ReasoningReport JSON as string
    overall_health  TEXT NOT NULL,         -- 'green' | 'amber' | 'red'
    created_at      TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
);
```

### Table: `explanations`
```sql
CREATE TABLE explanations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id          TEXT NOT NULL,
    reasoning_report_id INTEGER NOT NULL,
    stakeholder_role    TEXT NOT NULL,
    explanation_json    TEXT NOT NULL,     -- full ExplanationOutput JSON as string
    created_at          TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id),
    FOREIGN KEY (reasoning_report_id) REFERENCES reasoning_reports(id)
);
```

---

## 6. Pydantic Schemas

Define in `backend/schemas/`. Use Pydantic v2 syntax.

### `schemas/profile.py`
```python
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class TeamType(str, Enum):
    platform_team = "platform_team"
    product_team = "product_team"
    infrastructure_team = "infrastructure_team"
    security_team = "security_team"

class StakeholderRole(str, Enum):
    engineering_lead = "engineering_lead"
    product_owner = "product_owner"
    cto_vp_engineering = "cto_vp_engineering"
    business_stakeholder = "business_stakeholder"

class PrimaryGoal(str, Enum):
    maximize_reliability = "maximize_reliability"
    maximize_delivery_speed = "maximize_delivery_speed"
    reduce_operational_cost = "reduce_operational_cost"
    improve_developer_wellbeing = "improve_developer_wellbeing"
    improve_security_posture = "improve_security_posture"
    increase_feature_adoption = "increase_feature_adoption"

class BusinessCriticality(str, Enum):
    mission_critical = "mission_critical"
    business_important = "business_important"
    internal_tooling = "internal_tooling"

class DecisionType(str, Enum):
    release_readiness = "release_readiness"
    incident_response = "incident_response"
    sprint_planning = "sprint_planning"
    team_health_review = "team_health_review"
    stakeholder_reporting = "stakeholder_reporting"

class TimeHorizon(str, Enum):
    immediate = "immediate"
    short_term = "short_term"
    strategic = "strategic"

class DeclaredKPI(BaseModel):
    name: str
    value: float
    unit: str
    threshold_type: str  # 'minimum' | 'maximum' | 'target'
    business_impact: str

class DataSourceConfig(BaseModel):
    gitlab_base_url: str = "https://gitlab.com"
    gitlab_project_ids: List[str] = []    # one or more numeric project IDs as strings
    jira_base_url: Optional[str] = None   # e.g. https://yourorg.atlassian.net
    jira_project_keys: List[str] = []     # one or more project keys e.g. ["PROJ", "CORE"]

class ProfileCreate(BaseModel):
    team_name: str
    team_type: TeamType
    stakeholder_role: StakeholderRole
    primary_goal: PrimaryGoal
    secondary_goal: Optional[PrimaryGoal] = None
    business_criticality: BusinessCriticality
    decision_type: DecisionType
    time_horizon: TimeHorizon
    data_sources: List[str]
    sustainability_focus: List[str]
    declared_kpis: List[DeclaredKPI] = []
    data_source_config: DataSourceConfig  # project IDs declared per profile
    confirmed: bool = False

class ProfileResponse(ProfileCreate):
    id: str
    created_at: str
```

### `schemas/snapshot.py`
```python
from pydantic import BaseModel
from typing import List, Optional

class MetricRecord(BaseModel):
    code: str
    name: str
    current_value: float
    previous_value: Optional[float] = None
    unit: str
    trend: str           # 'improving' | 'stable' | 'degrading'
    threshold_status: str  # 'within' | 'warning' | 'breach'
    threshold_value: Optional[float] = None
    threshold_source: str  # 'declared' | 'dora_benchmark' | 'periodic_system'
    group: str
    tier: str            # 'devops' | 'business' | 'sustainability'
    sustainability_dimension: Optional[str] = None  # 'individual' | 'technical'
    source: str

class MetricSnapshot(BaseModel):
    profile_id: str
    snapshot_timestamp: str
    period_days: int
    metrics: List[MetricRecord]
    declared_kpis: list = []
```

### `schemas/reasoning.py`
```python
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
```

---

## 7. GitLab API Field Mappings

Base URL pattern: `{profile.data_source_config.gitlab_base_url}/api/v4/projects/{project_id}`

The ingestion service loops over all `gitlab_project_ids` in the profile's `data_source_config`.
Each raw event record stores the originating `project_id` for downstream filtering.

```python
# Pseudocode for multi-project ingestion loop
async def fetch_gitlab_data(profile_id, period_days, config: DataSourceConfig):
    all_events = []
    for project_id in config.gitlab_project_ids:
        events = await fetch_single_gitlab_project(
            profile_id=profile_id,
            period_days=period_days,
            project_id=project_id,
            base_url=config.gitlab_base_url
        )
        all_events.extend(events)
    return all_events
```

### Pipelines — GET `/pipelines`
```
Query params: updated_after={ISO_DATE}, per_page=100
Fields to extract:
  entity_id    → pipeline["id"]
  timestamp    → pipeline["created_at"]
  status       → pipeline["status"]  # 'success' | 'failed' | 'canceled' | 'running'
  ref          → pipeline["ref"]     # branch name
  sha          → pipeline["sha"]

A pipeline is a "deployment" if: status == 'success' AND ref == 'main' (or 'master')
A pipeline is a "failure"     if: status == 'failed'
```

### Merge Requests — GET `/merge_requests`
```
Query params: state=all, updated_after={ISO_DATE}, per_page=100
Fields to extract:
  entity_id       → mr["iid"]
  timestamp       → mr["created_at"]
  merged_at       → mr["merged_at"]
  closed_at       → mr["closed_at"]
  state           → mr["state"]         # 'opened' | 'merged' | 'closed'
  additions       → mr["changes_count"] # use as proxy for PRSi if diff not available
  source_branch   → mr["source_branch"]
  target_branch   → mr["target_branch"]
  author_id       → mr["author"]["id"]
```

### Commits — GET `/repository/commits`
```
Query params: since={ISO_DATE}, per_page=100
Fields to extract:
  entity_id    → commit["id"]           # SHA
  timestamp    → commit["created_at"]
  author_email → commit["author_email"]
  author_name  → commit["author_name"]

After-hours detection (for BUR proxy):
  Parse commit["created_at"] as UTC datetime.
  after_hours = True if hour < 7 OR hour >= 20
```

---

## 8. Jira API Field Mappings

Base URL pattern: `{profile.data_source_config.jira_base_url}/rest/api/3`
Auth: Basic auth with `{JIRA_EMAIL}:{JIRA_TOKEN}` base64 encoded. Credentials from `.env` only.

The ingestion service loops over all `jira_project_keys` in the profile's `data_source_config`.

```python
# Pseudocode for multi-project ingestion loop
async def fetch_jira_data(profile_id, period_days, config: DataSourceConfig):
    all_events = []
    for project_key in config.jira_project_keys:
        events = await fetch_single_jira_project(
            profile_id=profile_id,
            period_days=period_days,
            project_key=project_key,
            base_url=config.jira_base_url
        )
        all_events.extend(events)
    return all_events
```

### Issues — POST `/search` (JQL)
```
JQL for incidents: project={KEY} AND issuetype in (Bug, Incident) AND created >= -{DAYS}d
JQL for all issues: project={KEY} AND created >= -{DAYS}d

Fields to extract:
  entity_id      → issue["key"]
  timestamp      → issue["fields"]["created"]
  resolved_at    → issue["fields"]["resolutiondate"]
  status         → issue["fields"]["status"]["name"]
  issue_type     → issue["fields"]["issuetype"]["name"]
  priority       → issue["fields"]["priority"]["name"]
  story_points   → issue["fields"]["story_points"] or customfield_10016

An issue is "in-progress" if status in ['In Progress', 'In Review', 'In Development']
An issue is "incident"    if issuetype in ['Bug', 'Incident', 'Service Request']
An issue is "resolved"    if resolutiondate is not None
```

---

## 9. Metric Computation Formulas

All functions live in `backend/metrics/computation.py`. Each function receives a list of normalised raw events and a `period_days` integer. All functions return a dict: `{"current": float, "previous": float, "unit": str}`.

For "previous" period: use the same window shifted back by `period_days`.

```python
def compute_cfr(events, period_days):
    """Change Failure Rate = failed pipelines / total pipelines"""
    # Filter pipelines in current period
    # current = count(status=='failed') / count(all pipelines)
    # unit = "%", multiply result by 100
    # If total == 0: return current=0.0

def compute_df(events, period_days):
    """Deployment Frequency = count of successful deployments to main"""
    # Filter pipelines: status=='success' AND ref in ['main','master']
    # current = count in period
    # unit = "deployments"

def compute_mttr(events, period_days):
    """Mean Time to Recover = avg hours from incident open to resolved"""
    # Filter Jira issues: issue_type in ['Bug','Incident'] AND resolved in period
    # For each: delta_hours = (resolved_at - created) in hours
    # current = mean(delta_hours)
    # unit = "hours"
    # If no resolved incidents: return current=0.0

def compute_ltfc(events, period_days):
    """Lead Time for Changes = avg hours from first commit on branch to MR merge"""
    # For each merged MR in period:
    #   Find earliest commit with matching source_branch
    #   delta = merged_at - earliest_commit_timestamp (hours)
    # current = mean(deltas)
    # unit = "hours"

def compute_prct(events, period_days):
    """Pull Request Cycle Time = avg hours from MR created to merged"""
    # Filter MRs: state=='merged' AND merged_at in period
    # delta = merged_at - created_at (hours)
    # current = mean(deltas)
    # unit = "hours"

def compute_prsi(events, period_days):
    """Pull Request Size = avg lines changed per merged MR"""
    # Filter MRs: state=='merged' AND merged_at in period
    # Use changes_count field as proxy
    # current = mean(changes_count)
    # unit = "lines"

def compute_twip(events, period_days):
    """Team Work in Progress = count of in-progress issues at snapshot time"""
    # Filter Jira issues: status in ['In Progress','In Review','In Development']
    # AND created <= now AND (resolved_at is None OR resolved_at > now)
    # current = count
    # unit = "issues"

def compute_bur(events, period_days):
    """Burnout Rate proxy = % of active engineers with >3 after-hours commits"""
    # Group commits by author_email
    # For each engineer: count commits where hour < 7 OR hour >= 20
    # bur_engineers = count(engineers where after_hours_commits > 3)
    # current = (bur_engineers / total_engineers) * 100
    # unit = "%"
    # If no commits: return 0.0

def compute_cqi(events, period_days):
    """Code Quality Index proxy = pipeline success rate"""
    # Same data as CFR but inverted
    # current = (successful_pipelines / total_pipelines) * 100
    # unit = "%"

def compute_mic(events, period_days):
    """Maintainability Issue Count = open bugs older than 14 days"""
    # Filter Jira: issuetype=='Bug' AND resolved_at is None
    # AND created < (now - 14 days)
    # current = count
    # unit = "issues"
```

---

## 10. Metric Selection Matrix

Implement in `backend/metrics/selection.py` as a Python dict lookup.
Key: `(primary_goal, decision_type, business_criticality)`
Value: `{"devops": [...], "business": [...], "sustainability": [...]}`

```python
SELECTION_MATRIX = {
    # UC1 — Release readiness, reliability focus, mission critical
    ("maximize_reliability", "release_readiness", "mission_critical"): {
        "devops":         ["CFR", "DF", "MTTR", "CQI"],
        "business":       ["CSAT_MANUAL", "SLA_MANUAL"],
        "sustainability": ["BUR", "DSAT_MANUAL", "MIC"]
    },

    # UC2 — Sprint planning, delivery speed focus
    ("maximize_delivery_speed", "sprint_planning", "business_important"): {
        "devops":         ["LTfC", "PRCT", "PRSi", "TWiP", "DF"],
        "business":       ["VEL_MANUAL", "WIV_MANUAL"],
        "sustainability": ["BUR", "MIC"]
    },

    # UC3 — Team health review, wellbeing focus
    ("improve_developer_wellbeing", "team_health_review", "business_important"): {
        "devops":         ["MTTR", "CFR", "PRCT"],
        "business":       ["GOAL_MANUAL"],
        "sustainability": ["BUR", "DSAT_MANUAL", "MIC"]
    },

    # UC4 — Stakeholder reporting, CTO audience
    ("maximize_reliability", "stakeholder_reporting", "mission_critical"): {
        "devops":         ["DF", "CFR", "MTTR", "LTfC"],
        "business":       ["CSAT_MANUAL", "SLA_MANUAL", "TCO_MANUAL"],
        "sustainability": ["DSAT_MANUAL", "BUR", "MIC"]
    },

    # UC5 — Security posture review
    ("improve_security_posture", "release_readiness", "mission_critical"): {
        "devops":         ["CFR", "CQI", "MIC", "PRCT"],
        "business":       ["SLA_MANUAL", "CSAT_MANUAL"],
        "sustainability": ["BUR", "MIC"]
    },
}

# Fallback for unrecognised profile combinations
DEFAULT_SELECTION = {
    "devops":         ["CFR", "DF", "MTTR", "LTfC"],
    "business":       ["CSAT_MANUAL"],
    "sustainability": ["BUR", "DSAT_MANUAL"]
}

# Metrics with suffix _MANUAL are not computed from source data.
# They are provided as declared_kpis in the profile or as manual input.
# The snapshot assembler should include them if present in declared_kpis,
# and skip them with a logged warning if absent.
```

---

## 11. Threshold Definitions

Implement in `backend/metrics/threshold.py`.

```python
# DORA benchmark thresholds (source: DORA State of DevOps report)
DORA_THRESHOLDS = {
    "CFR":  {"within": (0, 0.15),   "warning": (0.15, 0.30), "breach": (0.30, 1.0), "unit": "%"},
    "DF":   {"within": (1, 9999),   "warning": (0.5, 1),     "breach": (0, 0.5),    "unit": "deployments/day"},
    "MTTR": {"within": (0, 24),     "warning": (24, 168),    "breach": (168, 9999), "unit": "hours"},
    "LTfC": {"within": (0, 24),     "warning": (24, 168),    "breach": (168, 9999), "unit": "hours"},
}

# General thresholds for non-DORA metrics
GENERAL_THRESHOLDS = {
    "BUR":  {"within": (0, 10),   "warning": (10, 25),  "breach": (25, 100), "unit": "%"},
    "MIC":  {"within": (0, 5),    "warning": (5, 15),   "breach": (15, 9999),"unit": "issues"},
    "CQI":  {"within": (80, 100), "warning": (60, 80),  "breach": (0, 60),   "unit": "%"},
    "PRCT": {"within": (0, 48),   "warning": (48, 120), "breach": (120, 9999),"unit": "hours"},
    "PRSi": {"within": (0, 400),  "warning": (400, 800),"breach": (800, 9999),"unit": "lines"},
    "TWiP": {"within": (0, 5),    "warning": (5, 10),   "breach": (10, 9999), "unit": "issues"},
}

# Threshold check logic:
# 1. If metric is in profile.declared_kpis, use declared value + threshold_type
# 2. Else if metric is in DORA_THRESHOLDS, use DORA benchmark
# 3. Else if metric is in GENERAL_THRESHOLDS, use general benchmark
# 4. Else return status='within', threshold_value=None, source='none'
```

---

## 6. LLM Call Specifications

### 6.0 Call 1a — Clarification Questions
**File:** `backend/pipeline/call1_interpret.py`
**Trigger:** POST `/api/profile/clarify`
**Inputs:** Free-text use-case description
**Outputs:** `{"questions": [...], "partial_profile": {...}}`
**LLM:** `claude-sonnet-4-6` (or active provider), max_tokens=800

**Purpose:** Extract what can be determined with high confidence and
generate 2-3 targeted questions for what remains unclear. Runs before
full profile population to give the LLM richer context.

**System prompt:**
```
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
```

**Acceptance criteria:**
- Returns questions array with 2-3 items
- partial_profile contains correct values for determinable fields
- Questions are contextually relevant — not generic
- Fields the LLM is confident about are never asked again

### 6.1 Call 1b — Profile Population With Answers
**File:** `backend/pipeline/call1_interpret.py`
**Trigger:** POST `/api/profile/interpret`
**Inputs:** `{"free_text": "...", "questions": [...], "answers": [...]}`
**Outputs:** Fully populated profile JSON
**LLM:** active provider, max_tokens=1000

**Extended to accept questions and answers.** When provided, includes
them in the user prompt for richer context. When absent, uses original
single-turn behaviour unchanged.

**Acceptance criteria:**
- Profile populated with answers is more complete than without
- confirmed always returns false
- declared_kpis always returns []
- Null fields returned as null not omitted

### 6.2 Call 1.5 — Metric Rationale Generation
**File:** `backend/pipeline/call15_rationale.py`
**Trigger:** POST `/api/metrics/prioritise/{profile_id}`
**Inputs:** Confirmed profile JSON + selected metric codes list
**Outputs:** `[{"code": "...", "rationale": "..."}]`
**LLM:** active provider, max_tokens=800

**Purpose:** Generate one-sentence contextual rationale for each
selected metric explaining WHY it matters for the specific use case.
This makes the selection matrix transparent to the user.

**System prompt:**
```
You are explaining metric selections to a software engineering stakeholder.
Given a use case profile and selected metrics, write a one-sentence
rationale for each metric explaining WHY it matters for this context.

Rules:
- Each rationale must reference the stakeholder's stated goal or
  decision type specifically — not a generic description
- Maximum 20 words per rationale
- Plain language — no jargon or metric codes in rationale text
- Return JSON array: [{"code": "string", "rationale": "string"}]
- No markdown fences, no preamble
```

**Acceptance criteria:**
- Every selected metric code has a rationale
- Rationales reference the specific goal or decision type
- Each rationale is under 20 words

### 6.3 Call 1.6 — AI Formula Derivation
**File:** `backend/pipeline/call16_formula.py`
**Trigger:** POST `/api/metrics/derive-formula`
**Inputs:** `{"metric_code": "...", "metric_name": "...", "available_sources": [...]}`
**Outputs:** Formula proposal with confidence and research basis
**LLM:** active provider, max_tokens=600

**Purpose:** Propose a computation formula for metrics not in the
standard catalog. Grounds formula in research where possible.
Confidence level determines whether the metric should be used
in thesis evaluation.

**System prompt:**
```
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
```

**Acceptance criteria:**
- Returns all five required JSON keys
- Confidence is always one of HIGH/MEDIUM/LOW
- LOW confidence includes clear warning language
- Formula only references fields from available_sources

### LLM Provider Abstraction (`backend/pipeline/llm_client.py`)

All three call files import `call_llm` from this single module.
Switching providers requires only changing `LLM_PROVIDER` in `.env` — no code changes.

```python
import os
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
MAX_RETRIES = 2

async def call_llm(system_prompt: str, user_prompt: str,
                   max_tokens: int = 2000) -> str:
    """
    Single entry point for all LLM calls.
    Returns raw string response. Caller is responsible for JSON parsing.
    Retries once on failure before raising.
    """
    for attempt in range(MAX_RETRIES):
        try:
            if LLM_PROVIDER == "anthropic":
                return await _call_anthropic(system_prompt, user_prompt, max_tokens)
            elif LLM_PROVIDER == "gemini":
                return await _call_gemini(system_prompt, user_prompt, max_tokens)
            elif LLM_PROVIDER == "openai":
                return await _call_openai(system_prompt, user_prompt, max_tokens)
            else:
                raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
        except RateLimitError:
            wait = 2 ** attempt * 15   # 15s, then 30s
            logger.warning(f"Rate limit hit — waiting {wait}s before retry")
            await asyncio.sleep(wait)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
            await asyncio.sleep(2)
    raise RuntimeError("LLM call failed after all retries")


async def _call_anthropic(system_prompt: str, user_prompt: str,
                           max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return response.content[0].text


async def _call_gemini(system_prompt: str, user_prompt: str,
                        max_tokens: int) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        system_instruction=system_prompt
    )
    response = model.generate_content(
        user_prompt,
        generation_config=genai.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.1    # low temperature for consistent JSON output
        )
    )
    return response.text


async def _call_openai(system_prompt: str, user_prompt: str,
                        max_tokens: int) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response.choices[0].message.content


class RateLimitError(Exception):
    pass
```

**Usage in call files — all three calls follow this exact pattern:**
```python
from backend.pipeline.llm_client import call_llm

async def run_call2(profile: dict, snapshot: dict) -> dict:
    user_prompt = USER_PROMPT_CALL2.format(
        profile_json=json.dumps(profile, indent=2),
        snapshot_json=json.dumps(snapshot, indent=2)
    )
    raw = await call_llm(SYSTEM_PROMPT_CALL2, user_prompt, max_tokens=2000)

    # Strip markdown fences if model wraps JSON despite instructions
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    try:
        data = json.loads(clean)
        return ReasoningReport(**data).model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Call 2 response failed validation: {e}\nRaw: {raw}")
        raise ValueError(f"Call 2 returned invalid response: {e}")
```

**Note on temperature:** All LLM calls use `temperature=0.1` where the provider supports it.
Low temperature is critical for Call 2 — you need deterministic JSON structure, not creative variation.
Anthropic does not expose temperature in the same way — the default is acceptable.


**File:** `backend/pipeline/call1_interpret.py`
**Model:** `claude-sonnet-4-6`, `max_tokens=1000`

```python
SYSTEM_PROMPT_CALL1 = """
You are a DevOps metrics assistant helping configure a decision intelligence system.
Your only task is to map the user's description onto the provided JSON profile schema.

Rules:
- Only use values defined in the schema enums. Do not invent new field values.
- If a field cannot be determined from the description, set it to null.
- Return only valid JSON. No explanation, no preamble, no markdown fences.
- Always return declared_kpis as empty array [].
- Always set confirmed to false.
"""

USER_PROMPT_CALL1 = """
Profile schema (use only these enum values):
{schema_json}

Use case description:
"{free_text}"

Return the populated profile as JSON only.
"""
```

**Error handling:** If the response is not valid JSON, retry once. If retry fails, raise `ValueError("Call 1 returned invalid JSON after retry")`.

### 12.2 Call 2 — Trade-off Reasoning
**File:** `backend/pipeline/call2_reason.py`
**Model:** `claude-sonnet-4-6`, `max_tokens=2000`

```python
SYSTEM_PROMPT_CALL2 = """
You are a decision intelligence engine for software engineering teams.
You receive structured, pre-validated metric data. You do not compute metrics.

Analyse the snapshot and return a structured reasoning report as JSON.

Steps:
1. THRESHOLD ASSESSMENT — record threshold_status for each metric.
2. CONFLICT DETECTION — identify metric pairs in tension given stated goals.
   Conflict types: speed_stability | throughput_sustainability | cost_reliability | other
3. SEVERITY SCORING — assign LOW/MEDIUM/HIGH/CRITICAL based on:
   business_criticality (mission_critical raises severity by one level),
   threshold_status (breach = higher), trend (degrading = higher),
   declared business_impact strings if present.
4. RECOMMENDATIONS — for HIGH or CRITICAL conflicts only, pick ONE code from:
   reduce_deployment_pace | invest_in_test_coverage | address_technical_debt |
   review_team_capacity | escalate_to_stakeholder | accept_risk_with_mitigation |
   investigate_incident_pattern | reduce_work_in_progress
5. SUSTAINABILITY FLAGS — always check BUR, DSAT_MANUAL (individual dimension)
   and CQI, MIC (technical dimension). Flag any with warning or breach status.
6. OVERALL HEALTH — green if no HIGH/CRITICAL conflicts, amber if HIGH exists,
   red if CRITICAL exists or sustainability breach exists.

Return only valid JSON. No prose. No markdown fences.
"""

USER_PROMPT_CALL2 = """
Confirmed profile:
{profile_json}

Metric snapshot:
{snapshot_json}

Return the reasoning report as JSON only.
"""
```

**Error handling:** Parse response as JSON. Validate against `ReasoningReport` Pydantic model. If validation fails, log the raw response and raise `ValueError("Call 2 response failed schema validation")`.

### 12.3 Call 3 — Explanation Generation
**File:** `backend/pipeline/call3_explain.py`
**Model:** `claude-sonnet-4-6`, `max_tokens=2000`

```python
SYSTEM_PROMPT_CALL3 = """
You are a communication layer for a decision intelligence system.
Translate the reasoning report into a stakeholder-appropriate explanation.

Adapt to stakeholder_role:
- engineering_lead: use metric codes and values, explain root causes, be direct about severity.
- product_owner: frame as sprint/delivery risk, avoid deep technical detail.
- cto_vp_engineering: frame as business risk, reference declared KPI thresholds explicitly.
- business_stakeholder: no metric codes, plain language only, max 3 key points.

Return a JSON object with exactly these keys:
- summary: 2 sentences max, overall health and primary concern
- key_findings: markdown, one paragraph per HIGH/CRITICAL conflict only
- sustainability_note: markdown, always present. If no flags: confirm indicators are healthy.
- recommended_actions: markdown ordered list, highest priority first
- tradeoff_explanation: markdown, what happens if top recommendation is followed vs not

Rules:
- Do not invent data not present in the reasoning report.
- Do not soften CRITICAL severity findings.
- Never use metric codes when stakeholder_role is business_stakeholder.
- Return only valid JSON. No preamble. No markdown fences.
"""

USER_PROMPT_CALL3 = """
Stakeholder role: {stakeholder_role}

Reasoning report:
{report_json}

Declared KPIs for business context:
{declared_kpis_json}

Return the explanation as JSON only.
"""
```

**Error handling:** Same as Call 2 — validate against `ExplanationOutput`. Log and raise on failure.

---

## 13. API Endpoints

All endpoints prefixed with `/api`. FastAPI app in `backend/main.py`. Include CORS middleware allowing `http://localhost:3000`.

```
POST   /api/profile/interpret          → call1_interpret(free_text) → unconfirmed profile JSON
POST   /api/profile                    → save confirmed profile → ProfileResponse
GET    /api/profile/{id}               → fetch profile → ProfileResponse
GET    /api/profiles                   → list all profiles → List[ProfileResponse]

POST   /api/ingest/{profile_id}        → run ingestion → {"status": "ok", "events_ingested": int}
POST   /api/metrics/compute/{profile_id} → run computation → {"status": "ok", "metrics_computed": int}
GET    /api/metrics/{profile_id}       → fetch latest computed metrics → List[MetricRecord]

POST   /api/intelligence/reason/{profile_id}  → run Call 2 → ReasoningReport
POST   /api/intelligence/explain/{profile_id} → run Call 3 (uses latest report) → ExplanationOutput
GET    /api/intelligence/{profile_id}/latest  → fetch latest explanation → ExplanationOutput

POST   /api/metrics/manual/{profile_id} → save manually entered metric values → {"status": "ok", "saved": int}
GET    /api/metrics/manual/{profile_id} → fetch manual metric values → List[ManualMetricValue]

POST   /api/seed                       → load mock data for profile_id → {"status": "ok"}
```

---

## 14. Frontend Component Specifications

### `ProfileWizard.tsx`
State: `{ step: 1|2|3|4|5, freeText: string, profile: ProfileCreate|null, manualKpis: ManualKPI[], loading: boolean }`

- **Step 1 — Describe your use case**
  `<textarea>` for free-text description of team and business context.
  "Interpret" button → POST `/api/profile/interpret` → populates Step 2.

- **Step 2 — Review and confirm profile**
  Editable form fields pre-populated from Call 1 response.
  All enum fields rendered as `<select>` dropdowns.
  User can correct any field before proceeding.

  **Data source configuration sub-section (always shown at bottom of Step 2):**
  > "Tell us where to fetch your data from. You can connect multiple GitLab projects
  > and Jira boards. Your API credentials are loaded from the server environment."

  - GitLab base URL — text input, defaults to `https://gitlab.com`, editable for self-hosted instances
  - GitLab project IDs — add/remove rows, each row is a numeric project ID (e.g. `12345678`).
    Helper text: "Find your project ID on the GitLab project home page under the project name."
  - Jira base URL — text input (e.g. `https://yourorg.atlassian.net`)
  - Jira project keys — add/remove rows, each row is a project key (e.g. `PROJ`, `CORE`).
    Helper text: "Find your project key in Jira under Project Settings > Details."

  Validation: at least one GitLab project ID OR one Jira project key must be provided
  before the user can proceed to Step 3. Show inline error if both are empty.

- **Step 3 — Declare business KPIs**
  Purpose: capture the business context the LLM needs to reason about severity and impact.
  Show a short explanation at the top:
  > "Business KPIs cannot be fetched automatically. Please enter the values your team
  > tracks so the system can connect technical metrics to business outcomes."

  Pre-populate suggested KPIs based on `decision_type` from the confirmed profile:

  ```
  release_readiness     → suggest: SLA uptime target (%), cost per incident (€/hr)
  sprint_planning       → suggest: sprint velocity (points), feature delivery target (%)
  team_health_review    → suggest: goal completion (%), team satisfaction score (1–10)
  stakeholder_reporting → suggest: SLA uptime (%), TCO (€/month), CSAT score (0–10)
  incident_response     → suggest: SLA uptime (%), cost per incident (€/hr)
  ```

  Each suggested KPI renders as a pre-filled row with editable fields:
  - `name` (string) — pre-filled with suggestion label
  - `current_value` (number) — empty, required
  - `previous_value` (number) — empty, optional (used for trend)
  - `unit` (string) — pre-filled (%, €, points, etc.)
  - `threshold_type` (select: minimum | maximum | target) — pre-filled
  - `business_impact` (string) — placeholder: "e.g. Each hour of downtime costs €10k"

  User can edit, remove, or add custom KPI rows.
  At least one KPI must be declared before proceeding.

- **Step 4 — Manual metric values**
  Purpose: collect current values for metrics marked `_MANUAL` in the selection matrix
  for this use case. These are metrics that cannot be computed from GitLab or Jira.

  Show explanation at top:
  > "The following metrics are relevant for your use case but cannot be fetched
  > automatically. Please enter current and previous period values where available."

  Display only the `_MANUAL` metrics selected for this profile's use case.
  Each row shows: metric name, description, input for current value, input for previous value.
  Fields are optional — skip with warning if left empty.

  ```
  CSAT_MANUAL   → "Customer Satisfaction Score (0–10 or 0–100)"
  DSAT_MANUAL   → "Developer Satisfaction Score (from last survey, 0–10)"
  VEL_MANUAL    → "Sprint Velocity (story points delivered last sprint)"
  WIV_MANUAL    → "Work Item Volume (total issues closed last sprint)"
  TCO_MANUAL    → "Total Cost of Ownership (€/month, infra + ops)"
  SLA_MANUAL    → "SLA Compliance (% of incidents resolved within SLA)"
  GOAL_MANUAL   → "Goal Completion Rate (% of quarterly goals on track)"
  ```

- **Step 5 — Review and confirm**
  Summary of profile, declared KPIs, and manual metric values.
  "Confirm and start analysis" button →
    1. POST `/api/profile` (save confirmed profile with declared_kpis)
    2. POST `/api/metrics/manual/{profile_id}` (save manual metric values)
    3. POST `/api/ingest/{profile_id}` (trigger ingestion)
    4. POST `/api/metrics/compute/{profile_id}` (trigger computation)
    5. Redirect to `/dashboard?profile_id={id}` on completion

### `MetricCard.tsx`
Props: `{ metric: MetricRecord }`
Display:
- Metric code (large, bold) + metric name (small, muted)
- Current value + unit
- Trend indicator: ▲ green (improving), — gray (stable), ▼ red (degrading)
- Threshold badge: green (within) | amber (warning) | red (breach)
- Tier badge: blue (DevOps) | green (Business) | amber (Sustainability)
- If sustainability: show sub-badge Individual or Technical

### `TradeoffPanel.tsx`
Props: `{ conflicts: Conflict[] }`
- List each conflict as a card
- Show metric_a vs metric_b with conflict_type label
- Severity badge: gray (LOW) | blue (MEDIUM) | amber (HIGH) | red (CRITICAL)
- Evidence text below

### `SustainabilityNote.tsx`
Props: `{ flags: SustainabilityFlag[], note: string }`
- Always rendered — never hidden
- If flags exist: amber left border, list each flag
- If no flags: green left border, show note text

### `RecommendationPanel.tsx`
Props: `{ recommendations: Recommendation[], actions: string }`
- Render `actions` as markdown
- Each recommendation chip shows code + priority badge

---

## 15. Mock Data Seed Script

**File:** `backend/db/seed.py`
**Purpose:** Populate the database with synthetic data for a fictional team so the system runs without live API credentials. This enables thesis evaluation and demos.

The seed script must create:

```python
# Fictional team profile (no real org names)
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
            "business_impact": "Each hour of downtime results in contract penalty and customer churn risk"
        }
    ],
    "confirmed": True
}

# Seed computed metrics — realistic values that produce interesting reasoning
SEED_METRICS = [
    {"metric_code": "CFR",  "current_value": 0.22, "previous_value": 0.14, "unit": "%",           "period_days": 14},
    {"metric_code": "DF",   "current_value": 3.2,  "previous_value": 4.1,  "unit": "deployments", "period_days": 14},
    {"metric_code": "MTTR", "current_value": 38.0, "previous_value": 22.0, "unit": "hours",        "period_days": 14},
    {"metric_code": "LTfC", "current_value": 31.0, "previous_value": 28.0, "unit": "hours",        "period_days": 14},
    {"metric_code": "PRCT", "current_value": 52.0, "previous_value": 44.0, "unit": "hours",        "period_days": 14},
    {"metric_code": "PRSi", "current_value": 620,  "previous_value": 410,  "unit": "lines",        "period_days": 14},
    {"metric_code": "TWiP", "current_value": 9,    "previous_value": 6,    "unit": "issues",       "period_days": 14},
    {"metric_code": "BUR",  "current_value": 28.0, "previous_value": 15.0, "unit": "%",            "period_days": 14},
    {"metric_code": "CQI",  "current_value": 78.0, "previous_value": 86.0, "unit": "%",            "period_days": 14},
    {"metric_code": "MIC",  "current_value": 11,   "previous_value": 7,    "unit": "issues",       "period_days": 14},
]
# Note: these values are intentionally degrading to produce a rich reasoning output
# CFR=22% (warning), BUR=28% (breach), MTTR=38h (warning), CQI=78% (warning)
# Expected Call 2 output: overall_health=red, speed_stability conflict HIGH,
# throughput_sustainability conflict CRITICAL, BUR sustainability flag individual/breach
```

Expose via `POST /api/seed` endpoint. Calling this endpoint loads the seed profile and metrics into the database, bypassing ingestion entirely. The frontend dashboard should detect `?demo=true` in the URL and trigger seed load automatically.

---

## 16. Error Handling Behaviour

| Scenario | Expected behaviour |
|---|---|
| LLM returns invalid JSON | Retry once. If still invalid, return HTTP 502 with `{"error": "LLM response invalid", "raw": "..."}` |
| No GitLab project IDs provided in profile | Return HTTP 400 with `{"error": "No GitLab project IDs configured — add at least one in the profile data source settings"}` |
| No Jira project keys provided in profile | Return HTTP 400 with `{"error": "No Jira project keys configured — add at least one in the profile data source settings"}` |
| GitLab project ID not found (404) | Skip that project, log warning: `"GitLab project {id} not found — skipping"`, continue with remaining projects |
| Jira project key not found | Skip that project, log warning: `"Jira project {key} not found — skipping"`, continue with remaining projects |
| All configured projects fail ingestion | Return HTTP 502 with `{"error": "All configured data sources failed — check project IDs and credentials"}` |
| Metric computation returns 0 for all metrics | Log warning, continue — do not block snapshot assembly |
| Snapshot has null current_value for required metric | Skip that metric, log warning, include remaining metrics |
| Profile not confirmed when reasoning is triggered | Return HTTP 400 with `{"error": "Profile must be confirmed before running analysis"}` |
| No manual KPIs declared | Log warning, continue with reduced business context. Call 3 will note limited business KPI data. |
| Manual metric value missing for _MANUAL metric in selection | Skip metric from snapshot, log warning: `"CSAT_MANUAL not provided — excluded from snapshot"` |
| No computed metrics found for profile | Return HTTP 404 with `{"error": "No metrics found — run ingestion and computation first"}` |

---

## 17. Data Privacy and Anonymisation

- No company names, team names, or project names are hardcoded anywhere in the system
- All sample and seed data uses synthetic values with fictional team names
- Profile and metric data are stored locally in SQLite only — no external logging or telemetry
- API credentials are stored in `.env` only — `.env` must be in `.gitignore`
- The system does not log or transmit raw source data beyond the local SQLite database
- Any real organisational data used during thesis evaluation must be anonymised before storage

---

## 19. Dependency Files

### `requirements.txt`
```
fastapi==0.110.0
uvicorn==0.29.0
sqlalchemy==2.0.29
pydantic==2.6.4
anthropic==0.25.0
google-generativeai==0.5.4
openai==1.30.0
httpx==0.27.0
python-dotenv==1.0.1
```

Install with:
```bash
pip install -r requirements.txt
```

Run the backend with:
```bash
uvicorn backend.main:app --reload --port 8000
```

### `package.json`
```json
{
  "name": "metricmind-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "14.2.3",
    "react": "^18",
    "react-dom": "^18",
    "axios": "^1.6.8",
    "tailwindcss": "^3.4.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "typescript": "^5"
  }
}
```

Install with:
```bash
cd frontend
npm install
```

Run the frontend with:
```bash
npm run dev
# Runs on http://localhost:3000
# Backend must be running on http://localhost:8000
```

### Tailwind CSS config (`frontend/tailwind.config.ts`)
```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
```

### `frontend/app/globals.css`
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

### Agent startup instructions
When handing this PRD to an AI coding agent, use the following prompt:

```
You are building MetricMind, an AI-supported DevOps decision intelligence
system. The full specification is in PRD.md in this project.

Read PRD.md completely before writing any code.

Build in the exact order specified in Section 1.3 of the PRD.
Start with Step 1: database models (Section 5).

Rules:
- Ask me before making any decision not covered in the PRD
- Do not skip ahead to later steps
- After each step, tell me what you built and what to test
- Use the exact field names, enum values, and schemas defined in the PRD
- Do not install packages not listed in Section 19
- Backend runs on port 8000, frontend on port 3000
- All timestamps are ISO 8601 UTC strings
- All JSON blobs stored in SQLite are serialised with json.dumps()
  and deserialised with json.loads() — never store raw dicts
```

After each completed step, continue with:
```
Step N is working. Proceed to Step N+1 from Section 1.3.
```

---

## 20. Known Design Decisions and Rationale

| Decision | Rationale |
|---|---|
| Interactive Call 1 (2-turn) | Single free-text prompt produces many null fields. Two-turn conversation — clarify then populate — produces significantly more complete profiles with higher confidence. Validated in prototype testing. |
| Metric prioritisation review | Makes selection matrix transparent to users. Addresses engineer trust concern. Also produces evaluation finding: whether users change the default selection reveals gap between theoretical model and practitioner preference. |
| AI-assisted formula derivation | Extends metric catalog without hardcoding unvalidated formulas. Follows practitioner methodology used in prior work. Confidence levels and transparent flagging maintain academic integrity. LOW confidence metrics excluded from evaluation. |
| Extensible catalog architecture | System designed as metric intelligence platform not fixed-catalog tool. New metrics can be added via catalog browser without code changes. Supports future work beyond thesis scope. |
| Three separate LLM calls | Makes reasoning auditable and testable. Each call has a defined input/output contract. Prevents hallucination of metric values. |
| Recommendations constrained to fixed allowed set | Addresses engineer trust concern from exploratory interviews. Constrained output is testable and defensible in evaluation. |
| Profile human-confirmed before any LLM call | Maintains deterministic boundary. LLM never drives metric selection. |
| BUR computed as after-hours commit proxy | No direct wellbeing data source available in prototype scope. Proxy is transparent and computable. Acknowledged as limitation in thesis. |
| DSAT as manual declared KPI | No survey tooling in scope. System functions with manual input. Limitation acknowledged in thesis. |
| Seed data produces degrading metric values | Ensures reasoning pipeline produces rich, non-trivial output during evaluation and demo. A fully healthy system produces uninteresting Call 2 output. |
| _MANUAL suffix on non-computable metrics | Makes it explicit in code which metrics require human declaration vs automated computation. Prevents silent null values. |
