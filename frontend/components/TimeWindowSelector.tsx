"use client";

import { TimeWindow, resolveWindowDates } from "@/lib/api";

const PRESETS = [
  { label: "Last 7 days",   value: "7d" },
  { label: "Last 30 days",  value: "30d" },
  { label: "Last 90 days",  value: "90d" },
  { label: "Last 6 months", value: "6m" },
  { label: "Full history",  value: "full_history" },
  { label: "Custom range",  value: "custom" },
];

function fmtDate(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

interface Props {
  value: TimeWindow;
  onChange: (w: TimeWindow) => void;
}

export default function TimeWindowSelector({ value, onChange }: Props) {
  const showDates = value.mode !== "full_history" && !(value.mode === "custom" && (!value.custom_start || !value.custom_end));
  const resolved = showDates ? resolveWindowDates(value) : null;

  const selectValue =
    value.mode === "full_history" ? "full_history"
    : value.mode === "custom" ? "custom"
    : value.preset ?? "30d";

  function handleSelectChange(v: string) {
    if (v === "full_history") {
      onChange({ mode: "full_history" });
    } else if (v === "custom") {
      onChange({ mode: "custom" });
    } else {
      onChange({ mode: "preset", preset: v as TimeWindow["preset"] });
    }
  }

  return (
    <div className="card p-4 mb-4">
      <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-3">Analysis Period</p>

      <select
        value={selectValue}
        onChange={(e) => handleSelectChange(e.target.value)}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 bg-white focus:outline-none focus:ring-2"
        style={{ focusRingColor: "#1B6EF3" } as React.CSSProperties}
      >
        {PRESETS.map((p) => (
          <option key={p.value} value={p.value}>{p.label}</option>
        ))}
      </select>

      {value.mode === "custom" && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Start date</label>
            <input
              type="date"
              value={value.custom_start ?? ""}
              onChange={(e) => onChange({ ...value, custom_start: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">End date</label>
            <input
              type="date"
              value={value.custom_end ?? ""}
              onChange={(e) => onChange({ ...value, custom_end: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2"
            />
          </div>
        </div>
      )}

      <div className="mt-3 space-y-0.5">
        {value.mode === "full_history" ? (
          <p className="text-xs text-slate-500">
            <span className="font-medium text-slate-600">Full project history</span>
            {" "}— splits at the midpoint between first commit and today
          </p>
        ) : resolved ? (
          <>
            <p className="text-xs text-slate-700">
              <span className="font-medium">Current:</span>{" "}
              {fmtDate(resolved.c_start)} – {fmtDate(resolved.c_end)}
            </p>
            <p className="text-xs text-slate-500">
              <span className="font-medium">Compared to:</span>{" "}
              {fmtDate(resolved.p_start)} – {fmtDate(resolved.p_end)}
            </p>
          </>
        ) : (
          <p className="text-xs text-slate-400 italic">Select start and end dates above</p>
        )}
      </div>
    </div>
  );
}
