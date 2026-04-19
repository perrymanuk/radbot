import { useAppStore } from "@/stores/app-store";
import SessionsPanel from "@/components/sessions/SessionsPanel";
import EventsPanel from "@/components/events/EventsPanel";

export default function SidePanel() {
  const activePanel = useAppStore((s) => s.activePanel);

  switch (activePanel) {
    case "sessions":
      return <SessionsPanel />;
    case "events":
      return <EventsPanel />;
    default:
      return null;
  }
}
