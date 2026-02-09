import { useState } from "react";
import * as api from "@/lib/api";
import type { Project } from "@/types";

interface Props {
  projects: Project[];
  onCreated: () => void;
}

export default function TaskForm({ projects, onCreated }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [projectId, setProjectId] = useState(projects[0]?.project_id ?? "");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !projectId) return;

    setSubmitting(true);
    try {
      await api.createTask({
        title: title.trim(),
        description: description.trim(),
        project_id: projectId,
      });
      setTitle("");
      setDescription("");
      onCreated();
    } catch (err) {
      console.error("Failed to create task:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="p-2 border-b border-border bg-bg-secondary space-y-1.5"
    >
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Task title..."
        className="w-full bg-bg-tertiary text-txt-primary border border-border px-2 py-1 font-mono text-[0.75rem] outline-none focus:border-accent-blue"
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description (optional)..."
        rows={2}
        className="w-full bg-bg-tertiary text-txt-primary border border-border px-2 py-1 font-mono text-[0.75rem] outline-none focus:border-accent-blue resize-none"
      />
      <div className="flex gap-1">
        <select
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="flex-1 bg-bg-tertiary text-txt-primary border border-border px-1 py-0.5 font-mono text-[0.75rem] outline-none focus:border-accent-blue"
        >
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={submitting || !title.trim() || !projectId}
          className="px-3 py-0.5 border border-border bg-bg-tertiary text-txt-primary text-[0.7rem] font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {submitting ? "..." : "ADD"}
        </button>
      </div>
    </form>
  );
}
