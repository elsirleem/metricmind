"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import axios from "axios";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";
import { getMetrics, MetricRecord } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type HistoryPoint = { date: string; value: number };
type MetricHistory = { metric_code: string; series: HistoryPoint[] };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortDate(iso: string) {
  // "2026-02-05" → "Feb 5"
  const [, m, d] = iso.split("-");
  const months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parseInt(m)]} ${parseInt(d)}`;
}

function fmtVal(v: number | undefined, decimals = 1) {
  if (v === undefined || v === null) return "—";
  return v % 1 === 0 ? String(v) : v.toFixed(decimals);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SummaryTile({
  label,
  value,
  unit,
  status,
}: {
  label: string;
  value: string;
  unit: string;
  status?: string;
}) {
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

function ChartCard({
  title,
  series,
  children,
}: {
  title: string;
  series: HistoryPoint[];
  children: React.ReactNode;
}) {
  if (series.length < 2) {
    return (
      <div className="card p-4">
        <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">{title}</p>
        <div className="h-[200px] flex items-center justify-center bg-slate-50 rounded-lg">
          <p className="text-sm text-slate-400">Not enough data</p>
        </div>
      </div>
    );
  }
  return (
    <div className="card p-4">
      <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">{title}</p>
      <div className="h-[200px]">{children}</div>
    </div>
  );
}

function Skeleton() {
  return <div className="h-[200px] bg-slate-100 rounded-xl" />;
}

// ---------------------------------------------------------------------------
// Main page content
// ---------------------------------------------------------------------------

function TrendsContent() {
  const params    = useSearchParams();
  const profileId = params.get("profile_id") ?? "";

  const [metrics, setMetrics]       = useState<MetricRecord[]>([]);
  const [history, setHistory]       = useState<MetricHistory[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState("");
  const [periodBoundary, setPeriodBoundary] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("tw_c_start");
      if (stored) {
        // Convert ISO datetime to YYYY-MM-DD for Recharts XAxis comparison
        setPeriodBoundary(stored.slice(0, 10));
      }
    } catch {
      // localStorage unavailable
    }
  }, []);

  useEffect(() => {
    if (!profileId) { setLoading(false); return; }

    const codes = "CFR,DF,CQI,MTTR,PRCT,LTfC,PR,BUR,MIC,BF,BLDS";

    Promise.all([
      getMetrics(profileId),
      axios
        .get<MetricHistory[]>(
          `${API_BASE}/api/metrics/${profileId}/history?metric_codes=${codes}&days=60`
        )
        .then((r) => r.data),
    ])
      .then(([m, h]) => { setMetrics(m); setHistory(h); })
      .catch((e) => { setError("Failed to load trend data."); console.error(e); })
      .finally(() => setLoading(false));
  }, [profileId]);

  const getSeries = (code: string): HistoryPoint[] =>
    history.find((h) => h.metric_code === code)?.series ?? [];

  const getMetricVal = (code: string) => metrics.find((m) => m.code === code);

  // Merge two series onto a shared date axis
  function mergeSeries(
    codeA: string,
    codeB: string,
    keyA: string,
    keyB: string,
  ): Record<string, unknown>[] {
    const dateSet = new Set<string>();
    getSeries(codeA).forEach((p) => dateSet.add(p.date));
    getSeries(codeB).forEach((p) => dateSet.add(p.date));
    const mapA = Object.fromEntries(getSeries(codeA).map((p) => [p.date, p.value]));
    const mapB = Object.fromEntries(getSeries(codeB).map((p) => [p.date, p.value]));
    return Array.from(dateSet)
      .sort()
      .map((d) => ({ date: d, [keyA]: mapA[d], [keyB]: mapB[d] }));
  }

  // ---------------------------------------------------------------------------
  // Render states
  // ---------------------------------------------------------------------------

  if (!profileId) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-400 text-sm">No profile selected. Open this page from the Dashboard.</p>
      </main>
    );
  }

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
                <Link href={`/dashboard?profile_id=${profileId}`} className="text-sm font-medium" style={{ color: "#FFFFFF" }}>
                  Dashboard
                </Link>
                <Link href={`/intelligence?profile_id=${profileId}`} className="text-sm font-medium" style={{ color: "#FFFFFF" }}>
                  Intelligence
                </Link>
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

          {/* Summary row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            {loading ? (
              [1, 2, 3].map((i) => <div key={i} className="h-[88px] bg-slate-100 rounded-xl" />)
            ) : (
              <>
                <SummaryTile label="CFR"  value={fmtVal(getMetricVal("CFR")?.current_value)}  unit="% change failure rate" status={getMetricVal("CFR")?.threshold_status} />
                <SummaryTile label="DF"   value={fmtVal(getMetricVal("DF")?.current_value, 0)} unit="deployments"           status={getMetricVal("DF")?.threshold_status} />
                <SummaryTile label="CQI"  value={fmtVal(getMetricVal("CQI")?.current_value)}  unit="% code quality index"  status={getMetricVal("CQI")?.threshold_status} />
              </>
            )}
          </div>

          {/* CFR + CQI line chart */}
          {loading ? (
            <Skeleton />
          ) : (
            <ChartCard title="CFR & CQI over time" series={[...getSeries("CFR"), ...getSeries("CQI")]}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={mergeSeries("CFR", "CQI", "CFR", "CQI")} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <Tooltip
                    labelFormatter={shortDate}
                    formatter={(v: number, name: string) => [`${fmtVal(v)}%`, name]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine y={0.15} stroke="#D97706" strokeDasharray="4 4" label={{ value: "CFR warn 0.15%", fontSize: 10, fill: "#D97706" }} />
                  {periodBoundary && (
                    <ReferenceLine x={periodBoundary} stroke="#1B6EF3" strokeDasharray="6 3" strokeWidth={1.5} label={{ value: "current period start", fontSize: 9, fill: "#1B6EF3", position: "insideTopRight" }} />
                  )}
                  <Line type="monotone" dataKey="CFR" stroke="#DC2626" strokeWidth={2} dot={false} name="CFR (%)" />
                  <Line type="monotone" dataKey="CQI" stroke="#1B6EF3" strokeWidth={2} dot={false} name="CQI (%)" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* DF bar chart */}
          {loading ? (
            <div className="h-[200px] bg-slate-100 rounded-xl mt-4" />
          ) : (
            <div className="mt-4">
              <ChartCard title="Deployment frequency over time" series={getSeries("DF")}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={getSeries("DF").map((p) => ({ ...p, date: shortDate(p.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                    <Bar dataKey="value" fill="#1B6EF3" radius={[3, 3, 0, 0]} name="Deployments" />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
          )}
        </section>

        {/* ── Section 2: MR and flow ─────────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-5">
            <span className="w-1 h-5 rounded-full bg-violet-500" />
            <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wide">Merge Requests &amp; Flow</h2>
          </div>

          {/* Summary row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            {loading ? (
              [1, 2, 3].map((i) => <div key={i} className="h-[88px] bg-slate-100 rounded-xl" />)
            ) : (
              <>
                <SummaryTile label="MTTR" value={fmtVal(getMetricVal("MTTR")?.current_value, 0)} unit="hours mean time to recover" status={getMetricVal("MTTR")?.threshold_status} />
                <SummaryTile label="PRCT" value={fmtVal(getMetricVal("PRCT")?.current_value, 0)} unit="hours PR cycle time"         status={getMetricVal("PRCT")?.threshold_status} />
                <SummaryTile label="PR"   value={fmtVal(getMetricVal("PR")?.current_value, 0)}   unit="pull requests"               status={getMetricVal("PR")?.threshold_status} />
              </>
            )}
          </div>

          {/* MTTR line chart */}
          {loading ? (
            <Skeleton />
          ) : (
            <ChartCard title="MTTR over time" series={getSeries("MTTR")}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={getSeries("MTTR").map((p) => ({ ...p, date: shortDate(p.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <Tooltip formatter={(v: number) => [`${fmtVal(v, 0)}h`, "MTTR"]} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                  <ReferenceLine y={24} stroke="#D97706" strokeDasharray="4 4" label={{ value: "warn 24h", fontSize: 10, fill: "#D97706" }} />
                  {periodBoundary && (
                    <ReferenceLine x={periodBoundary} stroke="#1B6EF3" strokeDasharray="6 3" strokeWidth={1.5} label={{ value: "current period start", fontSize: 9, fill: "#1B6EF3", position: "insideTopRight" }} />
                  )}
                  <Line type="monotone" dataKey="value" stroke="#1B6EF3" strokeWidth={2} dot={false} name="MTTR (h)" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* PRCT + LTfC line chart */}
          {loading ? (
            <div className="h-[200px] bg-slate-100 rounded-xl mt-4" />
          ) : (
            <div className="mt-4">
              <ChartCard title="PRCT & LTfC over time" series={[...getSeries("PRCT"), ...getSeries("LTfC")]}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={mergeSeries("PRCT", "LTfC", "PRCT", "LTfC")} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <Tooltip
                      labelFormatter={shortDate}
                      formatter={(v: number, name: string) => [`${fmtVal(v, 0)}h`, name]}
                      contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="PRCT" stroke="#1B6EF3" strokeWidth={2} dot={false} name="PRCT (h)" />
                    <Line type="monotone" dataKey="LTfC" stroke="#4B55C8" strokeWidth={2} dot={false} name="LTfC (h)" />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
          )}

          {/* PR bar chart */}
          {loading ? (
            <div className="h-[200px] bg-slate-100 rounded-xl mt-4" />
          ) : (
            <div className="mt-4">
              <ChartCard title="Pull request count over time" series={getSeries("PR")}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={getSeries("PR").map((p) => ({ ...p, date: shortDate(p.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                    <Bar dataKey="value" fill="#1B6EF3" radius={[3, 3, 0, 0]} name="Pull requests" />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
          )}
        </section>

        {/* ── Section 3: Team sustainability ────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-5">
            <span className="w-1 h-5 rounded-full" style={{ backgroundColor: "#16A34A" }} />
            <h2 className="text-sm font-bold uppercase tracking-wide" style={{ color: "#0A1628" }}>Team Sustainability</h2>
          </div>

          {/* Summary row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            {loading ? (
              [1, 2, 3].map((i) => <div key={i} className="h-[88px] bg-slate-100 rounded-xl" />)
            ) : (
              <>
                <SummaryTile label="BUR" value={fmtVal(getMetricVal("BUR")?.current_value)} unit="% burnout rate"    status={getMetricVal("BUR")?.threshold_status} />
                <SummaryTile label="MIC" value={fmtVal(getMetricVal("MIC")?.current_value, 0)} unit="open stale bugs" status={getMetricVal("MIC")?.threshold_status} />
                <SummaryTile label="BF"  value={fmtVal(getMetricVal("BF")?.current_value)}  unit="% bus factor"      status={getMetricVal("BF")?.threshold_status} />
              </>
            )}
          </div>

          {/* BUR line chart */}
          {loading ? (
            <Skeleton />
          ) : (
            <ChartCard title="Burnout rate over time" series={getSeries("BUR")}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={getSeries("BUR").map((p) => ({ ...p, date: shortDate(p.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <Tooltip formatter={(v: number) => [`${fmtVal(v)}%`, "BUR"]} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                  <ReferenceLine y={10} stroke="#D97706" strokeDasharray="4 4" label={{ value: "warn 10%", fontSize: 10, fill: "#D97706" }} />
                  <ReferenceLine y={25} stroke="#DC2626" strokeDasharray="4 4" label={{ value: "breach 25%", fontSize: 10, fill: "#DC2626" }} />
                  {periodBoundary && (
                    <ReferenceLine x={periodBoundary} stroke="#1B6EF3" strokeDasharray="6 3" strokeWidth={1.5} label={{ value: "current period start", fontSize: 9, fill: "#1B6EF3", position: "insideTopRight" }} />
                  )}
                  <Line type="monotone" dataKey="value" stroke="#16A34A" strokeWidth={2} dot={false} name="BUR (%)" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* MIC line chart */}
          {loading ? (
            <div className="h-[200px] bg-slate-100 rounded-xl mt-4" />
          ) : (
            <div className="mt-4">
              <ChartCard title="Maintainability issues over time" series={getSeries("MIC")}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={getSeries("MIC").map((p) => ({ ...p, date: shortDate(p.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <Tooltip formatter={(v: number) => [`${fmtVal(v, 0)}`, "MIC"]} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                    <ReferenceLine y={5} stroke="#D97706" strokeDasharray="4 4" label={{ value: "warn 5", fontSize: 10, fill: "#D97706" }} />
                    <Line type="monotone" dataKey="value" stroke="#16A34A" strokeWidth={2} dot={false} name="MIC" />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
          )}

          {/* Bus Factor bar chart */}
          {loading ? (
            <div className="h-[200px] bg-slate-100 rounded-xl mt-4" />
          ) : (
            <div className="mt-4">
              <ChartCard title="Bus factor over time" series={getSeries("BF")}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={getSeries("BF").map((p) => ({ ...p, date: shortDate(p.date) }))} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} domain={[0, 100]} />
                    <Tooltip formatter={(v: number) => [`${fmtVal(v)}%`, "Bus Factor"]} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }} />
                    <ReferenceLine y={40} stroke="#D97706" strokeDasharray="4 4" label={{ value: "warn 40%", fontSize: 10, fill: "#D97706" }} />
                    <ReferenceLine y={60} stroke="#DC2626" strokeDasharray="4 4" label={{ value: "breach 60%", fontSize: 10, fill: "#DC2626" }} />
                    <Bar dataKey="value" fill="#16A34A" radius={[3, 3, 0, 0]} name="Bus Factor (%)" />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
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
