import type { TelosEntry } from "@/lib/telos-api";
import {
  bucketTasks,
  selectTasksForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import TaskRow from "./TaskRow";

interface Props {
  project: TelosEntry;
}

export default function TasksTab({ project }: Props) {
  const tasks = useProjectsStore((s) =>
    selectTasksForProject(s, project.ref_code!),
  );
  const buckets = bucketTasks(tasks);

  if (tasks.length === 0) {
    return (
      <div
        className="text-[0.75rem] font-mono text-txt-secondary italic"
        data-test="projects-tasks-tab"
      >
        No tasks yet.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-test="projects-tasks-tab">
      <Section label="In progress" tasks={buckets.inprogress} bucket="inprogress" />
      <Section label="Backlog" tasks={buckets.backlog} bucket="backlog" />
      <Section label="Other" tasks={buckets.other} bucket="other" />
      <Section label="Done" tasks={buckets.done} bucket="done" />
    </div>
  );
}

function Section({
  label,
  tasks,
  bucket,
}: {
  label: string;
  tasks: TelosEntry[];
  bucket: string;
}) {
  if (tasks.length === 0) return null;
  return (
    <div className="border border-border rounded-sm">
      <div className="px-3 py-1.5 bg-bg-tertiary border-b border-border text-[0.65rem] font-mono uppercase tracking-wider text-txt-secondary">
        {label} ({tasks.length})
      </div>
      <div className="divide-y divide-border/40">
        {tasks.map((t) => (
          <TaskRow key={t.entry_id} task={t} bucket={bucket} />
        ))}
      </div>
    </div>
  );
}
