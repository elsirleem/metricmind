import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const api = axios.create({ baseURL: API_URL });

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DeclaredKPI {
  name: string;
  value: number;
  unit: string;
  threshold_type: "minimum" | "maximum" | "target";
  business_impact: string;
}

export interface DataSourceConfig {
  git_platform?: "gitlab" | "github";
  gitlab_base_url: string;
  gitlab_project_ids: string[];
  github_base_url?: string;
  github_repo_slugs?: string[];
  jira_base_url: string | null;
  jira_project_keys: string[];
}

export interface ProfileCreate {
  team_name: string;
  team_type: string;
  stakeholder_role: string;
  primary_goal: string;
  secondary_goal?: string | null;
  business_criticality: string;
  decision_type: string;
  time_horizon: string;
  data_sources: string[];
  sustainability_focus: string[];
  declared_kpis: DeclaredKPI[];
  data_source_config: DataSourceConfig;
  confirmed: boolean;
}

export interface ProfileResponse extends ProfileCreate {
  id: string;
  created_at: string;
  last_analysis_at?: string | null;
}

export interface MetricRecord {
  code: string;
  name: string;
  current_value: number;
  previous_value: number | null;
  unit: string;
  trend: "improving" | "stable" | "degrading";
  threshold_status: "within" | "warning" | "breach";
  threshold_value: number | null;
  threshold_source: string;
  group: string;
  tier: "devops" | "business" | "sustainability";
  sustainability_dimension: "individual" | "technical" | null;
  source: string;
}

export interface Conflict {
  metric_a: string;
  metric_b: string;
  conflict_type: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  evidence: string;
}

export interface Recommendation {
  code: string;
  target_metrics: string[];
  priority: "immediate" | "this_sprint" | "strategic";
}

export interface SustainabilityFlag {
  dimension: "individual" | "technical";
  metric_code: string;
  status: string;
  consecutive_periods: number;
}

export interface ReasoningReport {
  profile_id: string;
  snapshot_timestamp: string;
  overall_health: "green" | "amber" | "red";
  threshold_assessments: { metric_code: string; status: string; current_value: number; threshold_value: number | null }[];
  conflicts: Conflict[];
  recommendations: Recommendation[];
  sustainability_flags: SustainabilityFlag[];
}

export interface ExplanationSections {
  summary: string;
  key_findings: string;
  sustainability_note: string;
  recommended_actions: string;
  tradeoff_explanation: string;
}

export interface ExplanationOutput {
  profile_id: string;
  stakeholder_role: string;
  sections: ExplanationSections;
  generated_at: string;
}

export interface ManualMetricInput {
  metric_code: string;
  current_value: number;
  previous_value?: number | null;
  unit: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const clarifyProfile = (free_text: string) =>
  api.post<{ questions: string[]; partial_profile: Partial<ProfileCreate> }>("/api/profile/clarify", { free_text }).then((r) => r.data);

export const interpretProfile = (free_text: string, questions?: string[], answers?: string[]) =>
  api.post<Partial<ProfileCreate>>("/api/profile/interpret", { free_text, questions: questions ?? [], answers: answers ?? [] }).then((r) => r.data);

export const confirmProfile = (profileId: string) =>
  api.post<ProfileResponse>(`/api/profile/${profileId}/confirm`).then((r) => r.data);

export const createProfile = (body: ProfileCreate) =>
  api.post<ProfileResponse>("/api/profile", body).then((r) => r.data);

export const getProfile = (id: string) =>
  api.get<ProfileResponse>(`/api/profile/${id}`).then((r) => r.data);

export const getProfiles = () =>
  api.get<ProfileResponse[]>("/api/profile/all").then((r) => r.data);

export const deleteProfile = (id: string) =>
  api.delete<{ status: string; id: string }>(`/api/profile/${id}`).then((r) => r.data);

export const ingestData = (profileId: string, periodDays = 14) =>
  api.post<{ status: string; events_ingested: number }>(`/api/ingest/${profileId}?period_days=${periodDays}`).then((r) => r.data);

export const computeMetrics = (profileId: string, periodDays = 14, metricCodes?: string) =>
  api.post<{ status: string; metrics_computed: number }>(
    `/api/metrics/compute/${profileId}?period_days=${periodDays}${metricCodes ? `&metric_codes=${metricCodes}` : ""}`
  ).then((r) => r.data);

export const getMetrics = (profileId: string) =>
  api.get<MetricRecord[]>(`/api/metrics/${profileId}`).then((r) => r.data);

export const saveManualMetrics = (profileId: string, metrics: ManualMetricInput[]) =>
  api.post<{ status: string; saved: number }>(`/api/metrics/manual/${profileId}`, metrics).then((r) => r.data);

export const getManualMetrics = (profileId: string) =>
  api.get(`/api/metrics/manual/${profileId}`).then((r) => r.data);

export const runReasoning = (profileId: string) =>
  api.post<ReasoningReport>(`/api/intelligence/reason/${profileId}`).then((r) => r.data);

export const runExplanation = (profileId: string) =>
  api.post<ExplanationOutput>(`/api/intelligence/explain/${profileId}`).then((r) => r.data);

export const getLatestExplanation = (profileId: string) =>
  api.get<ExplanationOutput>(`/api/intelligence/${profileId}/latest`).then((r) => r.data);

export const seedDatabase = () =>
  api.post<{ status: string; profile_id: string }>("/api/seed").then((r) => r.data);

// ---------------------------------------------------------------------------
// Metric prioritisation & catalog
// ---------------------------------------------------------------------------

export interface SelectedMetric {
  code: string;
  name: string;
  tier: string;
  priority: number;
  rationale: string;
  source: string;
  formula: string;
  data_source: string;
  ai_derived: boolean;
}

export interface FormulaProposal {
  formula: string;
  plain_language: string;
  data_fields_required: string[];
  confidence: "HIGH" | "MEDIUM" | "LOW";
  research_basis: string;
}

export interface CatalogEntry {
  code: string;
  name: string;
  tier: string;
  source?: string;
  unit?: string;
  formula?: string;
  why?: string;
  space_dimension?: string;
  periodic_group?: string;
  reason?: string;
}

export interface MetricCatalog {
  standard: CatalogEntry[];
  external_required: CatalogEntry[];
}

export const prioritiseMetrics = (profileId: string) =>
  api.post<{ selected_metrics: SelectedMetric[] }>(`/api/metrics/prioritise/${profileId}`).then((r) => r.data);

// ---------------------------------------------------------------------------
// Step 0 — Project exploration (stateless, no profile required)
// ---------------------------------------------------------------------------

export interface ExploreNorthStarMetric {
  code: string;
  name: string;
  tier: string;
  why: string;
  evidence: string;
}

export interface ExploreResult {
  project_summary: string;
  north_star_metrics: ExploreNorthStarMetric[];
  inferred_concerns: string[];
  suggested_kpis: { name: string; why: string }[];
  business_context: string;
  confidence: "LOW" | "MEDIUM" | "HIGH";
  platform: "gitlab" | "github";
  gitlab_project_id: string;
  gitlab_base_url: string;
  github_repo_slug?: string;
  github_base_url?: string;
}

/** Detect whether a project URL is for GitHub or GitLab. */
export function detectPlatform(url: string): "gitlab" | "github" {
  try {
    const host = new URL(url).hostname;
    return host === "github.com" || host.endsWith(".github.com") ? "github" : "gitlab";
  } catch {
    return "gitlab";
  }
}

/** Extract numeric project ID or URL-encoded path from a GitLab project URL. */
export function extractProjectId(gitlabUrl: string): string | null {
  try {
    const url = new URL(gitlabUrl);
    const path = url.pathname.replace(/^\//, "").replace(/\/$/, "");
    if (/^\d+$/.test(path)) return path;
    return encodeURIComponent(path);
  } catch {
    return null;
  }
}

/** Extract "owner/repo" slug from a GitHub repository URL. */
export function extractRepoSlug(githubUrl: string): string | null {
  try {
    const parts = new URL(githubUrl).pathname.replace(/^\//, "").replace(/\/$/, "").split("/").filter(Boolean);
    return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : null;
  } catch {
    return null;
  }
}

export async function exploreProject(
  projectUrl: string,
  jiraUrl?: string
): Promise<ExploreResult> {
  const platform = detectPlatform(projectUrl);
  const baseUrl = new URL(projectUrl).origin;

  let body: Record<string, unknown>;
  if (platform === "github") {
    const repoSlug = extractRepoSlug(projectUrl);
    if (!repoSlug) throw new Error("Invalid GitHub URL — expected https://github.com/owner/repo");
    body = {
      platform: "github",
      github_base_url: baseUrl,
      github_repo_slug: repoSlug,
      jira_base_url: jiraUrl || null,
      jira_project_key: null,
    };
  } else {
    const projectPath = extractProjectId(projectUrl);
    if (!projectPath) throw new Error("Invalid GitLab URL");
    body = {
      platform: "gitlab",
      gitlab_base_url: baseUrl,
      gitlab_project_id: projectPath,
      jira_base_url: jiraUrl || null,
      jira_project_key: null,
    };
  }

  const res = await fetch(`${API_URL}/api/intelligence/explore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error || err.detail?.error || "Analysis failed");
  }

  const result: ExploreResult = await res.json();
  // Trust the origin from the user's URL, not the backend echo
  if (platform === "github") {
    result.github_base_url = baseUrl;
  } else {
    result.gitlab_base_url = baseUrl;
  }
  return result;
}

export const deriveFormula = (metric_code: string, metric_name: string, available_sources: string[]) =>
  api.post<FormulaProposal>("/api/metrics/derive-formula", { metric_code, metric_name, available_sources }).then((r) => r.data);

export const getMetricCatalog = () =>
  api.get<MetricCatalog>("/api/metrics/catalog").then((r) => r.data);
