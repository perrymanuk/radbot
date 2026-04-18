import { cn } from "@/lib/utils";
import { Icon } from "@/components/chat/icons";

// ─────────────────────────────────────────────────────────
// TASK ROW
//
// A single task card rendered inside a TaskLane. Shows status
// icon (circle/half/check), title, project pill, age, optional
// note.
//
// ── Backend surfacing ────────────────────────────────────
// Expects the existing `Task` shape from the tracker service
// (see radbot/tools/tasks.py). Minimal fields:
//   { id, title, status: "progress"|"done"|"backlog",
//     project: string, age: string, note?: string }
//
// The `project` arg carries display metadata (name + color) so
// the row doesn't need to hit a lookup store.
// ─────────────────────────────────────────────────────────

export interface TaskData {
  id: string;
  title: string;
  status: "progress" | "done" | "backlog";
  project: string;
  age: string;
  note?: string;
}

export interface ProjectMeta {
  id: string;
  name: string;
  color: string; // CSS color
}

function StatusIcon({ status }: { status: TaskData["status"] }) {
  if (status === "progress") return <span className="text-radbot-sunset"><Icon.half /></span>;
  if (status === "done") return <span className="text-terminal-green"><Icon.check /></span>;
  return <span className="text-txt-secondary/70"><Icon.circle /></span>;
}

export default function TaskRow({ t, project }: { t: TaskData; project: ProjectMeta }) {
  const done = t.status === "done";
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 px-3 py-2.5 rounded",
        "border border-border/70 bg-bg-secondary/40",
        "hover:bg-bg-secondary transition-colors",
      )}
    >
      <StatusIcon status={t.status} />
      <div className="flex-1 min-w-0">
        <div
          className={cn(
            "font-sans text-[0.8125rem] text-txt-primary leading-snug",
            done && "line-through opacity-55",
          )}
        >
          {t.title}
        </div>
        <div className="flex gap-2 mt-1 items-center flex-wrap font-mono text-[0.6rem] text-txt-secondary">
          <span
            className="inline-flex items-center gap-1 px-1.5 py-px rounded-sm border"
            style={{
              background: `color-mix(in oklch, ${project.color} 10%, transparent)`,
              color: project.color,
              borderColor: `color-mix(in oklch, ${project.color} 22%, transparent)`,
            }}
          >
            <span
              className="w-1 h-1 rounded-[1px]"
              style={{ background: project.color }}
              aria-hidden
            />
            {project.name}
          </span>
          <span>·</span>
          <span>{t.age}</span>
          {t.note && (
            <>
              <span>·</span>
              <span className="italic text-txt-secondary/70 font-sans">{t.note}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
