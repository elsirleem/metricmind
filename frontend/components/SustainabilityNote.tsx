"use client";
import ReactMarkdown from "react-markdown";
import { SustainabilityFlag } from "@/lib/api";

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

      <div className="flex items-start gap-2">
        {!hasFlags && <span className="w-2 h-2 rounded-full flex-shrink-0 mt-1" style={{ backgroundColor: "#16A34A" }} />}
        <div className="prose text-sm" style={{ color: "#14532D" }}>
          <ReactMarkdown>{note || "All sustainability indicators are healthy."}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
