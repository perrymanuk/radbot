import type { TelosEntry } from "@/lib/telos-api";
import {
  selectExplorationsForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import EntryMarkdown from "./EntryMarkdown";

interface Props {
  project: TelosEntry;
}

export default function ExplorationsTab({ project }: Props) {
  const explorations = useProjectsStore((s) =>
    selectExplorationsForProject(s, project.ref_code!),
  );

  if (explorations.length === 0) {
    return (
      <div
        className="text-[0.75rem] font-mono text-txt-secondary italic"
        data-test="projects-explorations-tab"
      >
        No explorations yet.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-test="projects-explorations-tab">
      {explorations.map((e) => (
        <div
          key={e.entry_id}
          className="border border-purple-500/30 bg-purple-500/5 rounded-sm p-3"
          data-test={`projects-exploration-${e.ref_code}`}
        >
          <div className="flex items-baseline gap-2 mb-1">
            <span className="text-[0.65rem] font-mono text-purple-400 uppercase tracking-wider">
              ⚗ {e.ref_code}
            </span>
            {e.status !== "active" && (
              <span className="text-[0.6rem] font-mono text-txt-secondary uppercase">
                {e.status}
              </span>
            )}
          </div>
          <EntryMarkdown content={e.content || ""} />
        </div>
      ))}
    </div>
  );
}
