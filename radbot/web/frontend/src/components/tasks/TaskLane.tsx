import type { ReactNode } from "react";

// ─────────────────────────────────────────────────────────
// TASK LANE — column for IN PROGRESS / BACKLOG / DONE
// ─────────────────────────────────────────────────────────

interface Props {
  label: string;
  color: string; // CSS color
  count: number;
  icon: ReactNode;
  children: ReactNode;
}

export default function TaskLane({ label, color, count, icon, children }: Props) {
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-center gap-2 px-1 py-1">
        <span className="inline-flex" style={{ color }} aria-hidden>
          {icon}
        </span>
        <span
          className="font-mono text-[0.6rem] font-bold tracking-[0.14em]"
          style={{ color }}
        >
          {label}
        </span>
        <span className="font-mono text-[0.6rem] text-txt-secondary px-1.5 py-px rounded-sm border border-border">
          {count}
        </span>
      </div>
      <div className="flex flex-col gap-1.5">{children}</div>
    </div>
  );
}
