import { useAppStore } from "@/stores/app-store";
import SessionsPanel from "@/components/sessions/SessionsPanel";
import TasksPanel from "@/components/tasks/TasksPanel";
import EventsPanel from "@/components/events/EventsPanel";

export default function SidePanel() {
  const activePanel = useAppStore((s) => s.activePanel);

  switch (activePanel) {
    case "sessions":
      return <SessionsPanel />;
    case "tasks":
      return <TasksPanel />;
    case "events":
      return <EventsPanel />;
    default:
      return null;
  }
}
