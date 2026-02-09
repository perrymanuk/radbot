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
    />
  );
}

export default function ChatHeader() {
  const status = useAppStore((s) => s.connectionStatus);
  const agentInfo = useAppStore((s) => s.agentInfo);
  const togglePanel = useAppStore((s) => s.togglePanel);
  const activePanel = useAppStore((s) => s.activePanel);
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
    <div className="flex items-center justify-between px-2 py-1 bg-bg-tertiary border-b border-border h-10 flex-shrink-0 z-10">
      {/* Left: title + status */}
      <div className="flex items-center gap-2">
        <h1 className="text-[0.85rem] tracking-wider font-normal text-accent-blue uppercase font-mono m-0 whitespace-nowrap">
          RadBot Terminal
        </h1>
        <StatusDot status={status} />
        <span className="text-[0.75rem] text-txt-secondary">
          <span className="text-terminal-amber font-bold">{agentName}</span>
          {modelName && (
            <span className="text-txt-primary ml-2">{modelName}</span>
          )}
        </span>
      </div>

      {/* Right: TTS toggle + panel toggle buttons */}
      <div className="flex gap-1.5">
        <PanelButton
          label={ttsAutoPlay ? "TTS:ON" : "TTS:OFF"}
          active={ttsAutoPlay}
          onClick={toggleTtsAutoPlay}
        />
        <PanelButton
          label="SESS"
          active={activePanel === "sessions"}
          onClick={() => togglePanel("sessions")}
        />
        <PanelButton
          label="TASKS"
          active={activePanel === "tasks"}
          onClick={() => togglePanel("tasks")}
        />
        <PanelButton
          label="EVENTS"
          active={activePanel === "events"}
          onClick={() => togglePanel("events")}
        />
      </div>
    </div>
  );
}

function PanelButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2 py-0.5 border text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
        "flex items-center gap-1",
        active
          ? "bg-accent-blue text-bg-primary border-accent-blue"
          : "bg-bg-tertiary text-txt-primary border-border hover:bg-accent-blue hover:text-bg-primary",
      )}
    >
      {label}
    </button>
  );
}
