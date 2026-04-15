"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getMetricCatalog } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CatalogMetric {
  code: string;
  name: string;
  tier: string;
  unit?: string;
  source?: string;
  formula?: string;
  why?: string;
  space_dimension?: string;
  periodic_group?: string;
  reason?: string;
}

interface Catalog {
  standard: CatalogMetric[];
  external_required: CatalogMetric[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GROUP_COLORS: Record<string, string> = {
  A: "#0B7A5E",
  B: "#1B6EF3",
  C: "#4B55C8",
  D: "#E8522A",
  E: "#D97706",
  F: "#16A34A",
};

const GROUP_LABELS: Record<string, string> = {
  A: "A. Perception",
  B: "B. People Dynamics",
  C: "C. Performance",
  D: "D. Activity",
  E: "E. Collaboration",
  F: "F. Efficiency & Flow",
};

const SOURCE_ICONS: Record<string, string> = {
  source_control:  "■",
  cicd:            "●",
  project_tracking:"▶",
  static_analysis: "★",
  telemetry:       "◆",
  itsm:            "✦",
  human_input:     "▲",
  survey:          "▲",
  hr_system:       "▲",
  crm:             "▶",
  finance:         "◆",
};

const SOURCE_LABELS: Record<string, string> = {
  source_control:  "Source Control",
  cicd:            "CI/CD",
  project_tracking:"Project Tracking",
  static_analysis: "Static Analysis",
  telemetry:       "Telemetry",
  itsm:            "ITSM",
  human_input:     "Human Input",
  survey:          "Survey",
  hr_system:       "HR System",
  crm:             "CRM",
  finance:         "Finance",
};

// Metrics that appear in each use case (from SELECTION_MATRIX)
const METRIC_USE_CASES: Record<string, string[]> = {
  CFR:  ["Release readiness", "Team health review", "Stakeholder reporting", "Security posture"],
  DF:   ["Release readiness", "Sprint planning", "Stakeholder reporting"],
  MTTR: ["Release readiness", "Team health review", "Stakeholder reporting"],
  CQI:  ["Release readiness", "Security posture"],
  LTfC: ["Sprint planning", "Stakeholder reporting"],
  PRCT: ["Sprint planning", "Team health review", "Security posture"],
  PRSi: ["Sprint planning"],
  TWiP: ["Sprint planning"],
  BUR:  ["Release readiness", "Sprint planning", "Team health review", "Stakeholder reporting", "Security posture"],
  MIC:  ["Release readiness", "Sprint planning", "Team health review", "Stakeholder reporting", "Security posture"],
  BF:   ["Release readiness", "Team health review"],
};

function groupPrefix(pg: string | undefined): string {
  if (!pg) return "";
  return pg.charAt(0).toUpperCase();
}

function groupColor(pg: string | undefined): string {
  return GROUP_COLORS[groupPrefix(pg)] ?? "#94a3b8";
}

// ---------------------------------------------------------------------------
// MetricTile
// ---------------------------------------------------------------------------

function MetricTile({
  metric,
  isExternal,
  onClick,
}: {
  metric: CatalogMetric;
  isExternal: boolean;
  onClick: () => void;
}) {
  const color = groupColor(metric.periodic_group);
  const prefix = groupPrefix(metric.periodic_group);
  const sourceIcon = SOURCE_ICONS[metric.source ?? ""] ?? "○";

  return (
    <div
      onClick={onClick}
      className="relative bg-white rounded-xl border border-slate-200 p-4 cursor-pointer hover:shadow-md transition-shadow"
      style={{ borderLeft: `3px solid ${color}` }}
    >
      {isExternal && (
        <div className="absolute inset-0 bg-slate-50/80 rounded-xl flex items-center justify-center z-10">
          <span className="text-xs font-semibold text-slate-400 bg-white border border-slate-200 px-2 py-1 rounded-lg">
            Requires external data
          </span>
        </div>
      )}
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs font-black text-slate-700 tracking-widest uppercase">{metric.code}</span>
        <span className="text-base" title={SOURCE_LABELS[metric.source ?? ""] ?? metric.source}>{sourceIcon}</span>
      </div>
      <p className="text-sm font-semibold text-slate-800 leading-snug mb-3">{metric.name}</p>
      <div className="flex items-center justify-between gap-2">
        {metric.periodic_group ? (
          <span
            className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-bold text-white"
            style={{ backgroundColor: color }}
          >
            {metric.periodic_group}
          </span>
        ) : (
          <span />
        )}
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-full"
          style={
            metric.tier === "devops"
              ? { backgroundColor: "#EBF2FE", color: "#0A1628", border: "1px solid #1B6EF3" }
              : metric.tier === "sustainability"
              ? { backgroundColor: "#E8F5E9", color: "#14532D", border: "1px solid #16A34A" }
              : { backgroundColor: "#F5F5F5", color: "#374151", border: "1px solid #6B7280" }
          }
        >
          {metric.tier}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MetricDrawer
// ---------------------------------------------------------------------------

function MetricDrawer({
  metric,
  isExternal,
  onClose,
}: {
  metric: CatalogMetric;
  isExternal: boolean;
  onClose: () => void;
}) {
  const color = groupColor(metric.periodic_group);
  const prefix = groupPrefix(metric.periodic_group);
  const groupLabel = GROUP_LABELS[prefix] ?? metric.periodic_group ?? "";
  const sourceIcon = SOURCE_ICONS[metric.source ?? ""] ?? "○";
  const sourceLabel = SOURCE_LABELS[metric.source ?? ""] ?? metric.source ?? "";
  const useCases = METRIC_USE_CASES[metric.code] ?? [];

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-slate-900/30 z-40"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed top-0 right-0 h-full w-full max-w-[480px] bg-white shadow-2xl z-50 overflow-y-auto flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 flex-shrink-0" style={{ backgroundColor: "#0A1628", borderBottom: "1px solid #1B6EF3" }}>
          <div className="flex items-center gap-2">
            {metric.periodic_group && (
              <span
                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold text-white"
                style={{ backgroundColor: color }}
              >
                {metric.periodic_group}
              </span>
            )}
            <span className="text-sm font-semibold" style={{ color: "#FFFFFF" }}>{groupLabel}</span>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg" style={{ color: "#6B7280" }}>
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Top section */}
        <div className="grid grid-cols-2 gap-4 p-6 border-b border-slate-100">
          {/* Left */}
          <div className="flex flex-col gap-3">
            <h2 className="text-xl font-black text-slate-900 leading-tight">{metric.name}</h2>
            {metric.why && <p className="text-sm text-slate-600 leading-relaxed">{metric.why}</p>}
            <hr className="border-slate-200" />
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-400">{sourceIcon}</span>
              <span className="text-sm text-slate-600 font-medium">{sourceLabel}</span>
            </div>
            {metric.unit && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-400">◈</span>
                <span className="text-sm text-slate-600 font-medium">{metric.unit}</span>
              </div>
            )}
          </div>

          {/* Right — gradient card */}
          <div
            className="rounded-xl p-4 flex flex-col justify-between min-h-[140px]"
            style={{ background: `linear-gradient(135deg, ${color}22 0%, ${color}44 100%)`, border: `1px solid ${color}33` }}
          >
            <div className="flex justify-between items-start">
              <span className="text-2xl">{sourceIcon}</span>
              {metric.unit && <span className="text-xs font-semibold text-slate-500 bg-white/60 px-2 py-0.5 rounded-full">{metric.unit}</span>}
            </div>
            <div>
              <p className="text-4xl font-black tracking-tight" style={{ color }}>{metric.code}</p>
              <p className="text-xs font-semibold text-slate-600 mt-1 leading-snug">{metric.name}</p>
            </div>
          </div>
        </div>

        {/* Bottom section */}
        <div className="grid grid-cols-2 gap-6 p-6 flex-1">
          {/* Left — formula */}
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">Why this metric matters</p>
            {metric.why && <p className="text-sm text-slate-600 mb-4">{metric.why}</p>}
            {metric.reason && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
                <p className="text-xs text-amber-700">{metric.reason}</p>
              </div>
            )}
            {metric.formula && !isExternal && (
              <>
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Formula</p>
                <p className="text-xs font-mono text-slate-700 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 leading-relaxed">
                  {metric.formula}
                </p>
              </>
            )}
          </div>

          {/* Right — use cases */}
          <div>
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">Use cases</p>
            {useCases.length > 0 ? (
              <div className="flex flex-col gap-2">
                {useCases.map((uc) => (
                  <span
                    key={uc}
                    className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-100 w-fit"
                  >
                    {uc}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 italic">Available in catalog — not currently in any use case</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-6 py-4 border-t border-slate-200 flex-shrink-0">
          {metric.space_dimension && (
            <span className="badge bg-slate-100 text-slate-600">{metric.space_dimension}</span>
          )}
          {metric.periodic_group && (
            <span
              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold text-white"
              style={{ backgroundColor: color }}
            >
              {metric.periodic_group}
            </span>
          )}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const TIER_FILTERS = [
  { value: "all",           label: "All" },
  { value: "devops",        label: "DevOps" },
  { value: "sustainability",label: "Sustainability" },
  { value: "business",      label: "Business" },
  { value: "external",      label: "External" },
];

const GROUP_FILTERS = [
  { value: "all", label: "All groups" },
  { value: "A",   label: "A. Perception" },
  { value: "B",   label: "B. People Dynamics" },
  { value: "C",   label: "C. Performance" },
  { value: "D",   label: "D. Activity" },
  { value: "E",   label: "E. Collaboration" },
  { value: "F",   label: "F. Efficiency & Flow" },
];

const SOURCE_FILTERS = [
  { value: "all",             label: "All sources" },
  { value: "cicd",            label: "CI/CD" },
  { value: "source_control",  label: "Source Control" },
  { value: "project_tracking",label: "Project Tracking" },
  { value: "human_input",     label: "Human Input" },
  { value: "static_analysis", label: "Static Analysis" },
  { value: "telemetry",       label: "Telemetry" },
  { value: "itsm",            label: "ITSM" },
];

function PillFilter({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors ${
            value === opt.value
              ? "bg-violet-600 text-white border-violet-600"
              : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export default function CatalogPage() {
  const [catalog, setCatalog]         = useState<Catalog | null>(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState("");
  const [tierFilter, setTierFilter]   = useState("all");
  const [groupFilter, setGroupFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [search, setSearch]           = useState("");
  const [selected, setSelected]       = useState<{ metric: CatalogMetric; isExternal: boolean } | null>(null);

  const loadCatalog = async () => {
    setLoading(true); setError("");
    try {
      const data = await getMetricCatalog();
      setCatalog(data as unknown as Catalog);
    } catch {
      setError("Failed to load catalog. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadCatalog(); }, []);

  const allMetrics: { metric: CatalogMetric; isExternal: boolean }[] = catalog
    ? [
        ...catalog.standard.map((m) => ({ metric: m, isExternal: false })),
        ...catalog.external_required.map((m) => ({ metric: m, isExternal: true })),
      ]
    : [];

  const filtered = allMetrics.filter(({ metric, isExternal }) => {
    if (tierFilter !== "all") {
      if (tierFilter === "external") {
        if (!isExternal) return false;
      } else {
        if (isExternal) return false;
        if (metric.tier !== tierFilter) return false;
      }
    }
    if (groupFilter !== "all") {
      if (groupPrefix(metric.periodic_group) !== groupFilter) return false;
    }
    if (sourceFilter !== "all") {
      if (metric.source !== sourceFilter) return false;
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      if (!metric.code.toLowerCase().includes(q) && !metric.name.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  return (
    <main className="min-h-screen bg-slate-50">
      {/* Nav */}
      <header style={{ backgroundColor: "var(--sbp-navy)", borderBottom: "1px solid #1B6EF3" }}>
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "#1B6EF3" }}>
              <span className="text-white text-sm font-black">M</span>
            </Link>
            <div>
              <h1 className="text-base font-bold leading-none" style={{ color: "#FFFFFF" }}>Metric Catalog</h1>
              <p className="text-xs mt-0.5" style={{ color: "#6B7280" }}>Periodic System of DevOps Metrics</p>
            </div>
          </div>
          <nav className="flex items-center gap-4">
            <Link href="/" className="text-sm font-medium" style={{ color: "#FFFFFF" }}>Home</Link>
            <Link href="/catalog" className="text-sm font-semibold" style={{ color: "#1B6EF3" }}>Catalog</Link>
          </nav>
        </div>
      </header>

      {/* Page header */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-black text-slate-900 mb-1">Metric Catalog</h2>
          <p className="text-sm text-slate-500">Browse all metrics available in MetricMind, grounded in the Periodic System of DevOps Metrics.</p>
        </div>

        {/* Filter bar */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 mb-6 space-y-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 space-y-3">
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Tier</p>
                <PillFilter options={TIER_FILTERS} value={tierFilter} onChange={setTierFilter} />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Periodic Group</p>
                <PillFilter options={GROUP_FILTERS} value={groupFilter} onChange={setGroupFilter} />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Data Source</p>
                <PillFilter options={SOURCE_FILTERS} value={sourceFilter} onChange={setSourceFilter} />
              </div>
            </div>
            <div className="sm:w-56">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Search</p>
              <input
                type="text"
                placeholder="Code or name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Active filter chips */}
          {(tierFilter !== "all" || groupFilter !== "all" || sourceFilter !== "all" || search.trim()) && (
            <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100">
              {tierFilter !== "all" && (
                <span className="inline-flex items-center gap-1 bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 rounded-full text-xs font-semibold">
                  Tier: {tierFilter}
                  <button onClick={() => setTierFilter("all")} className="hover:text-violet-900 ml-0.5">×</button>
                </span>
              )}
              {groupFilter !== "all" && (
                <span className="inline-flex items-center gap-1 bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 rounded-full text-xs font-semibold">
                  Group: {groupFilter}
                  <button onClick={() => setGroupFilter("all")} className="hover:text-violet-900 ml-0.5">×</button>
                </span>
              )}
              {sourceFilter !== "all" && (
                <span className="inline-flex items-center gap-1 bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 rounded-full text-xs font-semibold">
                  Source: {SOURCE_LABELS[sourceFilter] ?? sourceFilter}
                  <button onClick={() => setSourceFilter("all")} className="hover:text-violet-900 ml-0.5">×</button>
                </span>
              )}
              {search.trim() && (
                <span className="inline-flex items-center gap-1 bg-violet-50 text-violet-700 border border-violet-200 px-2.5 py-1 rounded-full text-xs font-semibold">
                  Search: {search}
                  <button onClick={() => setSearch("")} className="hover:text-violet-900 ml-0.5">×</button>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Loading */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 h-28 animate-pulse">
                <div className="h-3 bg-slate-100 rounded w-16 mb-3" />
                <div className="h-4 bg-slate-100 rounded w-full mb-2" />
                <div className="h-3 bg-slate-100 rounded w-24" />
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="text-center py-16">
            <p className="text-rose-600 text-sm mb-4">{error}</p>
            <button onClick={loadCatalog} className="text-violet-600 text-sm font-semibold hover:underline">Retry</button>
          </div>
        )}

        {/* Grid */}
        {!loading && !error && (
          <>
            <p className="text-xs text-slate-400 mb-4">{filtered.length} metrics</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {filtered.map(({ metric, isExternal }) => (
                <MetricTile
                  key={metric.code}
                  metric={metric}
                  isExternal={isExternal}
                  onClick={() => setSelected({ metric, isExternal })}
                />
              ))}
            </div>
            {filtered.length === 0 && (
              <p className="text-sm text-slate-400 text-center py-16">No metrics match the current filters.</p>
            )}
          </>
        )}
      </div>

      {/* Detail drawer */}
      {selected && (
        <MetricDrawer
          metric={selected.metric}
          isExternal={selected.isExternal}
          onClose={() => setSelected(null)}
        />
      )}
    </main>
  );
}
