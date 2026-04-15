"use client";

import { useEffect, useState, Suspense } from "react";
import ReactMarkdown from "react-markdown";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import TradeoffPanel from "@/components/TradeoffPanel";
import SustainabilityNote from "@/components/SustainabilityNote";
import RecommendationPanel from "@/components/RecommendationPanel";
import {
  ReasoningReport, ExplanationOutput,
  runReasoning, runExplanation, getLatestExplanation,
} from "@/lib/api";

const HEALTH_STYLES: Record<string, { bg: string; border: string; dot: string; text: string }> = {
  green: { bg: "#E8F5E9", border: "#16A34A", dot: "#16A34A", text: "#14532D" },
  amber: { bg: "#FFFBEB", border: "#D97706", dot: "#D97706", text: "#78350F" },
  red:   { bg: "#FEF2F2", border: "#DC2626", dot: "#DC2626", text: "#7F1D1D" },
};

function IntelligenceContent() {
  const params = useSearchParams();
  const profileId = params.get("profile_id") ?? "";

  const [report, setReport]           = useState<ReasoningReport | null>(null);
  const [explanation, setExplanation] = useState<ExplanationOutput | null>(null);
  const [loading, setLoading]         = useState(false);
  const [loadingExplain, setLoadingExplain] = useState(false);
  const [error, setError]             = useState("");

  useEffect(() => {
    if (!profileId) return;
    getLatestExplanation(profileId).then(setExplanation).catch(() => {});
  }, [profileId]);

  const handleRunAnalysis = async () => {
    if (!profileId) return;
    setLoading(true); setError("");
    try {
      const r = await runReasoning(profileId);
      setReport(r);
      setLoadingExplain(true);
      const e = await runExplanation(profileId);
      setExplanation(e);
    } catch (e: unknown) {
      setError("Analysis failed. Check that the profile is confirmed and metrics are available.");
      console.error(e);
    } finally {
      setLoading(false);
      setLoadingExplain(false);
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
            <button
              onClick={handleRunAnalysis}
              disabled={loading || !profileId}
              className="inline-flex items-center gap-2 py-2 px-4 rounded-lg text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ backgroundColor: "#1B6EF3", color: "#FFFFFF" }}
            >
              {loading ? (loadingExplain ? "Generating explanation…" : "Reasoning…") : "Run analysis"}
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-xl text-sm" style={{ backgroundColor: "#FEF2F2", border: "1px solid #DC2626", color: "#7F1D1D" }}>
            {error}
          </div>
        )}

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
          <div className="text-center py-20">
            <p className="text-slate-400 text-sm">Click &quot;Run analysis&quot; to generate a reasoning report and stakeholder explanation.</p>
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
