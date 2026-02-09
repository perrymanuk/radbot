import { useEffect, useState } from "react";
import { useAppStore } from "@/stores/app-store";
import TaskItem from "./TaskItem";
import TaskForm from "./TaskForm";
import { cn } from "@/lib/utils";

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In Progress" },
  { value: "done", label: "Done" },
];

export default function TasksPanel() {
  const tasks = useAppStore((s) => s.tasks);
  const projects = useAppStore((s) => s.projects);
  const loadTasks = useAppStore((s) => s.loadTasks);
  const loadProjects = useAppStore((s) => s.loadProjects);
  const taskStatusFilter = useAppStore((s) => s.taskStatusFilter);
  const taskProjectFilter = useAppStore((s) => s.taskProjectFilter);
  const taskSearch = useAppStore((s) => s.taskSearch);
  const setTaskStatusFilter = useAppStore((s) => s.setTaskStatusFilter);
  const setTaskProjectFilter = useAppStore((s) => s.setTaskProjectFilter);
  const setTaskSearch = useAppStore((s) => s.setTaskSearch);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    loadTasks();
    loadProjects();
  }, [loadTasks, loadProjects]);

  const filtered = tasks.filter((t) => {
    if (taskStatusFilter !== "all" && t.status !== taskStatusFilter) return false;
    if (taskProjectFilter !== "all" && t.project_id !== taskProjectFilter)
      return false;
    if (
      taskSearch &&
      !t.title?.toLowerCase().includes(taskSearch.toLowerCase()) &&
      !t.description?.toLowerCase().includes(taskSearch.toLowerCase())
    )
      return false;
    return true;
  });

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Header */}
      <div className="px-2 py-1.5 bg-bg-tertiary border-b border-border flex items-center gap-2">
        <span className="text-accent-blue text-[0.9rem] font-mono flex-1">
          Tasks
        </span>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-2 py-0.5 border border-border bg-bg-tertiary text-txt-primary text-[0.7rem] font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer"
        >
          {showForm ? "CLOSE" : "+ NEW"}
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

      {/* Filters */}
      <div className="p-1.5 border-b border-border flex flex-col gap-1">
        <div className="flex gap-1">
          {/* Status filter */}
          <select
            value={taskStatusFilter}
            onChange={(e) => setTaskStatusFilter(e.target.value)}
            className="flex-1 bg-bg-secondary text-txt-primary border border-border px-1 py-0.5 font-mono text-[0.75rem] outline-none focus:border-accent-blue h-6"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {/* Project filter */}
          <select
            value={taskProjectFilter}
            onChange={(e) => setTaskProjectFilter(e.target.value)}
            className="flex-1 bg-bg-secondary text-txt-primary border border-border px-1 py-0.5 font-mono text-[0.75rem] outline-none focus:border-accent-blue h-6"
          >
            <option value="all">All Projects</option>
            {projects.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* Search */}
        <input
          type="text"
          value={taskSearch}
          onChange={(e) => setTaskSearch(e.target.value)}
          placeholder="Search tasks..."
          className="w-full bg-bg-secondary text-txt-primary border border-border px-2 py-0.5 font-mono text-[0.75rem] outline-none focus:border-accent-blue h-6"
        />
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto p-1">
        {filtered.length === 0 ? (
          <div className="p-4 text-center text-txt-secondary text-[0.75rem] italic">
            No tasks found
          </div>
        ) : (
          filtered.map((task) => (
            <TaskItem
              key={task.task_id}
              task={task}
              onUpdated={loadTasks}
            />
          ))
        )}
      </div>
    </div>
  );
}
