import type { TelosEntry } from "@/lib/telos-api";
import {
  selectGoalsForProject,
  selectMilestonesForProject,
  selectTasksForProject,
  bucketTasks,
  useProjectsStore,
} from "@/stores/projects-store";
import EntryMarkdown from "./EntryMarkdown";

interface Props {
  project: TelosEntry;
}

export default function OverviewTab({ project }: Props) {
  const goals = useProjectsStore((s) =>
    selectGoalsForProject(s, project.ref_code!),
  );
  const milestones = useProjectsStore((s) =>
    selectMilestonesForProject(s, project.ref_code!),
  );
  const tasks = useProjectsStore((s) =>
    selectTasksForProject(s, project.ref_code!),
  );
  const buckets = bucketTasks(tasks);
  const total = tasks.length;
  const done = buckets.done.length;
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);

  return (
    <div className="space-y-4" data-test="projects-overview-tab">
      {goals.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {goals.map((g) => (
            <span
              key={g.entry_id}
              className="text-[0.65rem] font-mono px-2 py-0.5 rounded-sm bg-accent-blue/15 text-accent-blue border border-accent-blue/40"
              title={g.content}
            >
              {g.ref_code} · {(g.content || "").split("\n")[0].slice(0, 60)}
            </span>
          ))}
        </div>
      )}

      <div className="bg-bg-tertiary border border-border rounded-sm p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[0.7rem] font-mono uppercase tracking-wider text-txt-secondary">
            Progress
          </span>
          <span className="text-[0.75rem] font-mono text-txt-primary">
            {done}/{total} · {pct}%
          </span>
        </div>
        <div className="h-1 bg-bg-primary rounded-sm overflow-hidden">
          <div
            className="h-full bg-accent-blue transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex gap-3 mt-2 text-[0.65rem] font-mono text-txt-secondary">
          <span>{milestones.length} milestones</span>
          <span>·</span>
          <span>{buckets.inprogress.length} in progress</span>
          <span>·</span>
          <span>{buckets.backlog.length} backlog</span>
        </div>
      </div>

      <EntryMarkdown content={project.content || "_(no description)_"} />
    </div>
  );
}
