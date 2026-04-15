"use client";
import ReactMarkdown from "react-markdown";
import { Recommendation } from "@/lib/api";

const PRIORITY_STYLE: Record<string, { badgeBg: string; badgeBorder: string; badgeText: string; dot: string }> = {
  immediate:   { badgeBg: "#FEF2F2", badgeBorder: "#DC2626", badgeText: "#7F1D1D", dot: "#DC2626" },
  this_sprint: { badgeBg: "#FFFBEB", badgeBorder: "#D97706", badgeText: "#78350F", dot: "#D97706" },
  strategic:   { badgeBg: "#EBF2FE", badgeBorder: "#1B6EF3", badgeText: "#0A1628", dot: "#1B6EF3" },
};

const ACTION_LABEL: Record<string, string> = {
  reduce_deployment_pace:       "Reduce Deployment Pace",
  invest_in_test_coverage:      "Invest in Test Coverage",
  address_technical_debt:       "Address Technical Debt",
  review_team_capacity:         "Review Team Capacity",
  escalate_to_stakeholder:      "Escalate to Stakeholder",
  accept_risk_with_mitigation:  "Accept Risk with Mitigation",
  investigate_incident_pattern: "Investigate Incident Pattern",
  reduce_work_in_progress:      "Reduce Work in Progress",
};

export default function RecommendationPanel({
  recommendations,
  actions,
}: {
  recommendations: Recommendation[];
  actions: string;
}) {
  return (
    <div className="card p-6">
      <p className="text-xs font-bold uppercase tracking-wide mb-5" style={{ color: "#6B7280" }}>Recommended Actions</p>

      {recommendations && recommendations.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-5">
          {recommendations.map((r, i) => {
            const sty = PRIORITY_STYLE[r.priority] ?? { badgeBg: "#F5F5F5", badgeBorder: "#6B7280", badgeText: "#374151", dot: "#6B7280" };
            return (
              <div key={i} className="flex items-center gap-2 rounded-lg px-3 py-1.5 bg-white" style={{ border: "1px solid #E2E8F0" }}>
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: sty.dot }} />
                <span className="text-xs font-semibold" style={{ color: "#0A1628" }}>
                  {ACTION_LABEL[r.code] ?? r.code}
                </span>
                <span className="badge" style={{ backgroundColor: sty.badgeBg, border: `1px solid ${sty.badgeBorder}`, color: sty.badgeText }}>
                  {r.priority}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {actions && (
        <div className={`prose text-sm${recommendations?.length ? " border-t border-slate-100 pt-4" : ""}`} style={{ color: "#374151" }}>
          <ReactMarkdown>{actions}</ReactMarkdown>
        </div>
      )}

      {!recommendations?.length && !actions && (
        <p className="text-sm" style={{ color: "#6B7280" }}>No recommendations at this time.</p>
      )}
    </div>
  );
}
