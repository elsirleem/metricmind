from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional, List
from enum import Enum


class TeamType(str, Enum):
    platform_team = "platform_team"
    product_team = "product_team"
    infrastructure_team = "infrastructure_team"
    security_team = "security_team"


class StakeholderRole(str, Enum):
    engineer = "engineer"
    engineering_lead = "engineering_lead"
    product_owner = "product_owner"
    cto_vp_engineering = "cto_vp_engineering"
    business_analyst = "business_analyst"

    @classmethod
    def _missing_(cls, value):
        # Backward compatibility for the renamed role.
        # Older profiles stored "business_stakeholder"; it now means "business_analyst".
        if value == "business_stakeholder":
            return cls.business_analyst
        return None


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
    target_value: float
    current_value: Optional[float] = None
    unit: str
    threshold_type: str  # 'minimum' | 'maximum' | 'target'
    business_impact: str

    @model_validator(mode="before")
    @classmethod
    def _migrate_value_field(cls, data):
        # Backward compat: profiles created before current_value was added stored the
        # target under "value". Promote that to target_value when target_value is absent.
        if isinstance(data, dict) and "target_value" not in data and "value" in data:
            data = {**data, "target_value": data["value"]}
        return data


class DataSourceConfig(BaseModel):
    # Which Git platform this profile uses. Defaults to "gitlab" for backward
    # compatibility with profiles created before GitHub support was added.
    git_platform: Literal["gitlab", "github"] = "gitlab"

    # GitLab fields
    gitlab_base_url: str = "https://gitlab.com"
    gitlab_project_ids: List[str] = []    # numeric project IDs as strings

    # GitHub fields — repo slugs in "owner/repo" format (e.g. "vercel/next.js")
    github_base_url: str = "https://github.com"
    github_repo_slugs: List[str] = []

    # Jira fields (unchanged)
    jira_base_url: Optional[str] = None   # e.g. https://yourorg.atlassian.net
    jira_project_keys: List[str] = []     # e.g. ["PROJ", "CORE"]

    # Release tag pattern (glob) used to identify production deployments.
    # Default matches common SemVer release tags (v1.2.3 etc). Teams that use
    # alternative naming (release-*, r*, raw semver) can override.
    release_tag_pattern: str = "v*"

    @property
    def git_project_ids(self) -> List[str]:
        """Return the project identifiers for the active git platform."""
        return self.github_repo_slugs if self.git_platform == "github" else self.gitlab_project_ids

    @property
    def git_base_url(self) -> str:
        """Return the base URL for the active git platform."""
        return self.github_base_url if self.git_platform == "github" else self.gitlab_base_url


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
    last_analysis_at: Optional[str] = None
