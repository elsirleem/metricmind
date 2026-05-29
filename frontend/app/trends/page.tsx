"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import axios from "axios";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";
import { getMetrics, recomputeMetrics, MetricRecord } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type CommitDay    = { date: string; count: number };
type PipelineDay  = { date: string; success: number; failed: number; other: number };
type MrDay        = { date: string; opened: number; merged: number; closed: number };

interface EventSeries {
  commits:   CommitDay[];
  pipelines: PipelineDay[];
  mrs:       MrDay[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortDate(iso: string) {
  const [, m, d] = iso.split("-");
  const months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(m)]} ${parseInt(d)}`;
}

function fmtVal(v: number | null | undefined, decimals = 1): string {
  if (v === undefined || v === null) return "—";
  return v % 1 === 0 ? String(v) : v.toFixed(decimals);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SummaryTile({
  label, value, unit, status,
}: { label: string; value: string; unit: string; status?: string }) {
  const statusColor: Record<string, string> = {
    breach:  "text-[#DC2626]",
    warning: "text-[#D97706]",
    within:  "text-[#16A34A]",
  };
  return (
    <div className="card p-4 flex flex-col gap-1">
      <p className="text-xs font-bold text-slate-400 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-black tabular-nums ${status ? statusColor[status] ?? "text-slate-900" : "text-slate-900"}`}>
        {value}
      </p>
      <p className="text-xs text-slate-400">{unit}</p>
    </div>
  );
}

function ChartShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">{title}</p>
      <div className="h-[220px]">{children}</div>
    </div>
  );
}

function EmptyChart({ title }: { title: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">{title}</p>
      <div className="h-[220px] flex items-center justify-center bg-slate-50 rounded-lg">
        <p className="text-sm text-slate-400">No data — run an analysis first</p>
      </div>
    </div>
  );
}

function Skeleton() {
  return <div className="h-[220px] bg-slate-100 rounded-xl animate-pulse" />;
}

// ---------------------------------------------------------------------------
// Main page content
// ---------------------------------------------------------------------------

function TrendsContent() {
  const params    = useSearchParams();
  const profileId = params.get("profile_id") ?? "";

  const [metrics, setMetrics]           = useState<MetricRecord[]>([]);
  const [series, setSeries]             = useState<EventSeries | null>(null);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState("");
  const [periodBoundary, setPeriodBoundary] = useState<string | null>(null);
  const [refreshing, setRefreshing]     = useState(false);

  const handleRefresh = async () => {
    if (!profileId || refreshing) return;
    setRefreshing(true); setError("");
    try {
      await recomputeMetrics(profileId);
      const fresh = await getMetrics(profileId);
      setMetrics(fresh);
    } catch (e) {
      setError("Refresh failed — see console.");
      console.error(e);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    try {
      const stored = localStorage.getItem("tw_c_start");
      if (stored) setPeriodBoundary(stored.slice(0, 10));
    } catch { /* localStorage unavailable */ }
  }, []);

  useEffect(() => {
    if (!profileId) { setLoading(false); return; }

    Promise.all([
      getMetrics(profileId),
      axios
        .get<EventSeries>(`${API_BASE}/api/metrics/${profileId}/event-series?days=90`)
        .then((r) => r.data),
    ])
      .then(([m, s]) => { setMetrics(m); setSeries(s); })
      .catch((e) => { setError("Failed to load trend data."); console.error(e); })
      .finally(() => setLoading(false));
  }, [profileId]);

  const getMetricVal = (code: string) => metrics.find((m) => m.code === code);

  // MTTR: show "—" when value is null/undefined/0 (0 = no incidents)
  function fmtMttr(v: number | null | undefined): string {
    if (v === undefined || v === null || v === 0) return "—";
    return fmtVal(v, 0);
  }

  if (!profileId) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-400 text-sm">No profile selected. Open this page from the Dashboard.</p>
      </main>
    );
  }

  const commits   = series?.commits   ?? [];
  const pipelines = series?.pipelines ?? [];
  const mrs       = series?.mrs       ?? [];

  return (
    <main className="min-h-screen bg-slate-50">
      {/* Top bar */}
      <header style={{ backgroundColor: "var(--sbp-navy)", borderBottom: "1px solid #1B6EF3" }}>
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "#1B6EF3" }}>
              <span className="text-white text-sm font-black">M</span>
            </Link>
            <div>
              <h1 className="text-base font-bold leading-none" style={{ color: "#FFFFFF" }}>Trends</h1>
              {profileId && <p className="text-xs mt-0.5 font-mono" style={{ color: "#6B7280" }}>{profileId}</p>}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {profileId && (
              <>
                <button
                  type="button"
                  onClick={handleRefresh}
                  disabled={refreshing}
                  className="text-sm font-medium px-3 py-1.5 rounded-lg border border-white/20 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition"
                  style={{ color: "#FFFFFF" }}
                  title="Re-run metric computation on the latest ingested data"
                >
                  {refreshing ? "Refreshing…" : "Refresh metrics"}
                </button>
                <Link href={`/dashboard?profile_id=${profileId}`} className="text-sm font-medium" style={{ color: "#FFFFFF" }}>Dashboard</Link>
                <Link href={`/intelligence?profile_id=${profileId}`} className="text-sm font-medium" style={{ color: "#FFFFFF" }}>Intelligence</Link>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-12">
        {error && (
          <div className="p-4 rounded-xl text-sm" style={{ backgroundColor: "#FEF2F2", border: "1px solid #DC2626", color: "#7F1D1D" }}>{error}</div>
        )}

        {/* ── Section 1: Pipeline health ─────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-5">
            <span className="w-1 h-5 rounded-full" style={{ backgroundColor: "#1B6EF3" }} />
            <h2 className="text-sm font-bold uppercase tracking-wide" style={{ color: "#0A1628" }}>Pipeline Health</h2>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            {loading ? [1,2,3].map((i) => <div key={i} className="h-[88px] bg-slate-100 rounded-xl animate-pulse" />) : (
              <>
                {getMetricVal("CFR") && <SummaryTile label="CFR"  value={fmtVal(getMetricVal("CFR")?.current_value)}   unit="% change failure rate"  status={getMetricVal("CFR")?.threshold_status} />}
                {getMetricVal("DF")  && <SummaryTile label="DF"   value={fmtVal(getMetricVal("DF")?.current_value, 0)}  unit="deployments"             status={getMetricVal("DF")?.threshold_status} />}
                {getMetricVal("CQI") && <SummaryTile label="CQI"  value={fmtVal(getMetricVal("CQI")?.current_value)}   unit="% code quality index"    status={getMetricVal("CQI")?.threshold_status} />}
              </>
            )}
          </div>

          {/* Pipeline runs per day */}
          {loading ? <Skeleton /> : pipelines.length === 0 ? (
            <EmptyChart title="Pipeline runs per day" />
          ) : (
            <ChartShell title="Pipeline runs per day (success vs failed)">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pipelines.map((p) => ({ ...p, date: shortDate(p.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {periodBoundary && (
                    <ReferenceLine x={shortDate(periodBoundary)} stroke="#1B6EF3" strokeDasharray="6 3" strokeWidth={1.5}
                      label={{ value: "current period", fontSize: 9, fill: "#1B6EF3", position: "insideTopRight" }} />
                  )}
                  <Bar dataKey="success" stackId="a" fill="#16A34A" name="Success" radius={[0,0,0,0]} />
                  <Bar dataKey="failed"  stackId="a" fill="#DC2626" name="Failed"  radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartShell>
          )}
        </section>

        {/* ── Section 2: MR and flow ─────────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-5">
            <span className="w-1 h-5 rounded-full bg-violet-500" />
            <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wide">Merge Requests &amp; Flow</h2>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            {loading ? [1,2,3].map((i) => <div key={i} className="h-[88px] bg-slate-100 rounded-xl animate-pulse" />) : (
              <>
                {/* MTTR always rendered — "no incidents recorded" is informative context, not a missing-data error */}
                <SummaryTile label="MTTR" value={fmtMttr(getMetricVal("MTTR")?.current_value)} unit={getMetricVal("MTTR")?.current_value ? "hours mean time to recover" : "no incidents recorded"} status={getMetricVal("MTTR") ? getMetricVal("MTTR")?.threshold_status : undefined} />
                {getMetricVal("PRCT") && <SummaryTile label="PRCT" value={fmtVal(getMetricVal("PRCT")?.current_value, 0)} unit="hours PR cycle time"  status={getMetricVal("PRCT")?.threshold_status} />}
                {getMetricVal("PR")   && <SummaryTile label="PR"   value={fmtVal(getMetricVal("PR")?.current_value, 0)}   unit="pull requests"       status={getMetricVal("PR")?.threshold_status} />}
              </>
            )}
          </div>

          {/* MRs per day */}
          {loading ? <Skeleton /> : mrs.length === 0 ? (
            <EmptyChart title="Merge requests per day" />
          ) : (
            <ChartShell title="Merge requests per day (opened vs merged)">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={mrs.map((m) => ({ ...m, date: shortDate(m.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {periodBoundary && (
                    <ReferenceLine x={shortDate(periodBoundary)} stroke="#1B6EF3" strokeDasharray="6 3" strokeWidth={1.5}
                      label={{ value: "current period", fontSize: 9, fill: "#1B6EF3", position: "insideTopRight" }} />
                  )}
                  <Bar dataKey="opened" fill="#1B6EF3" name="Opened" radius={[3,3,0,0]} />
                  <Bar dataKey="merged" fill="#0B7A5E" name="Merged" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartShell>
          )}
        </section>

        {/* ── Section 3: Team sustainability ────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-5">
            <span className="w-1 h-5 rounded-full" style={{ backgroundColor: "#16A34A" }} />
            <h2 className="text-sm font-bold uppercase tracking-wide" style={{ color: "#0A1628" }}>Team Sustainability</h2>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            {loading ? [1,2,3,4].map((i) => <div key={i} className="h-[88px] bg-slate-100 rounded-xl animate-pulse" />) : (
              <>
                {getMetricVal("AHCR") && <SummaryTile label="AHCR" value={fmtVal(getMetricVal("AHCR")?.current_value)}    unit="% commits after hours"    status={getMetricVal("AHCR")?.threshold_status} />}
                {getMetricVal("BUR")  && <SummaryTile label="BUR"  value={fmtVal(getMetricVal("BUR")?.current_value)}     unit="% team at risk (>3 AH)"   status={getMetricVal("BUR")?.threshold_status} />}
                {getMetricVal("MIC")  && <SummaryTile label="MIC"  value={fmtVal(getMetricVal("MIC")?.current_value, 0)}  unit="open stale bugs"          status={getMetricVal("MIC")?.threshold_status} />}
                {getMetricVal("BF")   && <SummaryTile label="BF"   value={fmtVal(getMetricVal("BF")?.current_value)}      unit="% bus factor"             status={getMetricVal("BF")?.threshold_status} />}
              </>
            )}
          </div>

          {/* Commits per day */}
          {loading ? <Skeleton /> : commits.length === 0 ? (
            <EmptyChart title="Commits per day" />
          ) : (
            <ChartShell title="Commits per day">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={commits.map((c) => ({ ...c, date: shortDate(c.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                  {periodBoundary && (
                    <ReferenceLine x={shortDate(periodBoundary)} stroke="#1B6EF3" strokeDasharray="6 3" strokeWidth={1.5}
                      label={{ value: "current period", fontSize: 9, fill: "#1B6EF3", position: "insideTopRight" }} />
                  )}
                  <Bar dataKey="count" fill="#16A34A" name="Commits" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartShell>
          )}
        </section>

        <div className="pb-8">
          <Link href="/" className="text-sm text-slate-400 hover:text-slate-600">Back to home</Link>
        </div>
      </div>
    </main>
  );
}

export default function TrendsPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-50 flex items-center justify-center"><p className="text-slate-400 text-sm">Loading…</p></main>}>
      <TrendsContent />
    </Suspense>
  );
}
