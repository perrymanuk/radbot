import { useState } from "react";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";
import type { Task, TaskStatus } from "@/types";

interface Props {
  task: Task;
  onUpdated: () => void;
}

const statusColors: Record<TaskStatus, string> = {
  backlog: "bg-terminal-amber shadow-[0_0_5px_rgba(255,191,0,0.4)]",
  in_progress: "bg-accent-blue shadow-[0_0_5px_rgba(53,132,228,0.4)] animate-pulse-blue",
  done: "bg-terminal-green shadow-[0_0_5px_rgba(51,255,51,0.4)]",
};

const borderColors: Record<TaskStatus, string> = {
  backlog: "border-l-terminal-amber",
  in_progress: "border-l-accent-blue",
  done: "border-l-terminal-green",
};

const bgColors: Record<TaskStatus, string> = {
  backlog: "bg-terminal-amber/5",
  in_progress: "bg-accent-blue/10",
  done: "bg-terminal-green/5 opacity-80",
};

const nextStatus: Record<TaskStatus, TaskStatus> = {
  backlog: "in_progress",
  in_progress: "done",
  done: "backlog",
};

const STATUS_OPTIONS: { value: TaskStatus; label: string }[] = [
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In Progress" },
  { value: "done", label: "Done" },
];

export default function TaskItem({ task, onUpdated }: Props) {
  const status = (task.status as TaskStatus) || "backlog";
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description || "");
  const [editStatus, setEditStatus] = useState<TaskStatus>(status);

  const cycleStatus = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.updateTask(task.task_id, { status: nextStatus[status] });
      onUpdated();
    } catch (err) {
      console.error("Failed to update task status:", err);
    }
  };

  const saveEdit = async () => {
    try {
      await api.updateTask(task.task_id, {
        title,
        description,
        status: editStatus,
      });
      setEditing(false);
      onUpdated();
    } catch (err) {
      console.error("Failed to update task:", err);
    }
  };

  const deleteTask = async () => {
    try {
      await api.deleteTask(task.task_id);
      onUpdated();
    } catch (err) {
      console.error("Failed to delete task:", err);
    }
  };

  if (editing) {
    return (
      <div
        className={cn(
          "px-2 py-1.5 mb-0.5 border-l-[3px] border border-accent-blue bg-bg-tertiary",
          "text-[0.75rem]",
          borderColors[editStatus],
        )}
      >
        {/* Title */}
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Task title..."
          className="w-full bg-bg-secondary text-txt-primary border border-border px-2 py-1 font-mono text-[0.75rem] outline-none focus:border-accent-blue mb-1"
        />
        {/* Description */}
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description..."
          rows={2}
          className="w-full bg-bg-secondary text-txt-primary border border-border px-2 py-1 font-mono text-[0.75rem] outline-none focus:border-accent-blue mb-1 resize-none"
        />
        {/* Status select */}
        <select
          value={editStatus}
          onChange={(e) => setEditStatus(e.target.value as TaskStatus)}
          className="w-full bg-bg-secondary text-txt-primary border border-border px-1 py-0.5 font-mono text-[0.75rem] outline-none focus:border-accent-blue mb-1.5"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {/* Action buttons */}
        <div className="flex gap-1">
          <button
            onClick={saveEdit}
            className="px-2 py-0.5 border border-terminal-green bg-bg-tertiary text-terminal-green text-[0.7rem] font-mono uppercase tracking-wider hover:bg-terminal-green hover:text-bg-primary transition-all cursor-pointer"
          >
            SAVE
          </button>
          <button
            onClick={() => {
              setEditing(false);
              setTitle(task.title);
              setDescription(task.description || "");
              setEditStatus(status);
            }}
            className="px-2 py-0.5 border border-border bg-bg-tertiary text-txt-primary text-[0.7rem] font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer"
          >
            CANCEL
          </button>
          <button
            onClick={deleteTask}
            className="px-2 py-0.5 border border-terminal-red bg-bg-tertiary text-terminal-red text-[0.7rem] font-mono uppercase tracking-wider hover:bg-terminal-red hover:text-bg-primary transition-all cursor-pointer ml-auto"
          >
            DEL
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={() => setEditing(true)}
      className={cn(
        "px-2 py-1 mb-0.5 border-l-[3px] border border-border bg-bg-secondary",
        "text-[0.75rem] cursor-pointer transition-all",
        "hover:border-accent-blue hover:bg-bg-tertiary hover:shadow-[0_4px_8px_rgba(0,0,0,0.5)] hover:-translate-y-px",
        "flex items-center gap-1",
        borderColors[status],
        bgColors[status],
      )}
    >
      {/* Status dot - clickable to cycle */}
      <button
        onClick={cycleStatus}
        className={cn(
          "w-2.5 h-2.5 rounded-full border border-border flex-shrink-0",
          statusColors[status],
        )}
        title={`Status: ${status} (click to cycle)`}
      />

      {/* Content */}
      <span className="flex-1 truncate text-txt-primary font-normal tracking-[0.3px] leading-tight">
        {task.title || task.description}
      </span>

      {/* Project badge */}
      {task.project_name && (
        <span className="text-[0.65rem] text-terminal-amber bg-bg-tertiary px-1 py-0.5 border border-terminal-amber/30 tracking-wider font-medium whitespace-nowrap max-w-[80px] truncate ml-auto">
          {task.project_name}
        </span>
      )}
    </div>
  );
}
