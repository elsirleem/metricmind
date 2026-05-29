"use client";

import { useEffect, useState, Suspense } from "react";
import ReactMarkdown from "react-markdown";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import TradeoffPanel from "@/components/TradeoffPanel";
import SustainabilityNote from "@/components/SustainabilityNote";
import RecommendationPanel from "@/components/RecommendationPanel";
import TimeWindowSelector from "@/components/TimeWindowSelector";
import {
  ReasoningReport, ExplanationOutput,
  TimeWindow, resolveWindowDates,
  ingestData, computeMetrics, runReasoning, runExplanation,
  getLatestExplanation, getLatestReport,
} from "@/lib/api";

const HEALTH_STYLES: Record<string, { bg: string; border: string; dot: string; text: string }> = {
  green: { bg: "#E8F5E9", border: "#16A34A", dot: "#16A34A", text: "#14532D" },
  amber: { bg: "#FFFBEB", border: "#D97706", dot: "#D97706", text: "#78350F" },
  red:   { bg: "#FEF2F2", border: "#DC2626", dot: "#DC2626", text: "#7F1D1D" },
};

const DEFAULT_WINDOW: TimeWindow = { mode: "preset", preset: "30d" };

function IntelligenceContent() {
  const params = useSearchParams();
  const profileId = params.get("profile_id") ?? "";

  const [timeWindow, setTimeWindow]   = useState<TimeWindow>(DEFAULT_WINDOW);
  const [report, setReport]           = useState<ReasoningReport | null>(null);
  const [explanation, setExplanation] = useState<ExplanationOutput | null>(null);
  const [loading, setLoading]         = useState(false);
  const [loadingStep, setLoadingStep] = useState("");
  const [error, setError]             = useState("");

  useEffect(() => {
    if (!profileId) return;
    // Restore both the explanation (narrative sections) and the reasoning
    // report (conflicts panel, recommendations) so closing and re-opening
    // a profile preserves the full Intelligence view.
    getLatestExplanation(profileId).then(setExplanation).catch(() => {});
    getLatestReport(profileId).then(setReport).catch(() => {});
  }, [profileId]);

  const handleRunAnalysis = async () => {
    if (!profileId) return;
    setLoading(true);
    setError("");
    setReport(null);

    try {
      // Step 1 — Ingest raw events covering both periods
      setLoadingStep("Fetching data…");
      await ingestData(profileId, timeWindow);

      // Step 2 — Compute metrics for the selected time window
      setLoadingStep("Computing metrics…");
      await computeMetrics(profileId, timeWindow);

      // Persist the period boundary so Trends page can render it
      try {
        if (timeWindow.mode !== "full_history") {
          const resolved = resolveWindowDates(timeWindow);
          localStorage.setItem("tw_c_start", resolved.c_start.toISOString());
          localStorage.setItem("tw_c_end", resolved.c_end.toISOString());
        } else {
          localStorage.removeItem("tw_c_start");
          localStorage.removeItem("tw_c_end");
        }
      } catch {
        // localStorage unavailable — non-fatal
      }

      // Step 3 — Reasoning
      setLoadingStep("Running analysis…");
      const r = await runReasoning(profileId);
      setReport(r);

      // Step 4 — Explanation
      setLoadingStep("Generating explanation…");
      const e = await runExplanation(profileId);
      setExplanation(e);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Analysis failed. Check that the profile is confirmed and metrics are available.";
      setError(msg);
      console.error(err);
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  };

  const hs = report ? HEALTH_STYLES[report.overall_health] ?? HEALTH_STYLES.green : null;

  return (
    <main className="min-h-screen bg-slate-50">
      {/* Top bar */}
      <header style={{ backgroundColor: "var(--sbp-navy)", borderBottom: "1px solid #1B6EF3" }}>
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "#1B6EF3" }}>
              <span className="text-white text-sm font-black">M</span>
            </Link>
            <div>
              <h1 className="text-base font-bold leading-none" style={{ color: "#FFFFFF" }}>Decision Intelligence</h1>
              {profileId && <p className="text-xs mt-0.5 font-mono" style={{ color: "#6B7280" }}>{profileId}</p>}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {profileId && (
              <Link href={`/dashboard?profile_id=${profileId}`} className="text-sm font-medium" style={{ color: "#FFFFFF" }}>
                Dashboard
              </Link>
            )}
            {profileId && (
              <Link href={`/trends?profile_id=${profileId}`} className="text-sm font-medium" style={{ color: "#FFFFFF" }}>
                Trends
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-xl text-sm" style={{ backgroundColor: "#FEF2F2", border: "1px solid #DC2626", color: "#7F1D1D" }}>
            {error}
          </div>
        )}

        {/* Time window selector + Run Analysis */}
        <div className="mb-6">
          <TimeWindowSelector value={timeWindow} onChange={setTimeWindow} />
          <button
            type="button"
            onClick={handleRunAnalysis}
            disabled={loading || !profileId}
            className="w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ backgroundColor: "#1B6EF3", color: "#FFFFFF" }}
          >
            {loading ? (
              <>
                <span className="inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                {loadingStep || "Running…"}
              </>
            ) : (
              "Run Analysis →"
            )}
          </button>
        </div>

        {/* Health banner */}
        {report && hs && (
          <div className="flex items-center gap-3 p-4 rounded-xl border mb-6" style={{ backgroundColor: hs.bg, borderColor: hs.border }}>
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: hs.dot }} />
            <span className="text-sm font-bold" style={{ color: hs.text }}>
              Overall health: {report.overall_health.toUpperCase()}
            </span>
            <span className="text-xs text-slate-500 ml-1">
              {report.conflicts.length} conflict{report.conflicts.length !== 1 ? "s" : ""}
              {" · "}
              {report.sustainability_flags.length} sustainability flag{report.sustainability_flags.length !== 1 ? "s" : ""}
            </span>
          </div>
        )}

        {/* Explanation sections */}
        {explanation && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <div className="card p-6">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Summary</p>
              <div className="prose text-sm text-slate-700">
                <ReactMarkdown>{explanation.sections.summary}</ReactMarkdown>
              </div>
            </div>
            {explanation.sections.key_findings && (
              <div className="card p-6">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Key Findings</p>
                <div className="prose text-sm text-slate-700">
                  <ReactMarkdown>{explanation.sections.key_findings}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Analysis panels */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <TradeoffPanel conflicts={report?.conflicts ?? []} />
          <SustainabilityNote
            flags={report?.sustainability_flags ?? []}
            note={explanation?.sections.sustainability_note ?? ""}
          />
        </div>

        <RecommendationPanel
          recommendations={report?.recommendations ?? []}
          actions={explanation?.sections.recommended_actions ?? ""}
        />

        {explanation?.sections.tradeoff_explanation && (
          <div className="card p-6 mt-4">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Trade-off Explanation</p>
            <div className="prose text-sm text-slate-700">
              <ReactMarkdown>{explanation.sections.tradeoff_explanation}</ReactMarkdown>
            </div>
          </div>
        )}

        {!report && !explanation && !loading && (
          <div className="text-center py-16">
            <p className="text-slate-400 text-sm">Select a time window and click &quot;Run Analysis&quot; to generate a report.</p>
          </div>
        )}

        <div className="mt-8">
          <Link href="/" className="text-sm text-slate-400 hover:text-slate-600">Back to home</Link>
        </div>
      </div>
    </main>
  );
}

export default function IntelligencePage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-50 flex items-center justify-center"><p className="text-slate-400 text-sm">Loading…</p></main>}>
      <IntelligenceContent />
    </Suspense>
  );
}
