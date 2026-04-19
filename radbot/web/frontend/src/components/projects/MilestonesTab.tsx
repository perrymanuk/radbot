import { useState } from "react";
import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  bucketTasks,
  selectMilestonesForProject,
  selectTasksForMilestone,
  selectUnmilestonedTasks,
  useProjectsStore,
} from "@/stores/projects-store";
import { cn } from "@/lib/utils";
import EntryMarkdown from "./EntryMarkdown";
import TaskRow from "./TaskRow";

interface Props {
  project: TelosEntry;
}

export default function MilestonesTab({ project }: Props) {
  const milestones = useProjectsStore(
    useShallow((s) => selectMilestonesForProject(s, project.ref_code!)),
  );
  const unmilestoned = useProjectsStore(
    useShallow((s) => selectUnmilestonedTasks(s, project.ref_code!)),
  );

  return (
    <div className="space-y-3" data-test="projects-milestones-tab">
      {milestones.length === 0 && unmilestoned.length === 0 && (
        <div className="text-[0.75rem] font-mono text-txt-secondary italic">
          No milestones yet.
        </div>
      )}

      {milestones.map((m) => (
        <MilestoneCard key={m.entry_id} milestone={m} />
      ))}

      {unmilestoned.length > 0 && (
        <div
          className="border border-yellow-500/40 bg-yellow-500/5 rounded-sm"
          data-test="projects-unmilestoned"
        >
          <div className="px-3 py-1.5 border-b border-yellow-500/30 flex items-center justify-between">
            <span className="text-[0.7rem] font-mono uppercase tracking-wider text-yellow-500">
              ⚠ Unmilestoned
            </span>
            <span className="text-[0.65rem] font-mono text-txt-secondary">
              {unmilestoned.length} task{unmilestoned.length === 1 ? "" : "s"} need triage
            </span>
          </div>
          <div className="divide-y divide-border/40">
            {unmilestoned.map((t) => (
              <TaskRow key={t.entry_id} task={t} bucket={taskBucket(t)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function taskBucket(t: TelosEntry): string {
  const raw = ((t.metadata || {}).task_status || "").toString().toLowerCase();
  if (raw === "inprogress" || raw === "in_progress" || raw === "in progress")
    return "inprogress";
  if (raw === "done" || raw === "complete" || raw === "completed") return "done";
  if (raw === "backlog" || raw === "todo" || raw === "pending" || raw === "")
    return "backlog";
  return "other";
}

function MilestoneCard({ milestone }: { milestone: TelosEntry }) {
  const [expanded, setExpanded] = useState(true);
  const [showDone, setShowDone] = useState(false);
  const tasks = useProjectsStore(
    useShallow((s) => selectTasksForMilestone(s, milestone.ref_code!)),
  );
  const buckets = bucketTasks(tasks);
  const total = tasks.length;
  const done = buckets.done.length;
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  const firstLine = (milestone.content || "").split("\n")[0];

  return (
    <div
      className="border border-border rounded-sm bg-bg-secondary/50"
      data-test={`projects-milestone-${milestone.ref_code}`}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-bg-tertiary transition-colors"
      >
        <span className="text-txt-secondary font-mono text-xs">
          {expanded ? "▾" : "▸"}
        </span>
        <span className="text-[0.65rem] font-mono text-accent-blue uppercase tracking-wider">
          {milestone.ref_code}
        </span>
        <span className="text-[0.8rem] font-mono text-txt-primary flex-1 truncate">
          {firstLine}
        </span>
        <span className="text-[0.65rem] font-mono text-txt-secondary">
          {done}/{total} · {pct}%
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border/40">
          {milestone.content && milestone.content !== firstLine && (
            <div className="px-3 py-2 border-b border-border/40">
              <EntryMarkdown content={milestone.content} />
            </div>
          )}

          {total === 0 ? (
            <div className="px-3 py-2 text-[0.7rem] font-mono text-txt-secondary italic">
              No tasks.
            </div>
          ) : (
            <div>
              <TaskBucket label="In progress" tasks={buckets.inprogress} bucket="inprogress" />
              <TaskBucket label="Backlog" tasks={buckets.backlog} bucket="backlog" />
              <TaskBucket label="Other" tasks={buckets.other} bucket="other" />
              <div>
                <button
                  onClick={() => setShowDone((v) => !v)}
                  className={cn(
                    "w-full px-3 py-1 text-left text-[0.65rem] font-mono uppercase tracking-wider",
                    "text-txt-secondary hover:bg-bg-tertiary",
                  )}
                >
                  {showDone ? "▾" : "▸"} Done ({buckets.done.length})
                </button>
                {showDone && (
                  <div className="divide-y divide-border/40">
                    {buckets.done.map((t) => (
                      <TaskRow key={t.entry_id} task={t} bucket="done" />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TaskBucket({
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
    <div>
      <div className="px-3 py-1 text-[0.65rem] font-mono uppercase tracking-wider text-txt-secondary bg-bg-primary/50">
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
