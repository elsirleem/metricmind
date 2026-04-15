"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import MetricCard from "@/components/MetricCard";
import { MetricRecord, getMetrics, seedDatabase } from "@/lib/api";

function DashboardContent() {
  const params = useSearchParams();
  const router = useRouter();
  const profileId = params.get("profile_id");
  const isDemo = params.get("demo") === "true";

  const [metrics, setMetrics] = useState<MetricRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        let pid = profileId;
        if (isDemo && !pid) {
          const seed = await seedDatabase();
          pid = seed.profile_id;
          router.replace(`/dashboard?profile_id=${pid}`);
          return;
        }
        if (!pid) { setError("No profile ID provided."); setLoading(false); return; }
        setActiveProfileId(pid);
        const data = await getMetrics(pid);
        setMetrics(data);
      } catch (e: unknown) {
        setError("Failed to load metrics. Make sure you have run ingestion and computation first.");
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [profileId, isDemo, router]);

  const devops       = metrics.filter((m) => m.tier === "devops");
  const business     = metrics.filter((m) => m.tier === "business");
  const sustainability = metrics.filter((m) => m.tier === "sustainability");

  const breachCount  = metrics.filter((m) => m.threshold_status === "breach").length;
  const warningCount = metrics.filter((m) => m.threshold_status === "warning").length;
  const health       = breachCount > 0 ? "red" : warningCount > 0 ? "amber" : "green";

  const HEALTH_STYLES: Record<string, { bg: string; border: string; dot: string; text: string }> = {
    green: { bg: "#E8F5E9", border: "#16A34A", dot: "#16A34A", text: "#14532D" },
    amber: { bg: "#FFFBEB", border: "#D97706", dot: "#D97706", text: "#78350F" },
    red:   { bg: "#FEF2F2", border: "#DC2626", dot: "#DC2626", text: "#7F1D1D" },
  };
  const hs = HEALTH_STYLES[health];

  if (loading) return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center">
      <p className="text-slate-400 text-sm">Loading metrics…</p>
    </main>
  );

  if (error) return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-2xl mx-auto">
        <p className="text-rose-600 text-sm mb-4">{error}</p>
        <Link href="/" className="text-violet-600 text-sm font-medium hover:underline">Back to home</Link>
      </div>
    </main>
  );

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
              <h1 className="text-base font-bold leading-none" style={{ color: "#FFFFFF" }}>Metric Dashboard</h1>
              {activeProfileId && (
                <p className="text-xs mt-0.5 font-mono" style={{ color: "#6B7280" }}>{activeProfileId}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {activeProfileId && (
              <Link href={`/trends?profile_id=${activeProfileId}`} className="text-sm font-medium" style={{ color: "#FFFFFF" }}>
                Trends
              </Link>
            )}
            {activeProfileId && (
              <Link
                href={`/intelligence?profile_id=${activeProfileId}`}
                className="inline-flex items-center gap-1.5 py-2 px-4 rounded-lg text-sm font-semibold"
                style={{ backgroundColor: "#1B6EF3", color: "#FFFFFF" }}
              >
                Run AI Analysis
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Health summary */}
        <div className="flex items-center gap-3 p-4 rounded-xl border mb-8" style={{ backgroundColor: hs.bg, borderColor: hs.border }}>
          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: hs.dot }} />
          <div className="flex-1 min-w-0">
            <span className="text-sm font-bold" style={{ color: hs.text }}>
              {health === "green" ? "All metrics healthy" : health === "amber" ? "Warnings detected" : "Breaches detected"}
            </span>
            <span className="text-xs text-slate-500 ml-3">
              {metrics.length} metrics tracked
              {breachCount > 0 && ` · ${breachCount} breach${breachCount !== 1 ? "es" : ""}`}
              {warningCount > 0 && ` · ${warningCount} warning${warningCount !== 1 ? "s" : ""}`}
            </span>
          </div>
        </div>

        {/* Metric sections */}
        {devops.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center gap-2 mb-4">
              <span className="w-1 h-5 rounded-full" style={{ backgroundColor: "#1B6EF3" }} />
              <h2 className="text-sm font-bold uppercase tracking-wide" style={{ color: "#0A1628" }}>DevOps</h2>
              <span className="text-xs text-slate-400">{devops.length}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {devops.map((m) => <MetricCard key={m.code} metric={m} />)}
            </div>
          </section>
        )}

        {business.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center gap-2 mb-4">
              <span className="w-1 h-5 rounded-full" style={{ backgroundColor: "#0B7A5E" }} />
              <h2 className="text-sm font-bold uppercase tracking-wide" style={{ color: "#0A1628" }}>Business</h2>
              <span className="text-xs text-slate-400">{business.length}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {business.map((m) => <MetricCard key={m.code} metric={m} />)}
            </div>
          </section>
        )}

        {sustainability.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center gap-2 mb-4">
              <span className="w-1 h-5 rounded-full" style={{ backgroundColor: "#16A34A" }} />
              <h2 className="text-sm font-bold uppercase tracking-wide" style={{ color: "#0A1628" }}>Sustainability</h2>
              <span className="text-xs text-slate-400">{sustainability.length}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {sustainability.map((m) => <MetricCard key={m.code} metric={m} />)}
            </div>
          </section>
        )}

        {metrics.length === 0 && (
          <div className="text-center py-20 text-slate-400 text-sm">
            No metrics available. Run ingestion and computation first.
          </div>
        )}

        <Link href="/" className="text-sm text-slate-400 hover:text-slate-600">Back to home</Link>
      </div>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-50 flex items-center justify-center"><p className="text-slate-400 text-sm">Loading…</p></main>}>
      <DashboardContent />
    </Suspense>
  );
}
