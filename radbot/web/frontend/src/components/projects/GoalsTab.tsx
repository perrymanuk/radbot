import type { TelosEntry } from "@/lib/telos-api";
import {
  selectGoalsForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import EntryMarkdown from "./EntryMarkdown";

interface Props {
  project: TelosEntry;
}

export default function GoalsTab({ project }: Props) {
  const goals = useProjectsStore((s) =>
    selectGoalsForProject(s, project.ref_code!),
  );

  if (goals.length === 0) {
    return (
      <div
        className="text-[0.75rem] font-mono text-txt-secondary italic"
        data-test="projects-goals-tab"
      >
        No goals attached to this project.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-test="projects-goals-tab">
      {goals.map((g) => (
        <div
          key={g.entry_id}
          className="border border-accent-blue/30 bg-accent-blue/5 rounded-sm p-3"
          data-test={`projects-goal-${g.ref_code}`}
        >
          <div className="flex items-baseline gap-2 mb-1">
            <span className="text-[0.65rem] font-mono text-accent-blue uppercase tracking-wider">
              ◎ {g.ref_code}
            </span>
            {g.status !== "active" && (
              <span className="text-[0.6rem] font-mono text-txt-secondary uppercase">
                {g.status}
              </span>
            )}
          </div>
          <EntryMarkdown content={g.content || ""} />
        </div>
      ))}
    </div>
  );
}
