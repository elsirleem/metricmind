"use client";
import { MetricRecord } from "@/lib/api";

// SBP status colors
const STATUS_STYLE: Record<string, { borderLeft: string; badgeBg: string; badgeBorder: string; badgeText: string }> = {
  within:  { borderLeft: "#16A34A", badgeBg: "#E8F5E9", badgeBorder: "#16A34A", badgeText: "#14532D" },
  warning: { borderLeft: "#D97706", badgeBg: "#FFFBEB", badgeBorder: "#D97706", badgeText: "#78350F" },
  breach:  { borderLeft: "#DC2626", badgeBg: "#FEF2F2", badgeBorder: "#DC2626", badgeText: "#7F1D1D" },
};

// SBP tier colors — card background + border-left + badge
const TIER_STYLE: Record<string, { cardBg: string; titleColor: string; badgeBg: string; badgeBorder: string; badgeText: string }> = {
  devops:         { cardBg: "#FFFFFF", titleColor: "#0A1628", badgeBg: "#EBF2FE", badgeBorder: "#1B6EF3", badgeText: "#0A1628" },
  business:       { cardBg: "#FFFFFF", titleColor: "#064D3B", badgeBg: "#E0F4EF", badgeBorder: "#0B7A5E", badgeText: "#064D3B" },
  sustainability: { cardBg: "#FFFFFF", titleColor: "#14532D", badgeBg: "#E8F5E9", badgeBorder: "#16A34A", badgeText: "#14532D" },
};

const TREND_ICON: Record<string, { symbol: string; color: string }> = {
  improving: { symbol: "↑", color: "#16A34A" },
  stable:    { symbol: "→", color: "#6B7280" },
  degrading: { symbol: "↓", color: "#DC2626" },
};

function fmt(v: number) {
  return v % 1 === 0 ? String(v) : v.toFixed(2);
}

export default function MetricCard({ metric }: { metric: MetricRecord }) {
  const trend      = TREND_ICON[metric.trend] ?? TREND_ICON.stable;
  const statusKey  = metric.threshold_status ?? "within";
  const status     = STATUS_STYLE[statusKey] ?? STATUS_STYLE.within;
  const tier       = TIER_STYLE[metric.tier] ?? { cardBg: "#F5F5F5", titleColor: "#374151", badgeBg: "#F5F5F5", badgeBorder: "#6B7280", badgeText: "#374151" };

  return (
    <div
      className="rounded-xl border p-5 shadow-sm"
      style={{
        backgroundColor: tier.cardBg,
        borderColor: "#E2E8F0",
        borderLeft: `4px solid ${status.borderLeft}`,
      }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <span className="text-xs font-black tracking-widest uppercase" style={{ color: "#6B7280" }}>{metric.code}</span>
          <p className="text-sm font-medium leading-snug mt-0.5 truncate" style={{ color: tier.titleColor }}>{metric.name}</p>
        </div>
        <span
          className="badge ml-2 flex-shrink-0"
          style={{ backgroundColor: tier.badgeBg, border: `1px solid ${tier.badgeBorder}`, color: tier.badgeText }}
        >
          {metric.tier}
        </span>
      </div>

      {/* Value row */}
      <div className="flex items-baseline gap-2 mb-4">
        <span className="text-3xl font-black tabular-nums leading-none" style={{ color: "#0A1628" }}>
          {typeof metric.current_value === "number" ? fmt(metric.current_value) : metric.current_value}
        </span>
        <span className="text-sm font-medium" style={{ color: "#6B7280" }}>{metric.unit}</span>
        <span className="ml-auto text-xl font-bold" style={{ color: trend.color }} aria-label={metric.trend}>
          {trend.symbol}
        </span>
      </div>

      {/* Footer row */}
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className="badge"
          style={{ backgroundColor: status.badgeBg, border: `1px solid ${status.badgeBorder}`, color: status.badgeText }}
        >
          {statusKey}
          {metric.threshold_value !== null && metric.threshold_value !== undefined
            ? ` · ${metric.threshold_value}`
            : ""}
        </span>

        {metric.sustainability_dimension && (
          <span className="badge" style={{ backgroundColor: "#E8F5E9", border: "1px solid #16A34A", color: "#14532D" }}>
            {metric.sustainability_dimension}
          </span>
        )}

        {metric.previous_value !== null && metric.previous_value !== undefined && (
          <span className="text-xs ml-auto tabular-nums" style={{ color: "#6B7280" }}>
            prev {fmt(metric.previous_value)} {metric.unit}
          </span>
        )}
      </div>
    </div>
  );
}
