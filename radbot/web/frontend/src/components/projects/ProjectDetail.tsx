import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  selectExplorationsForProject,
  selectGoalsForProject,
  selectMilestonesForProject,
  selectTasksForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import DetailHeader from "./DetailHeader";
import TabBar, { type Tab } from "./TabBar";
import OverviewTab from "./OverviewTab";
import MilestonesTab from "./MilestonesTab";
import TasksTab from "./TasksTab";
import ExplorationsTab from "./ExplorationsTab";
import GoalsTab from "./GoalsTab";
import { accentFor } from "./shared/projectAccent";

const TABS: Omit<Tab, "count">[] = [
  { key: "overview", label: "Overview", icon: "folder" },
  { key: "milestones", label: "Milestones", icon: "flag" },
  { key: "tasks", label: "Tasks", icon: "check" },
  { key: "explorations", label: "Explorations", icon: "flask" },
  { key: "goals", label: "Goals", icon: "target" },
];

type TabKey = (typeof TABS)[number]["key"];

interface Props {
  project: TelosEntry;
  onRefresh: () => void;
  refreshing: boolean;
}

export default function ProjectDetail({ project, onRefresh, refreshing }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = (searchParams.get("tab") as TabKey) || "overview";
  const accent = accentFor(project.ref_code || "");

  const counts = useProjectsStore(
    useShallow((s) => ({
      milestones: selectMilestonesForProject(s, project.ref_code!).length,
      tasks: selectTasksForProject(s, project.ref_code!).length,
      explorations: selectExplorationsForProject(s, project.ref_code!).length,
      goals: selectGoalsForProject(s, project.ref_code!).length,
    })),
  );

  const tabs: Tab[] = TABS.map((t) => ({
    ...t,
    count:
      t.key === "overview"
        ? null
        : t.key === "milestones"
        ? counts.milestones || null
        : t.key === "tasks"
        ? counts.tasks || null
        : t.key === "explorations"
        ? counts.explorations || null
        : counts.goals || null,
  }));

  const setTab = (tab: string) => {
    const next = new URLSearchParams(searchParams);
    if (tab === "overview") next.delete("tab");
    else next.set("tab", tab);
    setSearchParams(next, { replace: true });
  };

  // Keyboard shortcuts 1-5 to switch tabs
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      const map: Record<string, TabKey> = {
        "1": "overview",
        "2": "milestones",
        "3": "tasks",
        "4": "explorations",
        "5": "goals",
      };
      if (map[e.key]) setTab(map[e.key]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "var(--surface)",
      }}
      data-test="projects-detail"
    >
      <DetailHeader project={project} onRefresh={onRefresh} refreshing={refreshing} />
      <TabBar tabs={tabs} active={currentTab} setActive={setTab} accent={accent} />
      <div style={{ flex: 1, overflowY: "auto", background: "var(--bg)" }}>
        {currentTab === "overview" && <OverviewTab project={project} />}
        {currentTab === "milestones" && <MilestonesTab project={project} />}
        {currentTab === "tasks" && <TasksTab project={project} />}
        {currentTab === "explorations" && <ExplorationsTab project={project} />}
        {currentTab === "goals" && <GoalsTab project={project} />}
      </div>
    </div>
  );
}
