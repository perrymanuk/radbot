import { useAppStore } from "@/stores/app-store";
import ChatPanel from "@/components/chat/ChatPanel";
import SidePanel from "./SidePanel";
import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";

export default function AppLayout() {
  const activePanel = useAppStore((s) => s.activePanel);
  const isMobile = useIsMobile();

  return (
    <div className="h-full w-full overflow-hidden flex">
      {/* Chat panel - always fills screen on mobile */}
      <div className={cn("h-full transition-all", !isMobile && activePanel ? "flex-[7_7_0%]" : "flex-1")}>
        <ChatPanel />
      </div>

      {/* Mobile: full-screen overlay */}
      {isMobile && activePanel && (
        <div className="fixed inset-0 z-50 bg-bg-primary animate-slide-in-right">
          <SidePanel />
        </div>
      )}

      {/* Desktop: side-by-side panel */}
      {!isMobile && activePanel && (
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
