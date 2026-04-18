import { useEffect, useState, useCallback } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { getCostDashboard, getSessionUsage } from "@/lib/admin-api";
import type { CostDashboard, SessionUsageStats } from "@/lib/admin-api";
import { cn } from "@/lib/utils";

// ── Helpers ─────────────────────────────────────────────────

function formatCost(usd: number): string {
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  if (usd >= 0.01) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(4)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function monthLabel(ym: string): string {
  const [y, m] = ym.split("-");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parseInt(m, 10) - 1]} ${y}`;
}

function pctChange(current: number, previous: number): { text: string; color: string } {
  if (previous === 0) return current > 0 ? { text: "new", color: "text-radbot-sunset" } : { text: "--", color: "text-txt-secondary/60" };
  const pct = ((current - previous) / previous) * 100;
  const sign = pct >= 0 ? "+" : "";
  return {
    text: `${sign}${pct.toFixed(0)}%`,
    color: pct > 0 ? "text-radbot-sunset" : "text-terminal-green",
  };
}

// ── Sub-components ──────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: { text: string; color?: string } }) {
  return (
    <div className="bg-bg-secondary border border-border rounded-lg p-4 flex-1 min-w-[140px]">
      <div className="text-txt-secondary/60 text-xs uppercase tracking-wide mb-1">{label}</div>
      <div className="text-xl font-semibold text-txt-primary">{value}</div>
      {sub && <div className={cn("text-xs mt-1", sub.color || "text-txt-secondary/60")}>{sub.text}</div>}
    </div>
  );
}

function BarRow({ label, value, maxValue, cost }: { label: string; value: number; maxValue: number; cost: string }) {
  const pct = maxValue > 0 ? Math.max(2, (value / maxValue) * 100) : 0;
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="w-[80px] text-xs text-txt-secondary text-right shrink-0 truncate" title={label}>{label}</div>
      <div className="flex-1 bg-bg-primary rounded h-5 overflow-hidden">
        <div className="bg-radbot-sunset h-full rounded transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="w-[70px] text-xs text-txt-primary text-right shrink-0">{cost}</div>
    </div>
  );
}

function DataTable({ columns, rows }: { columns: string[]; rows: (string | number)[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th key={col} className="text-left text-txt-secondary/60 font-medium py-2 px-2 uppercase tracking-wide">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-bg-tertiary/30">
              {row.map((cell, j) => (
                <td key={j} className="py-1.5 px-2 text-txt-primary/90">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Label Filter ────────────────────────────────────────────

const LABELS = [
  { value: "", label: "All" },
  { value: "production", label: "Production" },
  { value: "e2e", label: "E2E" },
];

// ── Main Panel ──────────────────────────────────────────────

export function CostTrackingPanel() {
  const token = useAdminStore((s) => s.token);
  const toast = useAdminStore((s) => s.toast);

  const [dashboard, setDashboard] = useState<CostDashboard | null>(null);
  const [sessionStats, setSessionStats] = useState<SessionUsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedLabel, setSelectedLabel] = useState("");
  const [selectedMonth, setSelectedMonth] = useState<string>("");

  const loadData = useCallback(async (year?: number, month?: number, label?: string) => {
    setLoading(true);
    try {
      const [dash, session] = await Promise.all([
        getCostDashboard(token, year, month, label || undefined),
        getSessionUsage(token),
      ]);
      setDashboard(dash);
      setSessionStats(session);
      if (!selectedMonth && dash.available_months.length > 0) {
        setSelectedMonth(dash.available_months[0].month);
      }
    } catch (e: any) {
      toast("Failed to load cost data: " + e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [token, toast, selectedMonth]);

  // Initial load
  useEffect(() => {
    loadData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Reload on label or month change
  const handleLabelChange = (label: string) => {
    setSelectedLabel(label);
    const [y, m] = selectedMonth ? selectedMonth.split("-").map(Number) : [0, 0];
    loadData(y || undefined, m || undefined, label);
  };

  const handleMonthChange = (ym: string) => {
    setSelectedMonth(ym);
    const [y, m] = ym.split("-").map(Number);
    loadData(y, m, selectedLabel);
  };

  if (loading && !dashboard) {
    return (
      <div>
        <h2 className="text-lg font-semibold mb-4">Cost Tracking</h2>
        <div className="text-txt-secondary text-sm">Loading cost data...</div>
      </div>
    );
  }

  const d = dashboard;
  const summary = d?.summary;
  const change = d ? pctChange(summary?.total_cost_usd ?? 0, d.previous_month_cost_usd) : null;
  const savings = summary ? summary.total_cost_without_cache_usd - summary.total_cost_usd : 0;
  const maxDailyCost = d?.daily.reduce((max, day) => Math.max(max, day.cost_usd), 0) ?? 0;

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Cost Tracking</h2>

      {/* Controls row */}
      <div className="flex items-center gap-4 mb-5 flex-wrap">
        {/* Label filter */}
        <div className="flex items-center gap-1 bg-bg-secondary border border-border rounded-md p-0.5">
          {LABELS.map((l) => (
            <button
              key={l.value}
              onClick={() => handleLabelChange(l.value)}
              className={cn(
                "px-3 py-1 text-xs rounded transition-colors cursor-pointer",
                selectedLabel === l.value
                  ? "bg-radbot-sunset text-bg-primary"
                  : "text-txt-secondary hover:text-txt-primary",
              )}
            >
              {l.label}
            </button>
          ))}
        </div>

        {/* Month picker */}
        {d && d.available_months.length > 0 && (
          <select
            value={selectedMonth}
            onChange={(e) => handleMonthChange(e.target.value)}
            className="bg-bg-secondary border border-border rounded-md px-3 py-1.5 text-sm text-txt-primary outline-none"
          >
            {d.available_months.map((m) => (
              <option key={m.month} value={m.month}>
                {monthLabel(m.month)} — {formatCost(m.cost_usd)}
              </option>
            ))}
          </select>
        )}

        {loading && <span className="text-txt-secondary/60 text-xs">Refreshing...</span>}
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="flex gap-3 mb-6 flex-wrap">
          <StatCard
            label="Monthly Cost"
            value={formatCost(summary.total_cost_usd)}
            sub={change ? { text: `${change.text} vs prev month`, color: change.color } : undefined}
          />
          <StatCard label="Requests" value={summary.total_requests.toLocaleString()} />
          <StatCard
            label="Tokens"
            value={formatTokens(summary.total_prompt_tokens + summary.total_output_tokens)}
            sub={{ text: `${formatTokens(summary.total_prompt_tokens)} in / ${formatTokens(summary.total_output_tokens)} out` }}
          />
          <StatCard
            label="Cache Savings"
            value={formatCost(savings)}
            sub={summary.total_prompt_tokens > 0
              ? { text: `${((summary.total_cached_tokens / summary.total_prompt_tokens) * 100).toFixed(0)}% cache hit rate` }
              : undefined}
          />
        </div>
      )}

      {/* Daily breakdown */}
      {d && d.daily.length > 0 && (
        <Section title="Daily Cost">
          {d.daily.map((day) => (
            <BarRow
              key={day.day}
              label={day.day.slice(5)} // MM-DD
              value={day.cost_usd}
              maxValue={maxDailyCost}
              cost={formatCost(day.cost_usd)}
            />
          ))}
        </Section>
      )}

      {/* Per-agent breakdown */}
      {d && d.by_agent.length > 0 && (
        <Section title="Cost by Agent">
          <DataTable
            columns={["Agent", "Requests", "Input Tokens", "Cached", "Output Tokens", "Cost"]}
            rows={d.by_agent.map((a) => [
              a.agent_name,
              a.requests.toLocaleString(),
              formatTokens(a.prompt_tokens),
              formatTokens(a.cached_tokens),
              formatTokens(a.output_tokens),
              formatCost(a.cost_usd),
            ])}
          />
        </Section>
      )}

      {/* Per-model breakdown */}
      {d && d.by_model.length > 0 && (
        <Section title="Cost by Model">
          <DataTable
            columns={["Model", "Requests", "Input Tokens", "Cached", "Output Tokens", "Cost"]}
            rows={d.by_model.map((m) => [
              m.model || "(unknown)",
              m.requests.toLocaleString(),
              formatTokens(m.prompt_tokens),
              formatTokens(m.cached_tokens),
              formatTokens(m.output_tokens),
              formatCost(m.cost_usd),
            ])}
          />
        </Section>
      )}

      {/* Real-time session stats */}
      {sessionStats && sessionStats.total_requests > 0 && (
        <Section title="Current Session (In-Memory)">
          <div className="text-xs text-txt-secondary/60 mb-2">
            Uptime: {Math.round(sessionStats.uptime_seconds / 60)} min — resets on server restart
          </div>
          <div className="flex gap-3 flex-wrap mb-3">
            <StatCard label="Session Cost" value={formatCost(sessionStats.estimated_cost_usd)} />
            <StatCard label="Session Requests" value={sessionStats.total_requests.toLocaleString()} />
            <StatCard
              label="Cache Rate"
              value={`${sessionStats.cache_hit_rate_pct.toFixed(0)}%`}
              sub={{ text: `${formatCost(sessionStats.estimated_savings_usd)} saved` }}
            />
          </div>
          {Object.keys(sessionStats.per_agent).length > 0 && (
            <DataTable
              columns={["Agent", "Requests", "Input", "Cached", "Output", "Cost"]}
              rows={Object.entries(sessionStats.per_agent)
                .sort(([, a], [, b]) => b.cost_usd - a.cost_usd)
                .map(([name, a]) => [
                  name,
                  a.requests.toLocaleString(),
                  formatTokens(a.prompt_tokens),
                  formatTokens(a.cached_tokens),
                  formatTokens(a.output_tokens),
                  formatCost(a.cost_usd),
                ])}
            />
          )}
        </Section>
      )}

      {/* Empty state */}
      {d && d.daily.length === 0 && summary?.total_requests === 0 && (
        <div className="text-txt-secondary/60 text-sm mt-4">No cost data for this month.</div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h3 className="text-sm font-semibold text-txt-secondary uppercase tracking-wide mb-3">{title}</h3>
      <div className="bg-bg-secondary border border-border rounded-lg p-4">{children}</div>
    </div>
  );
}
