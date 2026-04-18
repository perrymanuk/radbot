import { useEffect, useMemo, useState } from "react";
import { useAppStore } from "@/stores/app-store";
import { Icon } from "@/components/chat/icons";
import { cn } from "@/lib/utils";
import type { Task, Project, TaskStatus } from "@/types";
import TaskProjectList from "./TaskProjectList";
import TaskLane from "./TaskLane";
import TaskRow, { type TaskData, type ProjectMeta } from "./TaskRow";
import TaskForm from "./TaskForm";

// Project color palette — stable assignment by hash of project id so the
// same project always gets the same color.
const PROJECT_COLORS = [
  "#ff9966", // sunset
  "#3584e4", // blue
  "#33FF33", // green
  "#FFBF00", // amber
  "#ff66aa", // magenta
  "#b088ff", // violet
  "#66ccff", // sky
];

function colorFor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return PROJECT_COLORS[h % PROJECT_COLORS.length];
}

function relativeAge(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "";
  const diff = Date.now() - t;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  if (hours < 24) return `${hours}h`;
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  return `${months}mo`;
}

function mapStatus(s: TaskStatus | string): TaskData["status"] {
  if (s === "in_progress") return "progress";
  if (s === "done") return "done";
  return "backlog";
}

function toTaskData(t: Task): TaskData {
  return {
    id: t.task_id,
    title: t.title,
    status: mapStatus(t.status),
    project: t.project_id,
    age: relativeAge(t.updated_at || t.created_at),
    note: t.description ? t.description.slice(0, 120) : undefined,
  };
}

function toProjects(
  projects: Project[],
  tasks: Task[],
): (ProjectMeta & { count: number })[] {
  return projects.map((p) => ({
    id: p.project_id,
    name: p.name,
    color: colorFor(p.project_id),
    count: tasks.filter((t) => t.project_id === p.project_id).length,
  }));
}

export default function TasksPanel() {
  const tasks = useAppStore((s) => s.tasks);
  const projects = useAppStore((s) => s.projects);
  const loadTasks = useAppStore((s) => s.loadTasks);
  const loadProjects = useAppStore((s) => s.loadProjects);

  const [active, setActive] = useState<string>("all");
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    loadTasks();
    loadProjects();
  }, [loadTasks, loadProjects]);

  const taskData = useMemo(() => tasks.map(toTaskData), [tasks]);
  const projectRows = useMemo(() => toProjects(projects, tasks), [projects, tasks]);

  const filtered = useMemo(
    () => (active === "all" ? taskData : taskData.filter((t) => t.project === active)),
    [taskData, active],
  );

  const projectLookup = useMemo(() => {
    const m = new Map<string, ProjectMeta>();
    for (const p of projectRows) m.set(p.id, p);
    return m;
  }, [projectRows]);

  const resolveProject = (id: string): ProjectMeta =>
    projectLookup.get(id) ?? { id, name: id || "unassigned", color: "#7a8599" };

  const progress = filtered.filter((t) => t.status === "progress");
  const backlog = filtered.filter((t) => t.status === "backlog");
  const done = filtered.filter((t) => t.status === "done");

  return (
    <div className="flex h-full bg-bg-primary text-txt-primary">
      <TaskProjectList
        projects={projectRows}
        totalCount={tasks.length}
        active={active}
        onSelect={setActive}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-2.5 border-b border-border/70 bg-bg-tertiary/40 flex-wrap">
          <div className="inline-flex items-center gap-1.5 px-1.5 py-1 rounded-sm border bg-terminal-amber/15 border-terminal-amber/40">
            <span
              className="inline-grid place-items-center w-[18px] h-[18px] rounded-[3px] font-mono text-[0.72rem] font-bold leading-none"
              style={{ background: "#FFBF00", color: "#0e1419" }}
              aria-hidden
            >
              T
            </span>
            <span className="font-mono text-[0.7rem] font-bold tracking-[0.12em] text-terminal-amber">
              TRACKER
            </span>
            <span className="font-mono text-[0.6rem] tracking-[0.1em] text-txt-secondary/80 uppercase ml-1">
              tasks
            </span>
          </div>
          <span className="font-sans text-[0.7rem] text-txt-secondary">
            {filtered.length} task{filtered.length === 1 ? "" : "s"} · sorted by status
          </span>
          <div className="flex-1" />
          <button
            onClick={() => setShowForm((v) => !v)}
            className={cn(
              "inline-flex items-center gap-1 px-2.5 py-1 rounded-sm",
              "font-mono text-[0.68rem] font-bold tracking-[0.08em]",
              showForm
                ? "bg-bg-tertiary text-txt-secondary border border-border hover:bg-bg-secondary"
                : "bg-radbot-sunset text-bg-primary border border-radbot-sunset hover:brightness-110",
              "transition-all focus:outline-none focus:ring-1 focus:ring-accent-blue",
            )}
          >
            <Icon.plus />
            {showForm ? "CLOSE" : "NEW TASK"}
          </button>
        </div>

        {/* Create form */}
        {showForm && (
          <TaskForm
            projects={projects}
            onCreated={() => {
              setShowForm(false);
              loadTasks();
            }}
          />
        )}

        {/* Lanes */}
        <div
          className="flex-1 overflow-y-auto p-4 grid gap-4"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}
        >
          <TaskLane label="IN PROGRESS" color="#ff9966" count={progress.length} icon={<Icon.half />}>
            {progress.map((t) => (
              <TaskRow key={t.id} t={t} project={resolveProject(t.project)} />
            ))}
          </TaskLane>
          <TaskLane label="BACKLOG" color="#3584e4" count={backlog.length} icon={<Icon.circle />}>
            {backlog.map((t) => (
              <TaskRow key={t.id} t={t} project={resolveProject(t.project)} />
            ))}
          </TaskLane>
          <TaskLane label="DONE" color="#33FF33" count={done.length} icon={<Icon.check />}>
            {done.map((t) => (
              <TaskRow key={t.id} t={t} project={resolveProject(t.project)} />
            ))}
          </TaskLane>
        </div>
      </div>
    </div>
  );
}
