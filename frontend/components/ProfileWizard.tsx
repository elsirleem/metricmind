"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ProfileCreate, DeclaredKPI, ManualMetricInput, DataSourceConfig, SelectedMetric,
  CatalogEntry, MetricCatalog,
  ExploreResult, ExploreNorthStarMetric,
  clarifyProfile, interpretProfile, confirmProfile, createProfile,
  saveManualMetrics, ingestData, computeMetrics,
  prioritiseMetrics, getMetricCatalog, exploreProject,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TEAM_TYPES = ["platform_team", "product_team", "infrastructure_team", "security_team"];
const STAKEHOLDER_ROLES = ["engineering_lead", "product_owner", "cto_vp_engineering", "business_stakeholder"];
const PRIMARY_GOALS = [
  "maximize_reliability", "maximize_delivery_speed", "reduce_operational_cost",
  "improve_developer_wellbeing", "improve_security_posture", "increase_feature_adoption",
];
const BUSINESS_CRITICALITIES = ["mission_critical", "business_important", "internal_tooling"];
const DECISION_TYPES = ["release_readiness", "incident_response", "sprint_planning", "team_health_review", "stakeholder_reporting"];
const TIME_HORIZONS = ["immediate", "short_term", "strategic"];

const SUGGESTED_KPIS: Record<string, Array<Omit<DeclaredKPI, "value" | "business_impact">>> = {
  release_readiness:     [{ name: "SLA uptime target", unit: "%", threshold_type: "minimum" }, { name: "Cost per incident", unit: "€/hr", threshold_type: "maximum" }],
  sprint_planning:       [{ name: "Sprint velocity", unit: "points", threshold_type: "target" }, { name: "Feature delivery target", unit: "%", threshold_type: "minimum" }],
  team_health_review:    [{ name: "Goal completion", unit: "%", threshold_type: "minimum" }, { name: "Team satisfaction score", unit: "1-10", threshold_type: "minimum" }],
  stakeholder_reporting: [{ name: "SLA uptime", unit: "%", threshold_type: "minimum" }, { name: "TCO", unit: "€/month", threshold_type: "maximum" }, { name: "CSAT score", unit: "0-10", threshold_type: "minimum" }],
  incident_response:     [{ name: "SLA uptime", unit: "%", threshold_type: "minimum" }, { name: "Cost per incident", unit: "€/hr", threshold_type: "maximum" }],
};

const MANUAL_METRIC_INFO: Record<string, { label: string; description: string; unit: string }> = {
  CSAT_MANUAL:  { label: "Customer Satisfaction Score", description: "0–10 or 0–100", unit: "score" },
  DSAT_MANUAL:  { label: "Developer Satisfaction Score", description: "From last survey, 0–10", unit: "score" },
  VEL_MANUAL:   { label: "Sprint Velocity", description: "Story points delivered last sprint", unit: "points" },
  WIV_MANUAL:   { label: "Work Item Volume", description: "Total issues closed last sprint", unit: "issues" },
  TCO_MANUAL:   { label: "Total Cost of Ownership", description: "€/month, infra + ops", unit: "€/month" },
  SLA_MANUAL:   { label: "SLA Compliance", description: "% of incidents resolved within SLA", unit: "%" },
  GOAL_MANUAL:  { label: "Goal Completion Rate", description: "% of quarterly goals on track", unit: "%" },
};

const MANUAL_CODES_BY_USE_CASE: Record<string, string[]> = {
  "maximize_reliability|release_readiness|mission_critical":            ["CSAT_MANUAL", "SLA_MANUAL", "DSAT_MANUAL"],
  "maximize_delivery_speed|sprint_planning|business_important":         ["VEL_MANUAL", "WIV_MANUAL"],
  "improve_developer_wellbeing|team_health_review|business_important":  ["GOAL_MANUAL", "DSAT_MANUAL"],
  "maximize_reliability|stakeholder_reporting|mission_critical":        ["CSAT_MANUAL", "SLA_MANUAL", "TCO_MANUAL", "DSAT_MANUAL"],
  "improve_security_posture|release_readiness|mission_critical":        ["SLA_MANUAL", "CSAT_MANUAL"],
};

const DEFAULT_MANUAL_CODES = ["CSAT_MANUAL", "DSAT_MANUAL"];

const STEP_LABELS = ["Describe", "Configure", "KPIs", "Prioritise", "Metrics", "Review"];

const FIELD_LABELS: Record<string, string> = {
  team_name: "Team name",
  team_type: "Team type",
  stakeholder_role: "Stakeholder role",
  primary_goal: "Primary goal",
  secondary_goal: "Secondary goal",
  business_criticality: "Business criticality",
  decision_type: "Decision type",
  time_horizon: "Time horizon",
};

const TIER_BADGE_CLASSES: Record<string, string> = {
  devops:         "bg-blue-50 text-blue-700",
  business:       "bg-emerald-50 text-emerald-700",
  sustainability: "bg-amber-50 text-amber-700",
};


function getManualCodes(profile: Partial<ProfileCreate>): string[] {
  const key = `${profile.primary_goal}|${profile.decision_type}|${profile.business_criticality}`;
  return MANUAL_CODES_BY_USE_CASE[key] ?? DEFAULT_MANUAL_CODES;
}

function humanise(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Shared form primitives
// ---------------------------------------------------------------------------

function FormSelect({ label, value, options, onChange, required }: {
  label: string; value: string; options: string[]; onChange: (v: string) => void; required?: boolean;
}) {
  return (
    <div>
      <label className="label">{label}{required && <span className="text-rose-500 ml-1">*</span>}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input"
        title={label}
      >
        <option value="">Select…</option>
        {options.map((o) => <option key={o} value={o}>{humanise(o)}</option>)}
      </select>
    </div>
  );
}

function FormInput({ label, value, onChange, placeholder, helper, type = "text" }: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; helper?: string; type?: string;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        type={type} value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input"
      />
      {helper && <p className="text-xs text-slate-400 mt-1.5">{helper}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main wizard
// ---------------------------------------------------------------------------

export default function ProfileWizard() {
  const router = useRouter();

  const [step, setStep] = useState<0 | 1 | 2 | 3 | 4 | 5 | 6>(0);

  // ── Step 0 state ──
  const [step0Phase, setStep0Phase] = useState<"form" | "loading" | "results">("form");
  const [step0GitlabUrl, setStep0GitlabUrl] = useState("");
  const [step0JiraUrl, setStep0JiraUrl] = useState("");
  const [exploreResult, setExploreResult] = useState<ExploreResult | null>(null);
  const [northStarMetricCodes, setNorthStarMetricCodes] = useState<string[]>([]);
  const [step0Completed, setStep0Completed] = useState(false);

  // ── Step 1 phases ──
  const [phase, setPhase] = useState<"input" | "questions" | "done">("input");
  const [freeText, setFreeText] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<string[]>(["", "", ""]);
  const [partialProfile, setPartialProfile] = useState<Partial<ProfileCreate> | null>(null);

  // ── Profile state ──
  const [profile, setProfile] = useState<Partial<ProfileCreate>>({
    team_name: "", team_type: "", stakeholder_role: "", primary_goal: "",
    secondary_goal: null, business_criticality: "", decision_type: "",
    time_horizon: "", data_sources: ["gitlab", "jira"], sustainability_focus: [],
    declared_kpis: [], confirmed: false,
    data_source_config: {
      git_platform: "gitlab",
      gitlab_base_url: "https://gitlab.com", gitlab_project_ids: [],
      github_base_url: "https://github.com", github_repo_slugs: [],
      jira_base_url: "", jira_project_keys: [],
    },
  });
  const [manualKpis, setManualKpis] = useState<DeclaredKPI[]>([]);
  const [manualMetrics, setManualMetrics] = useState<Record<string, { current: string; previous: string }>>({});

  // ── Step 4 (Prioritise) state ──
  const [savedProfileId, setSavedProfileId] = useState<string | null>(null);
  const [selectedMetrics, setSelectedMetrics] = useState<SelectedMetric[]>([]);
  const [loadingPrioritise, setLoadingPrioritise] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [catalogData, setCatalogData] = useState<MetricCatalog | null>(null);
  const [catalogTab, setCatalogTab] = useState<"standard" | "external">("standard");

  // ── General ──
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (field: keyof ProfileCreate, value: unknown) =>
    setProfile((p) => ({ ...p, [field]: value }));

  const setDsc = (field: keyof DataSourceConfig, value: unknown) =>
    setProfile((p) => ({
      ...p,
      data_source_config: { ...(p.data_source_config as DataSourceConfig), [field]: value },
    }));

  const dsc = profile.data_source_config as DataSourceConfig;
  const step2Valid = (
    dsc?.git_platform === "github"
      ? (dsc?.github_repo_slugs?.length ?? 0) > 0
      : (dsc?.gitlab_project_ids?.length ?? 0) > 0
  ) || (dsc?.jira_project_keys?.length ?? 0) > 0;
  const manualCodes = getManualCodes(profile);

  // ── Step 4: load prioritised metrics on entry ────────────────────────────

  useEffect(() => {
    if (step === 4 && savedProfileId && selectedMetrics.length === 0) {
      setLoadingPrioritise(true);
      prioritiseMetrics(savedProfileId)
        .then((data) => {
          let metrics = data.selected_metrics;
          if (northStarMetricCodes.length > 0 && exploreResult) {
            const existingCodes = new Set(metrics.map((m: SelectedMetric) => m.code));
            const added: SelectedMetric[] = exploreResult.north_star_metrics
              .filter((ns: ExploreNorthStarMetric) => !existingCodes.has(ns.code))
              .map((ns: ExploreNorthStarMetric, i: number) => ({
                code: ns.code,
                name: ns.name,
                tier: ns.tier,
                priority: metrics.length + i + 1,
                rationale: ns.why,
                source: "north_star",
                formula: "",
                data_source: "gitlab",
                ai_derived: false,
              }));
            metrics = [...metrics, ...added];
          }
          setSelectedMetrics(metrics);
        })
        .catch(() => setError("Could not load metric recommendations. You can add metrics manually."))
        .finally(() => setLoadingPrioritise(false));
    }
  }, [step, savedProfileId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handlers ────────────────────────────────────────────────────────────

  // ── Step 0 handlers ──────────────────────────────────────────────────────

  const handleExploreProject = async () => {
    if (!step0GitlabUrl.trim()) return;
    setStep0Phase("loading");
    setError("");
    try {
      const result = await exploreProject(step0GitlabUrl, step0JiraUrl || undefined);
      setExploreResult(result);
      setStep0Phase("results");
    } catch (e: unknown) {
      setStep0Phase("form");
      setError(e instanceof Error ? e.message : "Project analysis failed. Please check your URL and try again.");
    }
  };

  const handleSkipStep0 = () => {
    setStep0Completed(false);
    setStep(1);
  };

  const handleContinueFromStep0 = () => {
    if (!exploreResult) return;
    setNorthStarMetricCodes(exploreResult.north_star_metrics.map((m) => m.code));
    setStep0Completed(true);
    // Pre-fill data source config for Step 2 based on detected platform
    const isGitHub = exploreResult.platform === "github";
    const hasJira = (profile.data_sources ?? []).includes("jira");
    setProfile((p) => ({
      ...p,
      data_sources: isGitHub ? (hasJira ? ["github", "jira"] : ["github"]) : (hasJira ? ["gitlab", "jira"] : ["gitlab"]),
      data_source_config: {
        git_platform: exploreResult.platform,
        gitlab_base_url: isGitHub ? "https://gitlab.com" : exploreResult.gitlab_base_url,
        gitlab_project_ids: isGitHub ? [] : [exploreResult.gitlab_project_id],
        github_base_url: isGitHub ? (exploreResult.github_base_url ?? "https://github.com") : "https://github.com",
        github_repo_slugs: isGitHub ? [exploreResult.github_repo_slug ?? ""] : [],
        jira_base_url: step0JiraUrl || null,
        jira_project_keys: [],
      },
    }));
    setStep(1);
  };

  // ── Step 1 handlers ──────────────────────────────────────────────────────

  const handleAnalyse = async () => {
    if (!freeText.trim()) return;
    setLoading(true); setError("");
    try {
      const result = await clarifyProfile(freeText);
      setQuestions(result.questions);
      setPartialProfile(result.partial_profile);
      setAnswers(new Array(result.questions.length).fill(""));
      setPhase("questions");
    } catch {
      setError("Could not interpret your description. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleContinueFromQuestions = async () => {
    setLoading(true); setError("");
    try {
      const result = await interpretProfile(freeText, questions, answers);
      setProfile((p) => ({ ...p, ...result, confirmed: false }));
      setStep(2);
    } catch {
      setError("Could not interpret your description. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const initKpis = () => {
    const suggestions = SUGGESTED_KPIS[profile.decision_type ?? ""] ?? [];
    setManualKpis(suggestions.map((s) => ({ ...s, value: 0, business_impact: "" })));
  };

  const handleSaveAndPrioritise = async () => {
    setLoading(true); setError("");
    try {
      const fullProfile: ProfileCreate = {
        ...(profile as ProfileCreate),
        declared_kpis: manualKpis,
        confirmed: false,
      };
      const sanitised: ProfileCreate = {
        ...fullProfile,
        secondary_goal: fullProfile.secondary_goal || null,
        data_sources: fullProfile.data_sources ?? [],
        sustainability_focus: fullProfile.sustainability_focus ?? [],
        declared_kpis: fullProfile.declared_kpis ?? [],
        data_source_config: {
          git_platform: fullProfile.data_source_config?.git_platform ?? "gitlab",
          gitlab_base_url: (() => { try { return new URL(fullProfile.data_source_config?.gitlab_base_url ?? "https://gitlab.com").origin; } catch { return "https://gitlab.com"; } })(),
          gitlab_project_ids: fullProfile.data_source_config?.gitlab_project_ids ?? [],
          github_base_url: (() => { try { return new URL(fullProfile.data_source_config?.github_base_url ?? "https://github.com").origin; } catch { return "https://github.com"; } })(),
          github_repo_slugs: fullProfile.data_source_config?.github_repo_slugs ?? [],
          jira_base_url: fullProfile.data_source_config?.jira_base_url ?? null,
          jira_project_keys: fullProfile.data_source_config?.jira_project_keys ?? [],
        },
      };
      const saved = await createProfile(sanitised);
      setSavedProfileId(saved.id);
      setSelectedMetrics([]); // reset so useEffect fetches fresh
      setStep(4);
    } catch {
      setError("Failed to save profile. Please check your inputs and try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    setLoading(true); setError("");
    try {
      let profileId = savedProfileId;
      if (profileId) {
        await confirmProfile(profileId);
      } else {
        // Fallback path (if step 4 was somehow bypassed)
        const fullProfile: ProfileCreate = {
          ...(profile as ProfileCreate),
          declared_kpis: manualKpis,
          confirmed: true,
        };
        const sanitised: ProfileCreate = {
          ...fullProfile,
          secondary_goal: fullProfile.secondary_goal || null,
          data_sources: fullProfile.data_sources ?? [],
          sustainability_focus: fullProfile.sustainability_focus ?? [],
          declared_kpis: fullProfile.declared_kpis ?? [],
          data_source_config: {
            gitlab_base_url: (() => { try { return new URL(fullProfile.data_source_config?.gitlab_base_url ?? "https://gitlab.com").origin; } catch { return "https://gitlab.com"; } })(),
            gitlab_project_ids: fullProfile.data_source_config?.gitlab_project_ids ?? [],
            jira_base_url: fullProfile.data_source_config?.jira_base_url ?? null,
            jira_project_keys: fullProfile.data_source_config?.jira_project_keys ?? [],
          },
        };
        const saved = await createProfile(sanitised);
        profileId = saved.id;
      }

      const manualInputs: ManualMetricInput[] = manualCodes
        .filter((code) => manualMetrics[code]?.current)
        .map((code) => ({
          metric_code: code,
          current_value: parseFloat(manualMetrics[code].current),
          previous_value: manualMetrics[code].previous ? parseFloat(manualMetrics[code].previous) : null,
          unit: MANUAL_METRIC_INFO[code]?.unit ?? "value",
        }));
      if (manualInputs.length > 0) await saveManualMetrics(profileId, manualInputs);

      const metricCodes = selectedMetrics.length > 0
        ? selectedMetrics.map((m) => m.code).join(",")
        : undefined;

      try { await ingestData(profileId); } catch {}
      try { await computeMetrics(profileId, 14, metricCodes); } catch {}

      router.push(`/dashboard?profile_id=${profileId}`);
    } catch (e: unknown) {
      setError("Submission failed. Please check your inputs and try again.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // ── Catalog helpers ──────────────────────────────────────────────────────

  const openCatalog = async () => {
    setShowCatalog(true);
    if (!catalogData) {
      try {
        const data = await getMetricCatalog();
        setCatalogData(data);
      } catch {
        setError("Could not load metric catalog.");
      }
    }
  };

  const addFromCatalog = (entry: CatalogEntry) => {
    if (selectedMetrics.find((m) => m.code === entry.code)) return;
    setSelectedMetrics((prev) => [
      ...prev,
      {
        code: entry.code,
        name: entry.name,
        tier: entry.tier,
        priority: prev.length + 1,
        rationale: "",
        source: "catalog",
        formula: entry.formula ?? "",
        data_source: entry.source ?? "",
        ai_derived: false,
      },
    ]);
    setShowCatalog(false);
  };

  const selectedCodes = new Set(selectedMetrics.map((m) => m.code));

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Step indicator */}
      <div className="flex items-center gap-0 mb-8">
        {/* Step 0 pre-step */}
        <div className="flex items-center">
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2
              ${step === 0
                ? "border-[#1B6EF3] bg-[#1B6EF3] text-white"
                : step0Completed
                ? "border-[#1B6EF3] bg-white text-[#1B6EF3]"
                : "border-dashed border-slate-300 bg-white text-slate-400"}`}
            >
              {step0Completed ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              )}
            </div>
            <span className={`text-xs mt-1 font-medium whitespace-nowrap ${step === 0 ? "text-[#1B6EF3]" : step0Completed ? "text-[#1B6EF3]" : "text-slate-400"}`}>
              Explore
            </span>
          </div>
          <div className={`w-5 h-px mx-2 mb-4 ${step > 0 ? "bg-[#1B6EF3]" : "bg-slate-200"}`} />
        </div>
        {STEP_LABELS.map((label, idx) => {
          const n = idx + 1;
          const done   = step > n;
          const active = step === n;
          return (
            <div key={n} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2
                  ${active  ? "border-[#1B6EF3] bg-[#1B6EF3] text-white"
                  : done    ? "border-[#1B6EF3] bg-[#1B6EF3] text-white"
                  :           "border-slate-200 bg-white text-slate-400"}`}
                >
                  {done ? (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : n}
                </div>
                <span className={`text-xs mt-1 font-medium ${active || done ? "text-[#1B6EF3]" : "text-slate-400"}`}>
                  {label}
                </span>
              </div>
              {n < 6 && (
                <div className={`flex-1 h-px mx-2 mb-4 ${step > n ? "bg-[#1B6EF3]" : "bg-slate-200"}`} />
              )}
            </div>
          );
        })}
      </div>

      {error && (
        <div className="mb-5 p-4 bg-rose-50 border border-rose-200 text-rose-700 rounded-xl text-sm">
          {error}
        </div>
      )}

      {/* ── Step 0: Explore (optional) ── */}
      {step === 0 && (
        <div className="card p-6">
          {step0Phase === "form" && (
            <>
              <h2 className="text-lg font-bold text-slate-900 mb-1">Not sure where to start?</h2>
              <p className="text-sm text-slate-500 mb-5">
                Paste your GitLab or GitHub project URL and MetricMind will analyse your activity to recommend
                the right metrics before you continue. This takes about 30 seconds.
              </p>
              <div className="space-y-4">
                <FormInput
                  label="Git project URL (GitLab or GitHub)"
                  value={step0GitlabUrl}
                  onChange={setStep0GitlabUrl}
                  placeholder="https://github.com/owner/repo  or  https://gitlab.com/group/project"
                  helper="Paste the full URL of your GitLab project or GitHub repository"
                />
                <FormInput
                  label="Jira URL (optional)"
                  value={step0JiraUrl}
                  onChange={setStep0JiraUrl}
                  placeholder="https://yourorg.atlassian.net"
                />
              </div>
              <button
                onClick={handleExploreProject}
                disabled={!step0GitlabUrl.trim()}
                className="btn-primary mt-5 w-full py-2.5"
              >
                Analyse project →
              </button>
              <div className="mt-3 text-center">
                <button
                  type="button"
                  onClick={handleSkipStep0}
                  className="text-sm text-slate-400 hover:text-slate-600"
                >
                  Skip — I know what I need →
                </button>
              </div>
            </>
          )}

          {step0Phase === "loading" && (
            <div className="flex flex-col items-center py-10 gap-4">
              <div className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: "#1B6EF3", borderTopColor: "transparent" }} />
              <p className="text-sm font-semibold text-slate-700 text-center">
                Reading project activity and identifying North Star metrics…
              </p>
              <p className="text-xs text-slate-400">This usually takes 15–30 seconds.</p>
            </div>
          )}

          {step0Phase === "results" && exploreResult && (
            <div className="space-y-5">
              {/* Section A — Project summary */}
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Project overview</p>
                <p className="text-sm text-slate-700">{exploreResult.project_summary}</p>
              </div>

              {/* Section B — North Star metrics */}
              <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Recommended North Star metrics</p>
                <p className="text-xs text-slate-400 mb-3">Based on your project activity</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {exploreResult.north_star_metrics.map((m) => (
                    <div key={m.code} className="border border-slate-200 rounded-xl p-4 bg-white">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-xs font-black tracking-widest uppercase" style={{ color: "#1B6EF3" }}>{m.code}</span>
                        <span className={`badge text-[10px] ${m.tier === "devops" ? "bg-[#EBF2FE] text-[#0A1628] border border-[#1B6EF3]" : m.tier === "business" ? "bg-[#E0F4EF] text-[#064D3B] border border-[#0B7A5E]" : "bg-[#E8F5E9] text-[#14532D] border border-[#16A34A]"}`}>
                          {m.tier}
                        </span>
                      </div>
                      <p className="text-sm font-semibold text-slate-800 mb-1">{m.name}</p>
                      <p className="text-xs text-slate-500 italic mb-1">{m.why}</p>
                      <p className="text-xs text-slate-400">{m.evidence}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Section C — Inferred concerns */}
              {exploreResult.inferred_concerns.length > 0 && (
                <div className="border-l-4 border-amber-400 bg-amber-50 rounded-r-xl p-4">
                  <p className="text-[10px] font-bold text-amber-700 uppercase tracking-wider mb-2">Inferred concerns</p>
                  <ul className="space-y-1">
                    {exploreResult.inferred_concerns.map((c, i) => (
                      <li key={i} className="text-sm text-amber-800 flex items-start gap-2">
                        <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Section D — Suggested KPIs + Business context */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="border border-slate-200 rounded-xl p-4 bg-white">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Suggested business KPIs</p>
                  <ul className="space-y-2">
                    {exploreResult.suggested_kpis.map((k, i) => (
                      <li key={i}>
                        <p className="text-xs font-semibold text-slate-800">{k.name}</p>
                        <p className="text-xs text-slate-400">{k.why}</p>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="border border-slate-200 rounded-xl p-4 bg-white">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Business context</p>
                  <p className="text-sm text-slate-700">{exploreResult.business_context}</p>
                </div>
              </div>

              {/* Confidence badge */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Analysis confidence:</span>
                <span className={`badge text-xs ${exploreResult.confidence === "HIGH" ? "bg-emerald-50 text-emerald-700" : exploreResult.confidence === "MEDIUM" ? "bg-blue-50 text-blue-700" : "bg-amber-50 text-amber-700"}`}>
                  {exploreResult.confidence}
                </span>
              </div>

              <button
                onClick={handleContinueFromStep0}
                className="btn-primary w-full py-2.5"
              >
                Continue with these recommendations →
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Step 1: Describe (3-phase) ── */}
      {step === 1 && (
        <div className="card p-6">
          {/* Phase: input */}
          {phase === "input" && (
            <>
              <h2 className="text-lg font-bold text-slate-900 mb-1">Describe your use case</h2>
              <p className="text-sm text-slate-500 mb-5">
                Tell us about your team, what you&apos;re deciding, and the business context. AI will ask a few clarifying questions.
              </p>
              <textarea
                className="input h-40 resize-none"
                placeholder="e.g. We're a platform engineering team supporting a mission-critical payments service. We're preparing for a release and want to understand our current reliability risks..."
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
              />
              <button
                onClick={handleAnalyse}
                disabled={!freeText.trim() || loading}
                className="btn-primary mt-4 w-full py-2.5"
              >
                {loading ? "Analysing…" : "Analyse"}
              </button>
            </>
          )}

          {/* Phase: questions */}
          {phase === "questions" && partialProfile && (
            <>
              <h2 className="text-lg font-bold text-slate-900 mb-4">Review what I understood</h2>

              {/* Understood fields */}
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mb-5">
                <p className="text-xs font-bold text-emerald-700 uppercase tracking-wide mb-3">I understood the following:</p>
                <ul className="space-y-1.5">
                  {Object.entries(partialProfile)
                    .filter(([k, v]) => v !== null && v !== undefined && v !== "" && FIELD_LABELS[k])
                    .map(([k, v]) => (
                      <li key={k} className="flex items-start gap-2 text-sm text-emerald-800">
                        <svg className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        <span><span className="font-semibold">{FIELD_LABELS[k]}:</span> {humanise(String(v))}</span>
                      </li>
                    ))}
                </ul>
              </div>

              {/* Clarifying questions */}
              <p className="text-sm font-semibold text-slate-700 mb-4">
                To give you the best analysis, I need a few more details:
              </p>
              <div className="space-y-4 mb-5">
                {questions.map((q, i) => (
                  <div key={i}>
                    <label className="block text-sm font-bold text-slate-800 mb-1.5">{q}</label>
                    <input
                      type="text"
                      className="input"
                      value={answers[i] ?? ""}
                      onChange={(e) => {
                        const updated = [...answers];
                        updated[i] = e.target.value;
                        setAnswers(updated);
                      }}
                      placeholder="Your answer…"
                    />
                  </div>
                ))}
              </div>

              <div className="flex gap-3">
                <button onClick={() => setPhase("input")} className="btn-secondary flex-1">Back</button>
                <button
                  onClick={handleContinueFromQuestions}
                  disabled={loading}
                  className="btn-primary flex-1 py-2.5"
                >
                  {loading ? "Processing…" : "Continue →"}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Step 2: Review & configure ── */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="card p-6">
            <h2 className="text-lg font-bold text-slate-900 mb-1">Review profile</h2>
            <p className="text-sm text-slate-500 mb-5">Verify and correct the AI-interpreted fields.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <FormInput label="Team name" value={profile.team_name ?? ""} onChange={(v) => set("team_name", v)} placeholder="e.g. Platform Engineering" />
              </div>
              <FormSelect label="Team type"            value={profile.team_type ?? ""}            options={TEAM_TYPES}             onChange={(v) => set("team_type", v)}            required />
              <FormSelect label="Stakeholder role"     value={profile.stakeholder_role ?? ""}     options={STAKEHOLDER_ROLES}      onChange={(v) => set("stakeholder_role", v)}     required />
              <FormSelect label="Primary goal"         value={profile.primary_goal ?? ""}         options={PRIMARY_GOALS}          onChange={(v) => set("primary_goal", v)}         required />
              <FormSelect label="Secondary goal"       value={profile.secondary_goal ?? ""}       options={PRIMARY_GOALS}          onChange={(v) => set("secondary_goal", v || null)} />
              <FormSelect label="Business criticality" value={profile.business_criticality ?? ""} options={BUSINESS_CRITICALITIES}  onChange={(v) => set("business_criticality", v)} required />
              <FormSelect label="Decision type"        value={profile.decision_type ?? ""}        options={DECISION_TYPES}         onChange={(v) => set("decision_type", v)}        required />
              <FormSelect label="Time horizon"         value={profile.time_horizon ?? ""}         options={TIME_HORIZONS}          onChange={(v) => set("time_horizon", v)}         required />
            </div>
          </div>

          {/* Data source config */}
          <div className="card p-6">
            <h3 className="text-sm font-bold text-slate-800 mb-1">Data sources</h3>
            {step0Completed && (
              <div className="mt-2 mb-3 px-3 py-2 bg-violet-50 border border-violet-100 rounded-lg">
                <p className="text-xs text-violet-700 font-medium">Pre-filled from your project analysis</p>
              </div>
            )}
            <p className="text-xs text-slate-500 mb-5">
              Connect your Git platform and Jira boards. API credentials are loaded from server environment.
            </p>

            <div className="space-y-5">
              {/* Platform toggle */}
              <div>
                <label className="label">Git platform</label>
                <div className="flex gap-2 mt-1">
                  {(["gitlab", "github"] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => {
                        setDsc("git_platform", p);
                        const hasJira = (profile.data_sources ?? []).includes("jira");
                        set("data_sources", hasJira ? [p, "jira"] : [p]);
                      }}
                      className={`flex-1 py-2 px-3 rounded-lg text-sm font-semibold border transition-colors ${
                        (dsc?.git_platform ?? "gitlab") === p
                          ? "border-[#1B6EF3] bg-[#EBF2FE] text-[#0A1628]"
                          : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                      }`}
                    >
                      {p === "gitlab" ? "GitLab" : "GitHub"}
                    </button>
                  ))}
                </div>
              </div>

              {/* GitLab fields */}
              {(dsc?.git_platform ?? "gitlab") !== "github" && (
                <>
                  <FormInput
                    label="GitLab base URL"
                    value={dsc?.gitlab_base_url ?? "https://gitlab.com"}
                    onChange={(v) => setDsc("gitlab_base_url", v)}
                    placeholder="https://gitlab.com"
                  />
                  <div>
                    <label className="label">GitLab project IDs</label>
                    <p className="text-xs text-slate-400 mb-2">Find the project ID on the GitLab project home page.</p>
                    <div className="space-y-2">
                      {(dsc?.gitlab_project_ids ?? []).map((id, i) => (
                        <div key={i} className="flex gap-2">
                          <input type="text" value={id}
                            onChange={(e) => {
                              const ids = [...(dsc?.gitlab_project_ids ?? [])];
                              ids[i] = e.target.value;
                              setDsc("gitlab_project_ids", ids);
                            }}
                            placeholder="e.g. 12345678"
                            className="input flex-1"
                          />
                          <button
                            type="button"
                            onClick={() => setDsc("gitlab_project_ids", (dsc?.gitlab_project_ids ?? []).filter((_, j) => j !== i))}
                            className="px-3 py-2 text-xs font-semibold text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-50"
                          >Remove</button>
                        </div>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={() => setDsc("gitlab_project_ids", [...(dsc?.gitlab_project_ids ?? []), ""])}
                      className="mt-2 text-xs font-semibold text-[#1B6EF3] hover:text-[#0A1628]"
                    >+ Add project ID</button>
                  </div>
                </>
              )}

              {/* GitHub fields */}
              {dsc?.git_platform === "github" && (
                <>
                  <FormInput
                    label="GitHub base URL"
                    value={dsc?.github_base_url ?? "https://github.com"}
                    onChange={(v) => setDsc("github_base_url", v)}
                    placeholder="https://github.com"
                    helper="Only change if using GitHub Enterprise"
                  />
                  <div>
                    <label className="label">GitHub repositories</label>
                    <p className="text-xs text-slate-400 mb-2">Enter repositories as owner/repo (e.g. vercel/next.js)</p>
                    <div className="space-y-2">
                      {(dsc?.github_repo_slugs ?? []).map((slug, i) => (
                        <div key={i} className="flex gap-2">
                          <input type="text" value={slug}
                            onChange={(e) => {
                              const slugs = [...(dsc?.github_repo_slugs ?? [])];
                              slugs[i] = e.target.value;
                              setDsc("github_repo_slugs", slugs);
                            }}
                            placeholder="e.g. vercel/next.js"
                            className="input flex-1"
                          />
                          <button
                            type="button"
                            onClick={() => setDsc("github_repo_slugs", (dsc?.github_repo_slugs ?? []).filter((_, j) => j !== i))}
                            className="px-3 py-2 text-xs font-semibold text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-50"
                          >Remove</button>
                        </div>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={() => setDsc("github_repo_slugs", [...(dsc?.github_repo_slugs ?? []), ""])}
                      className="mt-2 text-xs font-semibold text-[#1B6EF3] hover:text-[#0A1628]"
                    >+ Add repository</button>
                  </div>
                </>
              )}

              <FormInput
                label="Jira base URL"
                value={dsc?.jira_base_url ?? ""}
                onChange={(v) => setDsc("jira_base_url", v || null)}
                placeholder="https://yourorg.atlassian.net"
              />

              <div>
                <label className="label">Jira project keys</label>
                <p className="text-xs text-slate-400 mb-2">Find your project key in Jira under Project Settings &gt; Details.</p>
                <div className="space-y-2">
                  {(dsc?.jira_project_keys ?? []).map((key, i) => (
                    <div key={i} className="flex gap-2">
                      <input type="text" value={key}
                        onChange={(e) => {
                          const keys = [...(dsc?.jira_project_keys ?? [])];
                          keys[i] = e.target.value;
                          setDsc("jira_project_keys", keys);
                        }}
                        placeholder="e.g. PROJ"
                        className="input flex-1"
                      />
                      <button
                        onClick={() => setDsc("jira_project_keys", (dsc?.jira_project_keys ?? []).filter((_, j) => j !== i))}
                        className="px-3 py-2 text-xs font-semibold text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-50"
                      >Remove</button>
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => setDsc("jira_project_keys", [...(dsc?.jira_project_keys ?? []), ""])}
                  className="mt-2 text-xs font-semibold text-[#1B6EF3] hover:text-[#0A1628]"
                >+ Add project key</button>
              </div>
            </div>

            {!step2Valid && (
              <p className="mt-4 text-xs text-rose-600 font-medium">
                At least one {dsc?.git_platform === "github" ? "GitHub repository" : "GitLab project ID"} or one Jira project key is required.
              </p>
            )}
          </div>

          <div className="flex gap-3">
            <button onClick={() => setStep(1)} className="btn-secondary flex-1">Back</button>
            <button
              onClick={() => { initKpis(); setStep(3); }}
              disabled={!step2Valid}
              className="btn-primary flex-1 py-2.5"
            >Next: Declare KPIs</button>
          </div>
        </div>
      )}

      {/* ── Step 3: Declare KPIs ── */}
      {step === 3 && (
        <div>
          <div className="card p-6 mb-4">
            <h2 className="text-lg font-bold text-slate-900 mb-1">Declare business KPIs</h2>
            <p className="text-sm text-slate-500 mb-5">
              Business KPIs connect technical metrics to outcomes. Enter the values your team tracks.
            </p>

            <div className="space-y-3">
              {manualKpis.map((kpi, i) => (
                <div key={i} className="border border-slate-200 rounded-xl p-4 bg-slate-50">
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <div>
                      <label className="label">Name</label>
                      <input type="text" value={kpi.name} title="KPI name"
                        onChange={(e) => { const k = [...manualKpis]; k[i] = { ...k[i], name: e.target.value }; setManualKpis(k); }}
                        placeholder="e.g. SLA uptime" className="input" />
                    </div>
                    <div>
                      <label className="label">Value <span className="text-rose-500">*</span></label>
                      <input type="number" value={kpi.value || ""} title="KPI value"
                        onChange={(e) => { const k = [...manualKpis]; k[i] = { ...k[i], value: parseFloat(e.target.value) || 0 }; setManualKpis(k); }}
                        placeholder="0" className="input" />
                    </div>
                    <div>
                      <label className="label">Unit</label>
                      <input type="text" value={kpi.unit} title="Unit"
                        onChange={(e) => { const k = [...manualKpis]; k[i] = { ...k[i], unit: e.target.value }; setManualKpis(k); }}
                        placeholder="e.g. %" className="input" />
                    </div>
                    <div>
                      <label className="label">Threshold type</label>
                      <select value={kpi.threshold_type} title="Threshold type"
                        onChange={(e) => { const k = [...manualKpis]; k[i] = { ...k[i], threshold_type: e.target.value as DeclaredKPI["threshold_type"] }; setManualKpis(k); }}
                        className="input">
                        <option value="minimum">Minimum</option>
                        <option value="maximum">Maximum</option>
                        <option value="target">Target</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="label">Business impact</label>
                    <input type="text" value={kpi.business_impact}
                      onChange={(e) => { const k = [...manualKpis]; k[i] = { ...k[i], business_impact: e.target.value }; setManualKpis(k); }}
                      placeholder="e.g. Each hour of downtime costs €10k"
                      className="input" />
                  </div>
                  <button onClick={() => setManualKpis(manualKpis.filter((_, j) => j !== i))}
                    className="mt-3 text-xs font-semibold text-rose-600 hover:text-rose-700">
                    Remove KPI
                  </button>
                </div>
              ))}
            </div>

            <button
              onClick={() => setManualKpis([...manualKpis, { name: "", value: 0, unit: "", threshold_type: "target", business_impact: "" }])}
              className="mt-4 text-xs font-semibold text-violet-600 hover:text-violet-700"
            >+ Add custom KPI</button>

            {manualKpis.length === 0 && (
              <p className="mt-3 text-xs text-amber-600 font-medium">At least one KPI is recommended before proceeding.</p>
            )}
          </div>

          <div className="flex gap-3">
            <button onClick={() => setStep(2)} className="btn-secondary flex-1">Back</button>
            <button
              onClick={handleSaveAndPrioritise}
              disabled={loading}
              className="btn-primary flex-1 py-2.5"
            >{loading ? "Saving…" : "Next: Review metrics"}</button>
          </div>
        </div>
      )}

      {/* ── Step 4: Metric prioritisation ── */}
      {step === 4 && (
        <div>
          <div className="card p-6 mb-4">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900 mb-1">Selected metrics</h2>
                <p className="text-sm text-slate-500">
                  AI-recommended metrics for your use case. Remove any that are not relevant, or add more from the catalog.
                </p>
              </div>
              <button
                onClick={openCatalog}
                className="btn-secondary ml-4 flex-shrink-0 flex items-center gap-1.5"
              >
                <span className="text-lg leading-none">+</span> Add from catalog
              </button>
            </div>

            {loadingPrioritise ? (
              <div className="space-y-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-20 bg-slate-100 rounded-xl" />
                ))}
              </div>
            ) : selectedMetrics.length === 0 ? (
              <p className="text-sm text-slate-400 py-6 text-center">
                No metrics loaded. Use the catalog to add metrics manually.
              </p>
            ) : (
              <div className="space-y-6">
                {(["devops", "business", "sustainability"] as const).map((tier) => {
                  const tierMetrics = selectedMetrics.filter((m) => m.tier === tier);
                  if (tierMetrics.length === 0) return null;
                  const tierLabel = tier === "devops" ? "DevOps" : tier === "business" ? "Business" : "Sustainability";
                  return (
                    <div key={tier}>
                      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">{tierLabel}</h3>
                      <div className="space-y-2">
                        {tierMetrics.map((m) => (
                          <div key={m.code} className="border border-slate-200 rounded-xl p-4 bg-white flex gap-4">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <span className="text-xs font-black text-slate-800 tracking-widest uppercase">{m.code}</span>
                                <span className="text-sm font-semibold text-slate-700">{m.name}</span>
                                <span className={`badge ${TIER_BADGE_CLASSES[m.tier] ?? "bg-slate-100 text-slate-600"}`}>{tier}</span>
                                {m.source === "north_star" && (
                                  <span className="badge bg-amber-50 text-amber-700 border border-amber-200">★ North Star</span>
                                )}
                                {m.ai_derived && (
                                  <span className="badge bg-amber-50 text-amber-700">AI formula</span>
                                )}
                              </div>
                              {m.rationale && (
                                <p className="text-sm text-slate-600 italic mb-1">{m.rationale}</p>
                              )}
                              {m.formula && (
                                <p className="text-xs text-slate-400">{m.formula}</p>
                              )}
                            </div>
                            <button
                              onClick={() => setSelectedMetrics((prev) => prev.filter((x) => x.code !== m.code))}
                              className="text-xs font-semibold text-rose-500 hover:text-rose-700 flex-shrink-0 self-start mt-0.5"
                            >Remove</button>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <button onClick={() => setStep(3)} className="btn-secondary flex-1">Back</button>
            <button onClick={() => setStep(5)} className="btn-primary flex-1 py-2.5">Confirm metrics →</button>
          </div>
        </div>
      )}

      {/* ── Step 5: Manual metric values ── */}
      {step === 5 && (
        <div>
          <div className="card p-6 mb-4">
            <h2 className="text-lg font-bold text-slate-900 mb-1">Manual metric values</h2>
            <p className="text-sm text-slate-500 mb-5">
              These metrics are relevant to your use case but cannot be fetched automatically.
            </p>

            <div className="space-y-3">
              {manualCodes.map((code) => {
                const info = MANUAL_METRIC_INFO[code];
                if (!info) return null;
                const val = manualMetrics[code] ?? { current: "", previous: "" };
                return (
                  <div key={code} className="border border-slate-200 rounded-xl p-4 bg-slate-50">
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <span className="text-xs font-black text-violet-600 tracking-widest uppercase">{code}</span>
                        <p className="text-sm font-semibold text-slate-800 mt-0.5">{info.label}</p>
                        <p className="text-xs text-slate-400">{info.description}</p>
                      </div>
                      <span className="badge bg-slate-200 text-slate-600">{info.unit}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="label">Current value</label>
                        <input type="number" value={val.current} title={`${info.label} current value`} placeholder="0"
                          onChange={(e) => setManualMetrics((m) => ({ ...m, [code]: { ...val, current: e.target.value } }))}
                          className="input" />
                      </div>
                      <div>
                        <label className="label">Previous value <span className="text-slate-400 normal-case font-normal">(optional)</span></label>
                        <input type="number" value={val.previous} title={`${info.label} previous value`} placeholder="0"
                          onChange={(e) => setManualMetrics((m) => ({ ...m, [code]: { ...val, previous: e.target.value } }))}
                          className="input" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex gap-3">
            <button onClick={() => setStep(4)} className="btn-secondary flex-1">Back</button>
            <button onClick={() => setStep(6)} className="btn-primary flex-1 py-2.5">Review & confirm</button>
          </div>
        </div>
      )}

      {/* ── Step 6: Review & confirm ── */}
      {step === 6 && (
        <div>
          <div className="space-y-4 mb-5">
            <div className="card p-6">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-4">Profile</p>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
                {([
                  ["Team",        profile.team_name],
                  ["Type",        humanise(profile.team_type ?? "")],
                  ["Role",        humanise(profile.stakeholder_role ?? "")],
                  ["Goal",        humanise(profile.primary_goal ?? "")],
                  ["Decision",    humanise(profile.decision_type ?? "")],
                  ["Criticality", humanise(profile.business_criticality ?? "")],
                  ["Horizon",     humanise(profile.time_horizon ?? "")],
                ] as [string, string][]).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-xs text-slate-400 font-semibold">{k}</dt>
                    <dd className="text-sm text-slate-800 font-semibold">{v || "—"}</dd>
                  </div>
                ))}
              </dl>
            </div>

            {selectedMetrics.length > 0 && (
              <div className="card p-6">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">
                  Selected metrics <span className="normal-case font-normal">({selectedMetrics.length})</span>
                </p>
                <div className="flex flex-wrap gap-2">
                  {selectedMetrics.map((m) => (
                    <span key={m.code} className={`badge ${TIER_BADGE_CLASSES[m.tier] ?? "bg-slate-100 text-slate-600"}`}>
                      {m.code}
                      {m.ai_derived && " *"}
                    </span>
                  ))}
                </div>
                {selectedMetrics.some((m) => m.ai_derived) && (
                  <p className="text-xs text-slate-400 mt-2">* AI-derived formula</p>
                )}
              </div>
            )}

            {manualKpis.length > 0 && (
              <div className="card p-6">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">
                  Declared KPIs <span className="normal-case font-normal">({manualKpis.length})</span>
                </p>
                <div className="space-y-1">
                  {manualKpis.map((k, i) => (
                    <p key={i} className="text-sm text-slate-700">
                      <span className="font-semibold">{k.name}</span>: {k.value} {k.unit}
                      <span className="text-slate-400 ml-1">({k.threshold_type})</span>
                    </p>
                  ))}
                </div>
              </div>
            )}

            {manualCodes.some((c) => manualMetrics[c]?.current) && (
              <div className="card p-6">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">Manual metrics</p>
                <div className="space-y-1">
                  {manualCodes.filter((c) => manualMetrics[c]?.current).map((c) => (
                    <p key={c} className="text-sm text-slate-700">
                      <span className="font-mono font-bold text-violet-600 text-xs">{c}</span>
                      <span className="ml-2">{manualMetrics[c].current} {MANUAL_METRIC_INFO[c]?.unit}</span>
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <button onClick={() => setStep(5)} className="btn-secondary flex-1">Back</button>
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="flex-1 bg-emerald-600 text-white rounded-lg px-4 py-2.5 text-sm font-semibold hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? "Setting up…" : "Confirm and start"}
            </button>
          </div>
        </div>
      )}

      {/* ── Catalog modal ── */}
      {showCatalog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={(e) => { if (e.target === e.currentTarget) setShowCatalog(false); }}
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col mx-4">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-200">
              <h3 className="text-base font-bold text-slate-900">Metric catalog</h3>
              <button
                type="button"
                onClick={() => setShowCatalog(false)}
                className="text-slate-400 hover:text-slate-600"
                aria-label="Close catalog"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Tabs */}
            <div className="flex gap-0 px-6 pt-4 border-b border-slate-200">
              {(["standard", "external"] as const).map((tab) => {
                const labels = { standard: "Standard", external: "Requires external data" };
                return (
                  <button
                    key={tab}
                    onClick={() => setCatalogTab(tab)}
                    className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
                      catalogTab === tab
                        ? "border-violet-600 text-violet-600"
                        : "border-transparent text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    {labels[tab]}
                  </button>
                );
              })}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {!catalogData ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => <div key={i} className="h-12 bg-slate-100 rounded-lg" />)}
                </div>
              ) : catalogTab === "standard" ? (
                <div className="space-y-2">
                  {catalogData.standard
                    .filter((e) => !selectedCodes.has(e.code))
                    .map((entry) => (
                      <div key={entry.code} className="flex items-center gap-3 border border-slate-200 rounded-xl px-4 py-3">
                        <span className="text-xs font-black text-slate-700 tracking-widest uppercase w-14 flex-shrink-0">{entry.code}</span>
                        <div className="flex-1 min-w-0">
                          <span className="text-sm font-semibold text-slate-800">{entry.name}</span>
                          {entry.formula && <p className="text-xs text-slate-400 truncate">{entry.formula}</p>}
                        </div>
                        <span className={`badge flex-shrink-0 ${TIER_BADGE_CLASSES[entry.tier] ?? "bg-slate-100 text-slate-600"}`}>{entry.tier}</span>
                        <button
                          onClick={() => addFromCatalog(entry)}
                          className="btn-primary flex-shrink-0 px-3 py-1.5 text-xs"
                        >+ Add</button>
                      </div>
                    ))}
                  {catalogData.standard.filter((e) => !selectedCodes.has(e.code)).length === 0 && (
                    <p className="text-sm text-slate-400 text-center py-6">All standard metrics already selected.</p>
                  )}
                </div>
              ) : (
                /* External data tab */
                <div className="space-y-2">
                  {catalogData.external_required.map((entry) => (
                    <div key={entry.code} className="flex items-start gap-3 border border-slate-200 rounded-xl px-4 py-3 bg-slate-50">
                      <span className="text-xs font-black text-slate-400 tracking-widest uppercase w-14 flex-shrink-0 mt-0.5">{entry.code}</span>
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-semibold text-slate-600">{entry.name}</span>
                        <p className="text-xs text-slate-400 mt-0.5">{entry.reason}</p>
                      </div>
                      <span
                        className="flex-shrink-0 mt-0.5 text-slate-400"
                        title={entry.reason}
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
