"use client";
import ReactMarkdown from "react-markdown";
import { SustainabilityFlag } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  within:  "#14532D",
  warning: "#78350F",
  breach:  "#7F1D1D",
};

const STATUS_DOT: Record<string, string> = {
  within:  "#16A34A",
  warning: "#D97706",
  breach:  "#DC2626",
};

export default function SustainabilityNote({
  flags,
  note,
}: {
  flags: SustainabilityFlag[];
  note: string;
}) {
  const hasFlags = flags && flags.length > 0;
  const borderColor = hasFlags ? "#D97706" : "#16A34A";

  return (
    <div className="card p-6" style={{ borderLeft: `4px solid ${borderColor}`, backgroundColor: "#E8F5E9" }}>
      <p className="text-xs font-bold uppercase tracking-wide mb-4" style={{ color: "#6B7280" }}>Sustainability</p>

      {hasFlags ? (
        <div className="space-y-2.5">
          {flags.map((f, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <span className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: STATUS_DOT[f.status] ?? "#6B7280" }} />
              <div className="min-w-0">
                <span className="font-mono text-sm font-bold" style={{ color: STATUS_COLOR[f.status] ?? "#374151" }}>
                  {f.metric_code}
                </span>
                <span className="text-sm ml-2" style={{ color: "#6B7280" }}>
                  [{f.dimension}]
                  {f.consecutive_periods > 1 && ` for ${f.consecutive_periods} periods`}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0 mt-1" style={{ backgroundColor: "#16A34A" }} />
          <div className="prose text-sm" style={{ color: "#14532D" }}>
            <ReactMarkdown>{note || "All sustainability indicators are healthy."}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}
