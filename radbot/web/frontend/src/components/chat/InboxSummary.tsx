import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────
// INBOX SUMMARY CARD
//
// Placeholder card rendered inside an agent message when COMMS
// (the inbox triage agent) returns a batched email summary.
//
// Wire protocol (see AgentCards.tsx header):
//   ```radbot:inbox { ...InboxSummaryData... }```
// ─────────────────────────────────────────────────────────

export interface InboxSummaryData {
  personal: string[];
  work: string[];
  jira?: string;
}

interface Props {
  s: InboxSummaryData;
}

function Row({ label, items, color }: { label: string; items: string[]; color: string }) {
  if (!items.length) return null;
  return (
    <div className="mt-2.5">
      <div
        className="font-mono text-[0.6rem] font-bold tracking-[0.12em] mb-1.5"
        style={{ color }}
      >
        {label}
      </div>
      <ul className="m-0 p-0 list-none grid gap-1">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 font-sans text-[0.8125rem] text-txt-primary">
            <span style={{ color, opacity: 0.6 }}>›</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function InboxSummary({ s }: Props) {
  return (
    <div
      className={cn(
        "mt-3 px-4 py-3.5 rounded",
        "bg-black/25 border border-border",
      )}
    >
      <Row label="PERSONAL" items={s.personal} color="#3584e4" />
      <Row label="WORK"     items={s.work}     color="#FFBF00" />
      {s.jira && (
        <div
          className={cn(
            "mt-3 px-2.5 py-2 rounded",
            "border border-dashed border-terminal-amber/30",
            "font-sans text-[0.75rem] text-txt-secondary",
          )}
        >
          <span className="font-mono text-[0.6rem] font-bold tracking-[0.12em] text-terminal-amber mr-2">
            JIRA
          </span>
          {s.jira}
        </div>
      )}
    </div>
  );
}
