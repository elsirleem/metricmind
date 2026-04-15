"use client";
import { Conflict } from "@/lib/api";

const SEVERITY_STYLE: Record<string, { badgeBg: string; badgeBorder: string; badgeText: string; dot: string }> = {
  LOW:      { badgeBg: "#F5F5F5", badgeBorder: "#6B7280", badgeText: "#374151", dot: "#6B7280" },
  MEDIUM:   { badgeBg: "#EBF2FE", badgeBorder: "#1B6EF3", badgeText: "#0A1628", dot: "#1B6EF3" },
  HIGH:     { badgeBg: "#FFFBEB", badgeBorder: "#D97706", badgeText: "#78350F", dot: "#D97706" },
  CRITICAL: { badgeBg: "#FEF2F2", badgeBorder: "#DC2626", badgeText: "#7F1D1D", dot: "#DC2626" },
};

const CONFLICT_LABEL: Record<string, string> = {
  speed_stability:           "Speed vs Stability",
  throughput_sustainability: "Throughput vs Sustainability",
  cost_reliability:          "Cost vs Reliability",
  other:                     "Trade-off",
};

export default function TradeoffPanel({ conflicts }: { conflicts: Conflict[] }) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-5">
        <p className="text-xs font-bold uppercase tracking-wide" style={{ color: "#6B7280" }}>Trade-off Analysis</p>
        {conflicts.length > 0 && (
          <span className="badge" style={{ backgroundColor: "#F5F5F5", border: "1px solid #6B7280", color: "#374151" }}>
            {conflicts.length} conflict{conflicts.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {conflicts.length === 0 ? (
        <div className="flex items-center gap-2 py-2">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#16A34A" }} />
          <p className="text-sm" style={{ color: "#6B7280" }}>No conflicts detected.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {conflicts.map((c, i) => {
            const sty = SEVERITY_STYLE[c.severity] ?? SEVERITY_STYLE.LOW;
            return (
              <div key={i} className="rounded-lg p-4" style={{ border: "1px solid #E2E8F0", borderLeft: `3px solid ${sty.dot}` }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: sty.dot }} />
                  <span className="font-mono text-sm font-bold" style={{ color: "#0A1628" }}>{c.metric_a}</span>
                  <span className="text-xs" style={{ color: "#6B7280" }}>vs</span>
                  <span className="font-mono text-sm font-bold" style={{ color: "#0A1628" }}>{c.metric_b}</span>
                  <span className="ml-auto text-xs" style={{ color: "#6B7280" }}>{CONFLICT_LABEL[c.conflict_type] ?? c.conflict_type}</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="badge flex-shrink-0" style={{ backgroundColor: sty.badgeBg, border: `1px solid ${sty.badgeBorder}`, color: sty.badgeText }}>
                    {c.severity}
                  </span>
                  <p className="text-sm leading-snug" style={{ color: "#374151" }}>{c.evidence}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
