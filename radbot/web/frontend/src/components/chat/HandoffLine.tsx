import { cn } from "@/lib/utils";
import { agentFor } from "./agent-registry";

// ─────────────────────────────────────────────────────────
// HANDOFF LINE
//
// Inline pill rendered inside an agent message when the agent
// is about to delegate: BETO → PLANNER. Reads identity
// (color + glyph) from agent-registry.
//
// Wire protocol:
//   ```radbot:handoff { "from":"BETO", "to":"PLANNER", "reason":"..." }```
// ─────────────────────────────────────────────────────────

export interface HandoffInfo {
  from: string;
  to: string;
  reason?: string;
}

function Avatar({ id }: { id: string }) {
  const a = agentFor(id);
  return (
    <span
      className="inline-grid place-items-center w-4 h-4 rounded-[2px] font-mono text-[0.6rem] font-bold leading-none"
      style={{ background: a.tint, color: "#0e1419" }}
      aria-hidden
    >
      {a.glyph}
    </span>
  );
}

export default function HandoffLine({ handoff }: { handoff: HandoffInfo }) {
  const from = agentFor(handoff.from);
  const to = agentFor(handoff.to);
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 mt-2",
        "pl-1.5 pr-2.5 py-1 rounded-full",
        "bg-bg-tertiary border border-border",
        "font-mono text-[0.6rem] tracking-[0.06em] text-txt-secondary",
      )}
      title={handoff.reason}
    >
      <Avatar id={handoff.from} />
      <span className={from.textClass}>{from.name}</span>
      <svg width="18" height="8" viewBox="0 0 18 8" className="text-txt-secondary/60" aria-hidden>
        <path
          d="M1 4h12M10 1l3 3-3 3"
          stroke="currentColor"
          strokeWidth="1.2"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className={to.textClass}>{to.name}</span>
      <Avatar id={handoff.to} />
      {handoff.reason && (
        <span className="text-txt-secondary/70 italic font-sans normal-case ml-1 max-w-[16rem] truncate">
          {handoff.reason}
        </span>
      )}
    </div>
  );
}
