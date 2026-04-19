import { useState } from "react";
import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  bucketTasks,
  selectTasksForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import TaskLine from "./shared/TaskLine";
import { accentFor } from "./shared/projectAccent";

type Filter = "all" | "open" | "inprogress" | "backlog" | "done";

interface Props {
  project: TelosEntry;
}

export default function TasksTab({ project }: Props) {
  const accent = accentFor(project.ref_code || "");
  const [filter, setFilter] = useState<Filter>("all");
  const tasks = useProjectsStore(
    useShallow((s) => selectTasksForProject(s, project.ref_code!)),
  );
  const openTaskEditor = useProjectsStore((s) => s.openTaskEditor);
  const b = bucketTasks(tasks);

  const show =
    filter === "all"
      ? tasks
      : filter === "open"
      ? tasks.filter(
          (t) => {
            const status = ((t.metadata || {}).task_status || "").toString().toLowerCase();
            return !(status === "done" || status === "complete" || status === "completed");
          },
        )
      : filter === "inprogress"
      ? b.inprogress
      : filter === "backlog"
      ? b.backlog
      : b.done;

  const chip = (id: Filter, label: string, count: number, color: string) => {
    const isActive = filter === id;
    return (
      <button
        key={id}
        onClick={() => setFilter(id)}
        style={{
          padding: "5px 10px",
          borderRadius: 4,
          fontFamily: "var(--p-mono)",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.1em",
          color: isActive ? color : "var(--text-mute)",
          background: isActive
            ? `color-mix(in oklch, ${color} 14%, transparent)`
            : "transparent",
          border: `1px solid ${isActive ? `color-mix(in oklch, ${color} 36%, transparent)` : "var(--p-border)"}`,
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
        }}
        data-test={`projects-task-filter-${id}`}
      >
        {label}
        <span
          style={{
            fontSize: 9,
            padding: "0 4px",
            borderRadius: 2,
            background: isActive ? color : "var(--surface-2)",
            color: isActive ? "var(--bg)" : "var(--text-dim)",
          }}
        >
          {count}
        </span>
      </button>
    );
  };

  return (
    <div
      style={{ display: "flex", flexDirection: "column", height: "100%" }}
      data-test="projects-tasks-tab"
    >
      <div
        className="projects-tasks-chiprow"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "10px 22px",
          background: "var(--bg-sunk)",
          borderBottom: "1px solid var(--border-soft)",
          flexWrap: "wrap",
        }}
      >
        {chip("all", "ALL", tasks.length, "var(--text)")}
        {chip("open", "OPEN", b.inprogress.length + b.backlog.length + b.other.length, accent)}
        {chip("inprogress", "IN PROGRESS", b.inprogress.length, "var(--sunset)")}
        {chip("backlog", "BACKLOG", b.backlog.length, "var(--sky)")}
        {chip("done", "DONE", b.done.length, "var(--crt)")}
        <span style={{ flex: 1 }} />
        <span
          style={{
            fontFamily: "var(--p-mono)",
            fontSize: 10,
            color: "var(--text-dim)",
          }}
        >
          sorted by status · newest first
        </span>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {show.length === 0 ? (
          <div
            style={{
              padding: 30,
              textAlign: "center",
              fontFamily: "var(--p-mono)",
              fontSize: 12,
              color: "var(--text-dim)",
            }}
          >
            no tasks match.
          </div>
        ) : (
          show.map((t) => (
            <TaskLine
              key={t.entry_id}
              task={t}
              accent={accent}
              onClick={openTaskEditor}
            />
          ))
        )}
      </div>
    </div>
  );
}
