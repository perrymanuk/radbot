import { useState } from "react";
import { useAppStore } from "@/stores/app-store";
import { cn } from "@/lib/utils";
import type { ConnectionStatus } from "@/types";

function StatusDot({ status }: { status: ConnectionStatus }) {
  const colors: Record<ConnectionStatus, string> = {
    active: "bg-terminal-green shadow-[0_0_5px_rgba(51,255,51,0.4)]",
    thinking:
      "bg-terminal-amber shadow-[0_0_5px_rgba(255,191,0,0.4)] animate-pulse-blue",
    connecting: "bg-terminal-amber",
    reconnecting: "bg-terminal-amber animate-pulse",
    disconnected: "bg-terminal-red",
    error: "bg-terminal-red",
  };

  return (
    <span
      className={cn("inline-block w-2.5 h-2.5 rounded-full", colors[status])}
      role="status"
      aria-label={`Connection status: ${status}`}
    />
  );
}

export default function ChatHeader() {
  const status = useAppStore((s) => s.connectionStatus);
  const agentInfo = useAppStore((s) => s.agentInfo);
  const togglePanel = useAppStore((s) => s.togglePanel);
  const activePanel = useAppStore((s) => s.activePanel);
  const createNewSession = useAppStore((s) => s.createNewSession);
  const [ttsAutoPlay, setTtsAutoPlay] = useState(
    () => localStorage.getItem("radbot_tts_autoplay") === "true",
  );

  const toggleTtsAutoPlay = () => {
    const next = !ttsAutoPlay;
    setTtsAutoPlay(next);
    localStorage.setItem("radbot_tts_autoplay", String(next));
  };

  const agentName = agentInfo?.name ?? "BETO";
  const modelName = agentInfo?.model ?? "";

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-bg-tertiary border-b border-border min-h-[44px] md:min-h-[40px] flex-shrink-0 z-10">
      {/* Left: title + status */}
      <div className="flex items-center gap-2 min-w-0">
        <h1 className="text-sm sm:text-[0.85rem] tracking-wider font-normal text-txt-secondary uppercase font-mono m-0 whitespace-nowrap">
          <span className="hidden sm:inline">RadBot</span>
          <span className="sm:hidden">RB</span>
        </h1>
        <StatusDot status={status} />
        <span className="text-[0.75rem] text-txt-secondary hidden sm:inline">
          <span className="text-terminal-amber font-bold">{agentName}</span>
          {modelName && (
            <span className="text-txt-secondary/70 ml-2">{modelName}</span>
          )}
        </span>
      </div>

      {/* Right: action buttons + panel nav */}
      <div className="flex items-center gap-3 flex-shrink-0">
        {/* Action buttons group */}
        <div className="flex gap-1.5">
          <button
            onClick={() => createNewSession()}
            aria-label="Create new session"
            className={cn(
              "px-2 sm:px-2.5 py-1.5 sm:py-1 border text-[0.72rem] sm:text-[0.7rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
              "flex items-center gap-1 min-h-[40px] sm:min-h-0",
              "bg-bg-tertiary text-terminal-green border-terminal-green hover:bg-terminal-green hover:text-bg-primary",
              "focus:outline-none focus:ring-1 focus:ring-terminal-green",
            )}
          >
            <span className="hidden sm:inline">+ NEW</span>
            <span className="sm:hidden">+</span>
          </button>
          <button
            onClick={toggleTtsAutoPlay}
            aria-label={ttsAutoPlay ? "Disable auto text-to-speech" : "Enable auto text-to-speech"}
            className={cn(
              "px-2 sm:px-2.5 py-1.5 sm:py-1 border text-[0.72rem] sm:text-[0.7rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
              "flex items-center gap-1 min-h-[40px] sm:min-h-0",
              "focus:outline-none focus:ring-1 focus:ring-accent-blue",
              ttsAutoPlay
                ? "bg-terminal-green/15 text-terminal-green border-terminal-green/50"
                : "bg-bg-tertiary text-txt-secondary border-border hover:text-txt-primary hover:border-txt-secondary",
            )}
          >
            <span className="hidden sm:inline">{ttsAutoPlay ? "TTS:ON" : "TTS:OFF"}</span>
            <span className="sm:hidden">TTS</span>
          </button>
        </div>

        {/* Separator */}
        <div className="w-px h-5 bg-border hidden sm:block" />

        {/* Navigation tabs group */}
        <div className="flex gap-0.5 bg-bg-primary/50 p-0.5 rounded-sm">
          <NavTab
            label="SESS"
            ariaLabel="Sessions panel"
            active={activePanel === "sessions"}
            onClick={() => togglePanel("sessions")}
          />
          <NavTab
            label="TASKS"
            ariaLabel="Tasks panel"
            active={activePanel === "tasks"}
            onClick={() => togglePanel("tasks")}
          />
          <NavTab
            label="EVENTS"
            mobileLabel="EVT"
            ariaLabel="Events panel"
            active={activePanel === "events"}
            onClick={() => togglePanel("events")}
          />
          <a
            href="/terminal"
            aria-label="Open terminal"
            className={cn(
              "px-2 sm:px-2.5 py-1.5 sm:py-1 text-[0.72rem] sm:text-[0.7rem] font-mono uppercase tracking-wider transition-all cursor-pointer no-underline",
              "flex items-center gap-1.5 sm:gap-1 min-h-[40px] sm:min-h-0",
              "text-terminal-amber hover:bg-terminal-amber/15 hover:text-terminal-amber",
              "focus:outline-none focus:ring-1 focus:ring-terminal-amber",
            )}
          >
            <span className="hidden sm:inline">TERM</span>
            <span className="sm:hidden">T</span>
          </a>
        </div>
      </div>
    </div>
  );
}

function NavTab({
  label,
  mobileLabel,
  ariaLabel,
  active,
  onClick,
}: {
  label: string;
  mobileLabel?: string;
  ariaLabel: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={ariaLabel}
      aria-pressed={active}
      className={cn(
        "px-2 sm:px-2.5 py-1.5 sm:py-1 text-[0.72rem] sm:text-[0.7rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
        "flex items-center gap-1.5 sm:gap-1 min-h-[40px] sm:min-h-0",
        "focus:outline-none focus:ring-1 focus:ring-accent-blue",
        active
          ? "bg-accent-blue text-bg-primary border-b-2 border-accent-blue"
          : "text-txt-secondary hover:text-txt-primary hover:bg-bg-tertiary/50",
      )}
    >
      <span className="hidden sm:inline">{label}</span>
      <span className="sm:hidden">{mobileLabel ?? label}</span>
    </button>
  );
}
