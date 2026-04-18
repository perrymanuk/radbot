import { cn } from "@/lib/utils";
import { Icon } from "./icons";

// ─────────────────────────────────────────────────────────
// SYSTEM MESSAGE
//
// Full-width banner between user/agent messages for events the
// system narrates itself: scheduled triggers, tool completions,
// session boundaries, handoff fallbacks.
//
// Props shape is intentionally flexible — pass a `kind` for the
// accent color/icon and a label/text pair.
// ─────────────────────────────────────────────────────────

export type SystemMessageKind = "scheduled" | "info" | "warn" | "error";

interface Props {
  kind?: SystemMessageKind;
  /** Short uppercase tag, e.g. "SCHEDULED". Defaults from kind. */
  label?: string;
  /** Bold subject line between the tag and the body copy. */
  subject?: string;
  /** Body prose. */
  text: string;
  /** Already-formatted relative time ("2m ago"). */
  time?: string;
}

const KIND_META: Record<
  SystemMessageKind,
  { label: string; color: string; border: string; bg: string; icon: () => JSX.Element }
> = {
  scheduled: {
    label: "SCHEDULED",
    color: "text-accent-blue",
    border: "border-accent-blue/30",
    bg: "bg-accent-blue/[0.05]",
    icon: () => <Icon.bolt />,
  },
  info: {
    label: "INFO",
    color: "text-txt-secondary",
    border: "border-border",
    bg: "bg-bg-secondary/40",
    icon: () => <Icon.sparkle />,
  },
  warn: {
    label: "WARN",
    color: "text-terminal-amber",
    border: "border-terminal-amber/30",
    bg: "bg-terminal-amber/[0.06]",
    icon: () => <Icon.bolt />,
  },
  error: {
    label: "ERROR",
    color: "text-terminal-red",
    border: "border-terminal-red/40",
    bg: "bg-terminal-red/[0.06]",
    icon: () => <Icon.bolt />,
  },
};

export default function SystemMessage({ kind = "info", label, subject, text, time }: Props) {
  const meta = KIND_META[kind];
  return (
    <div
      role="status"
      className={cn(
        "flex items-center gap-3 px-5 py-2.5 my-1.5",
        "font-mono text-[0.7rem] text-txt-secondary",
        "border-t border-b border-dashed",
        meta.border,
        meta.bg,
      )}
    >
      <div className={cn("inline-flex items-center gap-1.5", meta.color)}>
        {meta.icon()}
        <span className="text-[0.6rem] font-bold tracking-[0.14em]">{label ?? meta.label}</span>
      </div>
      {subject && <span className="text-txt-primary font-semibold">{subject}</span>}
      {subject && <span className="text-txt-secondary/50">—</span>}
      <span className="font-sans text-[0.8125rem] flex-1">{text}</span>
      {time && <span className="text-[0.6rem] text-txt-secondary/70">{time}</span>}
    </div>
  );
}
