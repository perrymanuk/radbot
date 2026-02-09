import { useAppStore } from "@/stores/app-store";
import ChatPanel from "@/components/chat/ChatPanel";
import SidePanel from "./SidePanel";
import { cn } from "@/lib/utils";

export default function AppLayout() {
  const activePanel = useAppStore((s) => s.activePanel);

  return (
    <div className="h-screen w-screen overflow-hidden flex">
      {/* Chat panel - grows to fill when side panel is closed */}
      <div className={cn("h-full transition-all", activePanel ? "flex-[7_7_0%]" : "flex-1")}>
        <ChatPanel />
      </div>

      {/* Side panel - slides in/out */}
      {activePanel && (
        <>
          <div className="w-1 bg-border hover:bg-accent-blue transition-colors cursor-col-resize flex-shrink-0" />
          <div className="h-full flex-[3_3_0%] min-w-[200px] max-w-[50%]">
            <SidePanel />
          </div>
        </>
      )}
    </div>
  );
}
