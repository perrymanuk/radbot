import { cn } from "@/lib/utils";
import { Icon } from "@/components/chat/icons";
import type { ProjectMeta } from "./TaskRow";

// ─────────────────────────────────────────────────────────
// TASK PROJECT SIDEBAR
//
// Left rail of the Tasks panel. Lists "all tasks" + projects.
//
// ── Backend surfacing ────────────────────────────────────
// Needs a /api/projects endpoint returning
//   Array<{id, name, color, count}>
// and the current task list for the total. Until that lands,
// pass the memoized list in as `projects` from the parent.
// ─────────────────────────────────────────────────────────

interface Props {
  projects: (ProjectMeta & { count: number })[];
  totalCount: number;
  active: string; // "all" or project id
  onSelect: (id: string) => void;
}

export default function TaskProjectList({ projects, totalCount, active, onSelect }: Props) {
  return (
    <aside className="w-[200px] flex-none border-r border-border/70 bg-bg-tertiary/40 p-2.5 flex flex-col gap-0.5">
      <div className="flex items-center gap-2 px-2 pb-2 pt-1">
        <span className="font-mono text-[0.6rem] font-bold tracking-[0.14em] text-txt-secondary">
          PROJECTS
        </span>
        <div className="flex-1" />
        <button
          aria-label="New project"
          className="w-[22px] h-[22px] grid place-items-center rounded-sm border border-border text-txt-secondary hover:bg-bg-secondary transition-colors"
        >
          <Icon.plus />
        </button>
      </div>

      <button
        onClick={() => onSelect("all")}
        className={cn(
          "flex items-center gap-2 px-2 py-1.5 rounded-sm text-left transition-colors",
          "font-mono text-[0.75rem]",
          active === "all"
            ? "text-txt-primary bg-bg-secondary"
            : "text-txt-secondary hover:bg-bg-secondary/50",
        )}
      >
        <Icon.sparkle />
        <span className="flex-1">all tasks</span>
        <span className="text-[0.6rem] text-txt-secondary/70">{totalCount}</span>
      </button>

      {projects.map((p) => {
        const isActive = active === p.id;
        return (
          <button
            key={p.id}
            onClick={() => onSelect(p.id)}
            className={cn(
              "flex items-center gap-2 px-2 py-1.5 rounded-sm text-left transition-colors",
              "font-mono text-[0.75rem]",
              isActive
                ? "text-txt-primary bg-bg-secondary"
                : "text-txt-secondary hover:bg-bg-secondary/50",
            )}
          >
            <span className="w-2 h-2 rounded-sm" style={{ background: p.color }} aria-hidden />
            <span className="flex-1 truncate">{p.name}</span>
            <span className="text-[0.6rem] text-txt-secondary/70">{p.count}</span>
          </button>
        );
      })}

      <div className="flex-1" />
      <div className="px-2.5 py-2.5 mt-2 border border-dashed border-border rounded-sm font-mono text-[0.6rem] text-txt-secondary/80 leading-[1.5]">
        ✧ tip: ask Tracker
        <br />
        "add a task to radbot"
      </div>
    </aside>
  );
}
