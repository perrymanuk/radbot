import { useState, useRef, useEffect } from "react";
import { useAppStore } from "@/stores/app-store";
import { useNotificationStore } from "@/stores/notification-store";
import { cn } from "@/lib/utils";
import type { ConnectionStatus } from "@/types";
import NotificationsPopover from "@/components/notifications/NotificationsPopover";
import NotificationDetail from "@/components/notifications/NotificationDetail";
import type { Notification } from "@/types";

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

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  active: "WS CONNECTED",
  thinking: "WS THINKING",
  connecting: "WS CONNECTING",
  reconnecting: "WS RECONNECTING",
  disconnected: "WS DISCONNECTED",
  error: "WS ERROR",
};

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="hidden md:inline font-mono text-[0.55rem] tracking-[0.2em] text-txt-secondary/60 uppercase mr-1.5 select-none">
      {children}
    </span>
  );
}

export default function ChatHeader() {
  const status = useAppStore((s) => s.connectionStatus);
  const agentInfo = useAppStore((s) => s.agentInfo);
  const togglePanel = useAppStore((s) => s.togglePanel);
  const setActivePanel = useAppStore((s) => s.setActivePanel);
  const activePanel = useAppStore((s) => s.activePanel);
  const unreadNotifCount = useAppStore((s) => s.unreadNotificationCount);
  const splitMode = useAppStore((s) => s.splitMode);
  const toggleSplitMode = useAppStore((s) => s.toggleSplitMode);

  const [ttsAutoPlay, setTtsAutoPlay] = useState(
    () => localStorage.getItem("radbot_tts_autoplay") === "true",
  );
  const [notifOpen, setNotifOpen] = useState(false);
  const [selectedNotif, setSelectedNotif] = useState<Notification | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const bellRef = useRef<HTMLButtonElement>(null);

  const loadNotifications = useNotificationStore((s) => s.loadNotifications);

  useEffect(() => {
    if (notifOpen) loadNotifications();
  }, [notifOpen, loadNotifications]);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const toggleTtsAutoPlay = () => {
    const next = !ttsAutoPlay;
    setTtsAutoPlay(next);
    localStorage.setItem("radbot_tts_autoplay", String(next));
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  };

  const modelName = agentInfo?.model ?? "";

  return (
    <>
      <div className="scanlines flex items-center justify-start sm:justify-between gap-3 pl-3 pr-4 sm:px-3 py-1.5 bg-bg-secondary border-b border-border min-h-[44px] md:min-h-[40px] flex-shrink-0 z-10 relative">
        {/* Left: mascot + wordmark + model + status */}
        <div className="flex items-center gap-3 min-w-0">
          <div
            aria-hidden
            className="mascot-sticker block w-[32px] h-[32px] sm:w-[38px] sm:h-[38px] flex-none rounded-md border-2 border-[#ff9966] bg-cover"
            style={{
              backgroundImage: "url(/static/dist/radbot.png)",
              backgroundSize: "260%",
              backgroundPosition: "60% 30%",
            }}
          />
          <div className="hidden sm:flex items-baseline gap-2">
            <h1 className="pixel-font text-[22px] text-txt-primary m-0 leading-none">
              RADBOT
            </h1>
            <span className="inline-flex text-[9px] font-mono font-semibold tracking-[0.15em] text-[#ff9966] px-1.5 py-0.5 rounded-sm border border-[#ff9966]/40 bg-[#ff9966]/10">
              BETO·v0.9
            </span>
          </div>

          {modelName && (
            <>
              <div className="w-px h-5 bg-border hidden md:block mx-1" />
              <div className="hidden md:flex items-center gap-1.5">
                <span className="font-mono text-[0.55rem] tracking-[0.2em] text-txt-secondary/60 uppercase">
                  Model
                </span>
                <span className="font-mono text-[0.7rem] text-txt-primary tracking-[0.05em] px-1.5 py-0.5 rounded-sm border border-border bg-bg-primary/50 truncate max-w-[220px]">
                  {modelName}
                </span>
              </div>
            </>
          )}

          <div className="w-px h-5 bg-border hidden sm:block mx-1" />

          <div className="flex items-center gap-1.5">
            <StatusDot status={status} />
            <span className="font-mono text-[0.6rem] tracking-[0.14em] text-txt-secondary hidden sm:inline">
              {STATUS_LABEL[status]}
            </span>
          </div>
        </div>

        {/* Right: VOICE cluster + PANELS cluster */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0 sm:flex-shrink-0">
          {/* VOICE group — hidden on mobile (too cramped) */}
          <div className="hidden sm:flex items-center">
            <GroupLabel>Voice</GroupLabel>
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
              <span className="hidden sm:inline">{ttsAutoPlay ? "TTS ON" : "TTS OFF"}</span>
              <span className="sm:hidden">TTS</span>
            </button>
          </div>

          <div className="w-px h-5 bg-border hidden sm:block" />

          {/* PANELS group */}
          <div className="flex items-center min-w-0">
            <GroupLabel>Panels</GroupLabel>
            <div className="flex gap-0.5 bg-bg-primary/50 p-0.5 rounded-sm items-center min-w-0 overflow-x-auto sm:overflow-visible [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              <NavTab
                label="CHAT"
                ariaLabel="Focus chat (close side panels)"
                active={activePanel === null && !splitMode}
                onClick={() => setActivePanel(null)}
              />
              <NavTab
                label="SESS"
                ariaLabel="Sessions panel"
                active={activePanel === "sessions"}
                onClick={() => togglePanel("sessions")}
              />
              <NavTab
                label="EVENTS"
                mobileLabel="EVT"
                ariaLabel="Events panel"
                active={activePanel === "events"}
                onClick={() => togglePanel("events")}
              />
              <div className="hidden sm:contents">
                <NavTab
                  label="SPLIT"
                  ariaLabel="Toggle split view"
                  active={splitMode}
                  onClick={toggleSplitMode}
                />
              </div>

              <button
                ref={bellRef}
                onClick={() => setNotifOpen((v) => !v)}
                aria-label="Notifications"
                aria-expanded={notifOpen}
                className={cn(
                  "relative flex-none px-1.5 sm:px-2.5 py-1 sm:py-1 text-[0.68rem] sm:text-[0.7rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                  "flex items-center gap-1 min-h-[32px] sm:min-h-0",
                  "focus:outline-none focus:ring-1 focus:ring-accent-blue",
                  notifOpen
                    ? "bg-accent-blue/15 text-accent-blue"
                    : "text-accent-blue hover:bg-accent-blue/15",
                )}
              >
                <span className="hidden sm:inline">NOTIF</span>
                <span className="sm:hidden">N</span>
                {unreadNotifCount > 0 && (
                  <span className="absolute top-0.5 right-0.5 sm:-top-0.5 sm:-right-0.5 bg-terminal-red text-bg-primary text-[0.45rem] sm:text-[0.5rem] font-bold rounded-full min-w-[11px] sm:min-w-[14px] h-[11px] sm:h-[14px] flex items-center justify-center px-0.5 leading-none">
                    {unreadNotifCount > 99 ? "99+" : unreadNotifCount}
                  </span>
                )}
              </button>

              <a
                href="/terminal"
                aria-label="Open terminal"
                className={cn(
                  "hidden sm:flex px-2 sm:px-2.5 py-1.5 sm:py-1 text-[0.72rem] sm:text-[0.7rem] font-mono uppercase tracking-wider transition-all cursor-pointer no-underline",
                  "items-center gap-1.5 sm:gap-1 min-h-[40px] sm:min-h-0",
                  "text-terminal-amber hover:bg-terminal-amber/15 hover:text-terminal-amber",
                  "focus:outline-none focus:ring-1 focus:ring-terminal-amber",
                )}
              >
                TERM
              </a>
            </div>
          </div>

          <button
            onClick={toggleFullscreen}
            aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
            className={cn(
              "hidden sm:grid w-7 h-7 flex-none place-items-center border border-border rounded-sm cursor-pointer transition-all",
              "text-txt-secondary hover:text-txt-primary hover:bg-bg-primary/50",
              "focus:outline-none focus:ring-1 focus:ring-accent-blue",
            )}
            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            <span className="font-mono text-[0.8rem] leading-none">{isFullscreen ? "⤦" : "⤢"}</span>
          </button>
        </div>
      </div>

      {notifOpen && (
        <NotificationsPopover
          buttonRef={bellRef}
          onClose={() => setNotifOpen(false)}
          onSelect={(n) => {
            setSelectedNotif(n);
            setNotifOpen(false);
          }}
        />
      )}
      {selectedNotif && (
        <NotificationDetail
          notification={selectedNotif}
          onClose={() => setSelectedNotif(null)}
        />
      )}
    </>
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
        "flex-none px-1.5 sm:px-2.5 py-1 sm:py-1 text-[0.68rem] sm:text-[0.7rem] font-mono uppercase tracking-wider transition-all cursor-pointer rounded-sm",
        "flex items-center gap-1 min-h-[32px] sm:min-h-0 border",
        "focus:outline-none focus:ring-1 focus:ring-accent-blue",
        active
          ? "bg-bg-primary/60 text-txt-primary border-radbot-sunset/60"
          : "text-txt-secondary border-transparent hover:text-txt-primary hover:bg-bg-tertiary/50",
      )}
    >
      <span className="hidden sm:inline">{label}</span>
      <span className="sm:hidden">{mobileLabel ?? label}</span>
    </button>
  );
}
