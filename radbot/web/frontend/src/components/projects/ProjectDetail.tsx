import { useSearchParams } from "react-router-dom";
import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import { cn } from "@/lib/utils";
import {
  selectExplorationsForProject,
  selectGoalsForProject,
  selectMilestonesForProject,
  selectTasksForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import OverviewTab from "./OverviewTab";
import MilestonesTab from "./MilestonesTab";
import TasksTab from "./TasksTab";
import ExplorationsTab from "./ExplorationsTab";
import GoalsTab from "./GoalsTab";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "milestones", label: "Milestones" },
  { key: "tasks", label: "Tasks" },
  { key: "explorations", label: "Explorations" },
  { key: "goals", label: "Goals" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

interface Props {
  project: TelosEntry;
}

export default function ProjectDetail({ project }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = (searchParams.get("tab") as TabKey) || "overview";

  const counts = useProjectsStore(
    useShallow((s) => ({
      milestones: selectMilestonesForProject(s, project.ref_code!).length,
      tasks: selectTasksForProject(s, project.ref_code!).length,
      explorations: selectExplorationsForProject(s, project.ref_code!).length,
      goals: selectGoalsForProject(s, project.ref_code!).length,
    })),
  );

  const tabCount = (key: TabKey) => {
    if (key === "milestones") return counts.milestones;
    if (key === "tasks") return counts.tasks;
    if (key === "explorations") return counts.explorations;
    if (key === "goals") return counts.goals;
    return null;
  };

  const setTab = (tab: TabKey) => {
    const next = new URLSearchParams(searchParams);
    if (tab === "overview") next.delete("tab");
    else next.set("tab", tab);
    setSearchParams(next, { replace: true });
  };

  const firstLine = (project.content || "").split("\n")[0];

  return (
    <div className="flex flex-col h-full bg-bg-primary" data-test="projects-detail">
      <div className="px-4 py-2.5 bg-bg-tertiary border-b border-border flex items-baseline gap-3 flex-shrink-0">
        <span className="text-[0.7rem] font-mono text-accent-blue uppercase tracking-wider">
          {project.ref_code}
        </span>
        <span className="text-sm font-mono text-txt-primary truncate">
          {firstLine}
        </span>
        {project.status !== "active" && (
          <span className="ml-auto text-[0.65rem] font-mono text-txt-secondary uppercase">
            {project.status}
          </span>
        )}
      </div>

      <div className="flex border-b border-border bg-bg-secondary flex-shrink-0 overflow-x-auto">
        {TABS.map((t) => {
          const active = t.key === currentTab;
          const count = tabCount(t.key);
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-3 py-1.5 text-[0.7rem] font-mono uppercase tracking-wider",
                "border-b-2 transition-colors whitespace-nowrap",
                active
                  ? "text-accent-blue border-accent-blue"
                  : "text-txt-secondary border-transparent hover:text-txt-primary",
              )}
              data-test={`projects-tab-${t.key}`}
            >
              {t.label}
              {count !== null && (
                <span className="ml-1.5 opacity-60">{count}</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {currentTab === "overview" && <OverviewTab project={project} />}
        {currentTab === "milestones" && <MilestonesTab project={project} />}
        {currentTab === "tasks" && <TasksTab project={project} />}
        {currentTab === "explorations" && <ExplorationsTab project={project} />}
        {currentTab === "goals" && <GoalsTab project={project} />}
      </div>
    </div>
  );
}
