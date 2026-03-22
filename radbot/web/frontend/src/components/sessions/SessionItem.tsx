import { useState } from "react";
import { useAppStore } from "@/stores/app-store";
import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface Props {
  session: Session;
}

function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;

  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;

  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;

  const weeks = Math.floor(days / 7);
  if (weeks < 4) return `${weeks}w ago`;

  return new Date(dateStr).toLocaleDateString();
}

export default function SessionItem({ session }: Props) {
  const currentSessionId = useAppStore((s) => s.sessionId);
  const switchSession = useAppStore((s) => s.switchSession);
  const deleteSession = useAppStore((s) => s.deleteSession);
  const setActivePanel = useAppStore((s) => s.setActivePanel);
  const isActive = session.id === currentSessionId;
  const isMobile = useIsMobile();
  const [confirming, setConfirming] = useState(false);

  const handleClick = () => {
    if (confirming) return;
    switchSession(session.id);
    if (isMobile) setActivePanel(null);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirming(true);
  };

  const confirmDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteSession(session.id);
    setConfirming(false);
  };

  const cancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirming(false);
  };

  if (confirming) {
    return (
      <div className="px-2 py-2 sm:py-1.5 mb-0.5 border border-terminal-red/50 bg-terminal-red/10 text-[0.75rem]">
        <div className="text-terminal-red font-mono mb-1">Delete this session?</div>
        <div className="flex gap-2">
          <button
            onClick={confirmDelete}
            className="px-2 py-0.5 border border-terminal-red text-terminal-red text-[0.7rem] font-mono uppercase hover:bg-terminal-red hover:text-bg-primary transition-all"
          >
            Yes
          </button>
          <button
            onClick={cancelDelete}
            className="px-2 py-0.5 border border-border text-txt-secondary text-[0.7rem] font-mono uppercase hover:text-txt-primary transition-all"
          >
            No
          </button>
        </div>
      </div>
    );
  }

  const timeStr = relativeTime(session.last_message_at || session.created_at);

  return (
    <div
      onClick={handleClick}
      className={cn(
        "group px-2 py-2 sm:py-1.5 mb-0.5 border border-border bg-bg-secondary text-[0.75rem] cursor-pointer transition-all",
        "hover:border-accent-blue hover:bg-bg-tertiary",
        isActive && "border-accent-blue bg-bg-tertiary shadow-[0_0_0_1px_#3584e4]",
      )}
    >
      <div className="flex items-center gap-2">
        {isActive && (
          <span className="w-2 h-2 flex-shrink-0 rounded-full bg-terminal-green shadow-[0_0_5px_rgba(51,255,51,0.4)]" />
        )}
        <span className="text-txt-primary flex-1 truncate font-mono">
          {session.name || `Session ${session.id.slice(0, 8)}`}
        </span>
        <button
          onClick={handleDelete}
          className={cn(
            "px-1 text-txt-secondary hover:text-terminal-red transition-all text-[0.7rem] font-mono flex-shrink-0",
            isMobile ? "opacity-100" : "opacity-0 group-hover:opacity-100",
          )}
          aria-label="Delete session"
        >
          ×
        </button>
      </div>
      {session.description && (
        <div className="text-txt-secondary text-[0.65rem] mt-0.5 truncate italic pl-0 sm:pl-4">
          {session.description}
        </div>
      )}
      <div className="text-txt-secondary text-[0.65rem] mt-0.5 truncate pl-0 sm:pl-4">
        {timeStr && <span>{timeStr}</span>}
        {session.preview && (
          <span className={timeStr ? "ml-2" : ""}>{session.preview}</span>
        )}
      </div>
    </div>
  );
}
