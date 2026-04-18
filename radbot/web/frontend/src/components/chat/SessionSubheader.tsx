import { useState } from "react";
import { useAppStore } from "@/stores/app-store";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────
// SESSION SUBHEADER
//
// Thin strip between the main header and the message list:
//   SESSION · radbot / web-redesign · started 2h ago · 24 messages        [ + NEW SESSION ]
//
// Reads:
//   - app-store.sessions[] + app-store.sessionId  → current Session
//   - app-store.messages.length                   → message count
//   - app-store.createNewSession                  → "+ NEW SESSION" action
//
// Typography spec (all uppercase unless otherwise noted):
//   • SESSION label       → font-mono, text-[0.58rem], tracking-[0.2em], text-txt-secondary/70
//   • Separator dots (·)  → font-mono, text-[0.65rem], text-txt-secondary/40, mx-2
//   • Project path        → font-mono, text-[0.7rem], tracking-[0.08em],
//                            project name text-accent-blue, "/", then session name text-txt-primary (regular case)
//   • Meta (started/msgs) → font-mono, text-[0.65rem], tracking-[0.1em], text-txt-secondary
//   • Numeric emphasis    → text-txt-primary font-bold for message count
//   • +NEW SESSION button → matches existing "+ NEW" button spec: border-terminal-green,
//                           font-mono text-[0.7rem] tracking-wider
//
// Spacing:
//   • px-4 py-2 (44px tall on mobile / ~32px desktop)
//   • border-b border-border (same as header)
//   • Background: bg-bg-primary (slightly darker than header → visual stacking)
// ─────────────────────────────────────────────────────────

function formatRelative(iso: string): string {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Separator dot
function Dot() {
  return <span className="mx-2 text-[0.65rem] text-txt-secondary/40 font-mono select-none">·</span>;
}

// Project / session name. Heuristic: if session name is "project/name",
// split; otherwise render the whole name as the session, with "default" project.
function ProjectPath({ name }: { name: string }) {
  const slashIdx = name.indexOf("/");
  const [project, session] =
    slashIdx > 0 ? [name.slice(0, slashIdx).trim(), name.slice(slashIdx + 1).trim()] : ["radbot", name];

  return (
    <span className="font-mono text-[0.7rem] tracking-[0.08em]">
      <span className="text-accent-blue font-semibold">{project}</span>
      <span className="text-txt-secondary/50 mx-1">/</span>
      <span className="text-txt-primary">{session || "untitled"}</span>
    </span>
  );
}

export default function SessionSubheader() {
  const sessionId = useAppStore((s) => s.sessionId);
  const sessions = useAppStore((s) => s.sessions);
  const messages = useAppStore((s) => s.messages);
  const createNewSession = useAppStore((s) => s.createNewSession);
  const [busy, setBusy] = useState(false);

  const current = sessions.find((s) => s.id === sessionId);
  const msgCount = messages.length;

  const handleNew = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await createNewSession();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-1.5 bg-bg-primary border-b border-border flex-shrink-0 min-h-[32px]">
      {/* Left: label + path + meta */}
      <div className="flex items-center min-w-0 flex-1 overflow-hidden">
        <span className="font-mono text-[0.58rem] tracking-[0.2em] font-bold text-txt-secondary/70 uppercase flex-none">
          Session
        </span>
        <Dot />

        {current ? (
          <ProjectPath name={current.name ?? `session-${current.id.slice(0, 8)}`} />
        ) : (
          <span className="font-mono text-[0.7rem] text-txt-secondary/60 italic">no session</span>
        )}

        {/* Meta strip — hides on very narrow viewports */}
        {current && (
          <div className="hidden sm:flex items-center min-w-0 ml-0">
            <Dot />
            <span className="font-mono text-[0.65rem] tracking-[0.1em] text-txt-secondary whitespace-nowrap">
              started <span className="text-txt-primary/90">{formatRelative(current.created_at)}</span>
            </span>
            <Dot />
            <span className="font-mono text-[0.65rem] tracking-[0.1em] text-txt-secondary whitespace-nowrap">
              <span className="text-txt-primary font-bold">{msgCount}</span>
              <span className="ml-1">{msgCount === 1 ? "message" : "messages"}</span>
            </span>
          </div>
        )}
      </div>

      {/* Right: + NEW SESSION */}
      <button
        onClick={handleNew}
        disabled={busy}
        aria-label="Create new session"
        className={cn(
          "flex-none inline-flex items-center gap-1 px-2.5 py-1 border",
          "font-mono text-[0.65rem] tracking-wider uppercase cursor-pointer transition-all",
          "bg-bg-tertiary text-terminal-green border-terminal-green/60",
          "hover:bg-terminal-green hover:text-bg-primary hover:border-terminal-green",
          "focus:outline-none focus:ring-1 focus:ring-terminal-green",
          "disabled:opacity-50 disabled:cursor-wait",
        )}
      >
        <span className="hidden sm:inline">+ NEW SESSION</span>
        <span className="sm:hidden">+ NEW</span>
      </button>
    </div>
  );
}
