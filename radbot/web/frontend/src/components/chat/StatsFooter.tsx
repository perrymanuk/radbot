import { useAppStore } from "@/stores/app-store";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────
// STATS FOOTER
//
// Bottom strip, immediately below the ChatInput:
//
//   MSGS 17 · IN 1.2k · OUT 772 · TOTAL 1.9k · CTX ▓▓░░░░░░ 0.19%        COST $0.0092 · today $0.47 · mo $12.18
//
// ── Data sources ─────────────────────────────────────────
// The footer reads the following fields from app-store (all OPTIONAL so it
// degrades gracefully until the backend lands):
//
//   sessionStats: {
//     inputTokens:  number;   // cumulative prompt tokens for this session
//     outputTokens: number;   // cumulative completion tokens
//     contextTokens: number;  // current ctx window usage (last request)
//     contextWindow: number;  // model's max ctx, e.g. 1_000_000 for gemini-2.5-pro
//     costUsd: number;        // cost of THIS session (so far)
//     costTodayUsd: number;   // rolling 24h cost across all sessions
//     costMonthUsd: number;   // month-to-date cost
//   } | null
//
// messages.length covers MSGS.
//
// ── Backend surfacing needed ─────────────────────────────
// 1.  Extend the WebSocket `status` event (see use-websocket.ts) to include
//     {input_tokens, output_tokens, context_tokens, context_window, cost_usd,
//      cost_today_usd, cost_month_usd}. This is emitted after every model turn.
//
// 2.  Token accounting: hook into ADK's usage metadata callback in
//     radbot/callbacks/ — most providers (Gemini, Anthropic, OpenAI) return
//     usage on each response. Accumulate per session_id in Postgres (new
//     `session_stats` table keyed by session_id) so reloads restore the totals.
//
// 3.  Cost calc: map (model, input_tokens, output_tokens) → USD via a price
//     table (or read from each provider's usage API). Store and aggregate.
//
// 4.  On session init / load, the frontend should fetch /api/sessions/{id}/stats
//     and call setSessionStats(...) in app-store.
//
// ── Typography ───────────────────────────────────────────
//   • Row container:   font-mono text-[0.6rem] tracking-[0.12em] uppercase
//                       text-txt-secondary
//   • Numeric values:  text-txt-primary font-bold, NOT uppercased
//   • Separator dots:  text-txt-secondary/40, mx-1.5
//   • CTX bar:         10 segments, 3px tall, 80px wide, bg-bg-tertiary
//                       fill color graded by % (green <60%, amber <85%, red >=85%)
// ─────────────────────────────────────────────────────────

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return (n / 1000).toFixed(n < 10_000 ? 1 : 0) + "k";
  return (n / 1_000_000).toFixed(2) + "M";
}

function formatUsd(n: number): string {
  if (n < 0.01) return "$" + n.toFixed(4);
  if (n < 10) return "$" + n.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  if (n < 100) return "$" + n.toFixed(2);
  return "$" + n.toFixed(0);
}

function ctxColor(pct: number): string {
  if (pct >= 85) return "#CC0000"; // terminal-red
  if (pct >= 60) return "#FFBF00"; // terminal-amber
  return "#33FF33";                // terminal-green
}

// 10-segment horizontal progress
function CtxBar({ pct }: { pct: number }) {
  // Always light at least one cell so the bar is visible even at <10%.
  const lit = Math.max(pct > 0 ? 1 : 0, Math.min(10, Math.round(pct / 10)));
  const color = ctxColor(pct);
  return (
    <div
      className="inline-flex items-center gap-[2px] mx-2 align-middle"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Context window usage"
    >
      {Array.from({ length: 10 }).map((_, i) => {
        const filled = i < lit;
        return (
          <span
            key={i}
            className="inline-block w-[7px] h-[4px] rounded-[1px]"
            style={{
              background: filled ? color : "rgba(255,255,255,0.06)",
              boxShadow: filled ? `0 0 5px ${color}aa` : "none",
            }}
          />
        );
      })}
    </div>
  );
}

function Dot() {
  return (
    <span className="mx-2 text-txt-secondary/30 select-none" aria-hidden>
      ·
    </span>
  );
}

function Stat({
  label,
  children,
  valueClass,
  labelCase = "upper",
}: {
  label: string;
  children: React.ReactNode;
  valueClass?: string;
  labelCase?: "upper" | "lower";
}) {
  return (
    <span className="whitespace-nowrap inline-flex items-baseline gap-1.5">
      <span
        className={cn(
          "text-txt-secondary/60 tracking-[0.14em]",
          labelCase === "upper" ? "uppercase" : "normal-case",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "font-semibold tabular-nums tracking-normal",
          valueClass ?? "text-txt-primary",
        )}
      >
        {children}
      </span>
    </span>
  );
}

export default function StatsFooter() {
  const messages = useAppStore((s) => s.messages);
  const stats = useAppStore((s) => s.sessionStats);

  const msgs = messages.length;
  const inTok = stats?.inputTokens ?? 0;
  const outTok = stats?.outputTokens ?? 0;
  const total = inTok + outTok;
  const ctxPct =
    stats && stats.contextWindow > 0
      ? (stats.contextTokens / stats.contextWindow) * 100
      : 0;

  const ctxLabel = ctxPct < 0.01 ? "0%" : ctxPct.toFixed(ctxPct < 1 ? 2 : 1) + "%";
  const ctxValueClass =
    ctxPct >= 85
      ? "text-terminal-red"
      : ctxPct >= 60
        ? "text-terminal-amber"
        : "text-terminal-green";

  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 px-4 py-1.5",
        "bg-bg-secondary border-t border-border flex-shrink-0",
        "font-mono text-[0.62rem] text-txt-secondary",
      )}
      aria-label="Session stats"
    >
      {/* Left: counters + ctx bar */}
      <div className="flex items-center min-w-0 overflow-hidden">
        <span className="hidden sm:inline-flex items-baseline">
          <Stat label="MSGS">{msgs}</Stat>
          <Dot />
          <Stat label="IN">{formatTokens(inTok)}</Stat>
          <Dot />
          <Stat label="OUT">{formatTokens(outTok)}</Stat>
          <Dot />
        </span>
        <Stat label="TOTAL">{formatTokens(total)}</Stat>
        <Dot />
        <span className="whitespace-nowrap inline-flex items-center">
          <span className="text-txt-secondary/60 tracking-[0.14em] uppercase">CTX</span>
          <span className="hidden sm:inline-flex">
            <CtxBar pct={ctxPct} />
          </span>
          <span className={cn("font-semibold tabular-nums ml-1.5 sm:ml-0", ctxValueClass)}>{ctxLabel}</span>
        </span>
      </div>

      {/* Right: costs — COST is accent-green to highlight spend */}
      <div className="flex items-center flex-none">
        <Stat label="COST" valueClass="text-terminal-green">
          {formatUsd(stats?.costUsd ?? 0)}
        </Stat>
        <span className="hidden sm:inline-flex items-baseline">
          <Dot />
          <Stat label="today" labelCase="lower">
            {formatUsd(stats?.costTodayUsd ?? 0)}
          </Stat>
        </span>
        <span className="hidden md:inline-flex items-baseline">
          <Dot />
          <Stat label="mo" labelCase="lower">
            {formatUsd(stats?.costMonthUsd ?? 0)}
          </Stat>
        </span>
      </div>
    </div>
  );
}
