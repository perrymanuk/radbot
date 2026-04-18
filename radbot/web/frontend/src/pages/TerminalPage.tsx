import { useEffect, useState, useCallback, useRef } from "react";
import { useTerminalStore } from "@/stores/terminal-store";
import { cn } from "@/lib/utils";
import { useSTT } from "@/hooks/use-stt";
import TerminalEmulator from "@/components/terminal/TerminalEmulator";
import WorkspaceSelector from "@/components/terminal/WorkspaceSelector";
import type { ConnectionState } from "@/hooks/use-terminal-ws";

function StatusIndicator({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full",
        ok
          ? "bg-terminal-green shadow-[0_0_5px_rgba(51,255,51,0.4)]"
          : "bg-terminal-red",
      )}
    />
  );
}

function RecordingTimer({ startTime }: { startTime: number }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime]);
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return (
    <span className="text-terminal-red font-mono text-[0.65rem] tabular-nums">
      {mins}:{secs.toString().padStart(2, "0")}
    </span>
  );
}

function SessionUptime({ createdAt }: { createdAt: number }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(interval);
  }, []);
  const diff = Math.floor((Date.now() - createdAt) / 1000);
  if (diff < 60) return <span>{diff}s</span>;
  const mins = Math.floor(diff / 60);
  if (mins < 60) return <span>{mins}m</span>;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return <span>{hours}h {remMins}m</span>;
}

export default function TerminalPage() {
  const activeTerminalId = useTerminalStore((s) => s.activeTerminalId);
  const setActiveTerminalId = useTerminalStore((s) => s.setActiveTerminalId);
  const sessions = useTerminalStore((s) => s.sessions);
  const workspaces = useTerminalStore((s) => s.workspaces);
  const openTerminal = useTerminalStore((s) => s.openTerminal);
  const loadWorkspaces = useTerminalStore((s) => s.loadWorkspaces);
  const status = useTerminalStore((s) => s.status);
  const loadStatus = useTerminalStore((s) => s.loadStatus);
  const killTerminal = useTerminalStore((s) => s.killTerminal);
  const createScratchWorkspace = useTerminalStore((s) => s.createScratchWorkspace);
  const [terminalClosed, setTerminalClosed] = useState(false);
  const [showKillConfirm, setShowKillConfirm] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [sessionCreatedAt] = useState<number>(Date.now());
  const killConfirmTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // STT: ref to sendInput from TerminalEmulator
  const sendInputRef = useRef<((data: string) => void) | null>(null);

  const handleSendInputRef = useCallback((fn: (data: string) => void) => {
    sendInputRef.current = fn;
  }, []);

  const handleTranscript = useCallback((text: string) => {
    sendInputRef.current?.(text);
  }, []);

  const { state: sttState, toggle: sttToggle, recordingStartTime } = useSTT(handleTranscript);

  useEffect(() => {
    loadStatus();
    loadWorkspaces();
  }, [loadStatus, loadWorkspaces]);

  const handleClosed = useCallback((exitCode: number) => {
    setTerminalClosed(true);
    console.log("[Terminal] Process exited with code:", exitCode);
  }, []);

  const handleBack = useCallback(() => {
    setActiveTerminalId(null);
    setTerminalClosed(false);
    setShowKillConfirm(false);
  }, [setActiveTerminalId]);

  const handleKillRequest = useCallback(() => {
    setShowKillConfirm(true);
    // Auto-dismiss after 5 seconds
    clearTimeout(killConfirmTimerRef.current);
    killConfirmTimerRef.current = setTimeout(() => {
      setShowKillConfirm(false);
    }, 5000);
  }, []);

  const handleKillConfirm = useCallback(async () => {
    clearTimeout(killConfirmTimerRef.current);
    setShowKillConfirm(false);
    if (activeTerminalId) {
      await killTerminal(activeTerminalId);
      setTerminalClosed(false);
    }
  }, [activeTerminalId, killTerminal]);

  const handleKillCancel = useCallback(() => {
    clearTimeout(killConfirmTimerRef.current);
    setShowKillConfirm(false);
  }, []);

  const handleConnectionStateChange = useCallback((state: ConnectionState) => {
    setConnectionState(state);
  }, []);

  // Clean up timer on unmount
  useEffect(() => {
    return () => clearTimeout(killConfirmTimerRef.current);
  }, []);

  const activeSession = sessions.find(
    (s) => s.terminal_id === activeTerminalId,
  );

  // Keyboard shortcuts (page-level)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept if terminal has focus (let TerminalEmulator handle its own shortcuts)
      const target = e.target as HTMLElement;
      const isTerminalFocused = target.closest(".xterm");

      // Ctrl+Shift+T: new scratch workspace + open terminal
      if (e.ctrlKey && e.shiftKey && e.key === "T" && !isTerminalFocused) {
        e.preventDefault();
        createScratchWorkspace().then(() => {
          const ws = useTerminalStore.getState().workspaces[0];
          if (ws) openTerminal(String(ws.workspace_id));
        });
        return;
      }
      // Ctrl+Shift+W: kill active terminal (with confirmation)
      if (e.ctrlKey && e.shiftKey && e.key === "W") {
        e.preventDefault();
        if (activeTerminalId && !showKillConfirm) {
          handleKillRequest();
        }
        return;
      }
      // Ctrl+Shift+[ / ]: switch workspace tabs
      if (e.ctrlKey && e.shiftKey && (e.key === "[" || e.key === "{")) {
        e.preventDefault();
        switchWorkspaceTab(-1);
        return;
      }
      if (e.ctrlKey && e.shiftKey && (e.key === "]" || e.key === "}")) {
        e.preventDefault();
        switchWorkspaceTab(1);
        return;
      }
    };

    const switchWorkspaceTab = (direction: number) => {
      const sorted = [...workspaces].sort(
        (a, b) => new Date(b.last_used_at).getTime() - new Date(a.last_used_at).getTime()
      );
      if (sorted.length === 0) return;
      const currentIdx = activeSession
        ? sorted.findIndex((ws) => String(ws.workspace_id) === activeSession.workspace_id)
        : -1;
      const nextIdx = (currentIdx + direction + sorted.length) % sorted.length;
      const nextWs = sorted[nextIdx];
      const running = sessions.find(
        (s) => s.workspace_id === String(nextWs.workspace_id) && !s.closed,
      );
      if (running) {
        setActiveTerminalId(running.terminal_id);
      } else {
        openTerminal(String(nextWs.workspace_id), nextWs.last_session_id ?? undefined);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeTerminalId, activeSession, workspaces, sessions, showKillConfirm, handleKillRequest, createScratchWorkspace, openTerminal, setActiveTerminalId]);

  return (
    <div className="flex flex-col h-full bg-bg-primary">
      {/* Header bar */}
      <div className="flex items-center px-2 py-1 bg-bg-tertiary border-b border-border min-h-[44px] md:min-h-[40px] flex-shrink-0 z-10 gap-2">
        {/* Left: title + status */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <a
            href="/"
            className="text-sm sm:text-[0.85rem] tracking-wider font-normal text-accent-blue uppercase font-mono whitespace-nowrap hover:text-terminal-green transition-colors no-underline"
          >
            RadBot
          </a>
          <span className="text-txt-secondary font-mono text-xs">/</span>
          <h1 className="text-sm sm:text-[0.85rem] tracking-wider font-normal text-terminal-amber uppercase font-mono m-0 whitespace-nowrap">
            Terminal
          </h1>
          {status && <StatusIndicator ok={status.status === "ok"} />}
          {/* Connection state indicator */}
          {activeTerminalId && connectionState !== "connected" && connectionState !== "disconnected" && (
            <span className="text-[0.65rem] font-mono text-terminal-amber">
              {connectionState === "connecting" ? "connecting..." : "reconnecting..."}
            </span>
          )}
        </div>

        {/* Center: workspace tabs -- horizontally scrollable */}
        {workspaces.length > 0 && (
          <div
            className="flex-1 min-w-0 overflow-x-auto flex items-center gap-1 scrollbar-hide"
            style={{ scrollSnapType: "x mandatory", WebkitOverflowScrolling: "touch" }}
          >
            {[...workspaces]
              .sort((a, b) => new Date(b.last_used_at).getTime() - new Date(a.last_used_at).getTime())
              .map((ws) => {
                const wsId = String(ws.workspace_id);
                const isScratch = ws.owner === "_scratch";
                const label = ws.name || (isScratch ? "Scratch" : ws.repo);
                const isActive = activeSession?.workspace_id === wsId;
                const hasRunning = sessions.some(
                  (s) => s.workspace_id === wsId && !s.closed,
                );

                const handleTabClick = () => {
                  // If this workspace has a running session, switch to it
                  const running = sessions.find(
                    (s) => s.workspace_id === wsId && !s.closed,
                  );
                  if (running) {
                    setActiveTerminalId(running.terminal_id);
                    setTerminalClosed(false);
                  } else {
                    // Open a new session (or resume if last_session_id exists)
                    openTerminal(wsId, ws.last_session_id ?? undefined);
                    setTerminalClosed(false);
                  }
                };

                return (
                  <button
                    key={wsId}
                    onClick={handleTabClick}
                    style={{ scrollSnapAlign: "start" }}
                    className={cn(
                      "flex items-center gap-1 px-2 py-0.5 border text-[0.7rem] font-mono whitespace-nowrap transition-all cursor-pointer flex-shrink-0",
                      isActive
                        ? "border-accent-blue bg-accent-blue/20 text-accent-blue"
                        : "border-border bg-bg-secondary text-txt-secondary hover:border-accent-blue hover:text-txt-primary",
                    )}
                  >
                    {hasRunning && (
                      <span className="w-1.5 h-1.5 rounded-full bg-terminal-green shadow-[0_0_4px_rgba(51,255,51,0.4)]" />
                    )}
                    {label}
                  </button>
                );
              })}

            {/* Session uptime */}
            {activeTerminalId && (
              <span className="text-[0.65rem] font-mono text-txt-secondary flex-shrink-0 ml-1">
                <SessionUptime createdAt={sessionCreatedAt} />
              </span>
            )}
          </div>
        )}

        {/* Right: action buttons */}
        <div className="flex gap-1.5 flex-shrink-0">
          {activeTerminalId && (
            <>
              {/* MIC button */}
              <button
                onClick={sttToggle}
                disabled={sttState === "processing"}
                className={cn(
                  "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                  "flex items-center gap-1 min-h-[40px] sm:min-h-0",
                  sttState === "recording"
                    ? "bg-bg-tertiary text-terminal-red border-terminal-red"
                    : sttState === "processing"
                      ? "bg-bg-tertiary text-terminal-amber border-terminal-amber opacity-70 cursor-not-allowed"
                      : "bg-bg-tertiary text-txt-primary border-border hover:bg-accent-blue hover:text-bg-primary",
                )}
              >
                {sttState === "recording" ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-terminal-red animate-pulse" />
                    {recordingStartTime && <RecordingTimer startTime={recordingStartTime} />}
                  </>
                ) : sttState === "processing" ? "..." : "Mic"}
              </button>
              <button
                onClick={handleBack}
                className={cn(
                  "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                  "flex items-center min-h-[40px] sm:min-h-0",
                  "bg-bg-tertiary text-txt-primary border-border hover:bg-accent-blue hover:text-bg-primary",
                )}
              >
                Back
              </button>

              {/* Kill button with confirmation */}
              {showKillConfirm ? (
                <>
                  <span className="text-terminal-amber text-[0.7rem] font-mono flex items-center">Kill?</span>
                  <button
                    onClick={handleKillConfirm}
                    className={cn(
                      "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                      "flex items-center min-h-[40px] sm:min-h-0",
                      "bg-terminal-red text-bg-primary border-terminal-red hover:bg-terminal-red/80",
                    )}
                  >
                    Yes
                  </button>
                  <button
                    onClick={handleKillCancel}
                    className={cn(
                      "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                      "flex items-center min-h-[40px] sm:min-h-0",
                      "bg-bg-tertiary text-txt-secondary border-border hover:text-txt-primary",
                    )}
                  >
                    No
                  </button>
                </>
              ) : (
                <button
                  onClick={handleKillRequest}
                  className={cn(
                    "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                    "flex items-center min-h-[40px] sm:min-h-0",
                    "bg-bg-tertiary text-terminal-red border-terminal-red hover:bg-terminal-red hover:text-bg-primary",
                  )}
                >
                  Kill
                </button>
              )}
            </>
          )}
          <a
            href="/"
            className={cn(
              "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer no-underline",
              "flex items-center min-h-[40px] sm:min-h-0",
              "bg-bg-tertiary text-terminal-green border-terminal-green hover:bg-terminal-green hover:text-bg-primary",
            )}
          >
            Chat
          </a>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTerminalId ? (
          <div className="h-full flex flex-col">
            {terminalClosed && (
              <div className="px-3 py-2 bg-terminal-red/10 border-b border-terminal-red text-terminal-red text-xs font-mono flex items-center justify-between">
                <span>Terminal session has ended.</span>
                <button
                  onClick={handleBack}
                  className="underline hover:no-underline"
                >
                  Back to workspaces
                </button>
              </div>
            )}
            <div className="flex-1 bg-bg-primary">
              <TerminalEmulator
                terminalId={activeTerminalId}
                onClosed={handleClosed}
                onSendInputRef={handleSendInputRef}
                onConnectionStateChange={handleConnectionStateChange}
              />
            </div>
          </div>
        ) : (
          <div className="h-full overflow-y-auto">
            {status && status.status !== "ok" && (
              <div className="mx-4 mt-4 p-3 border border-terminal-amber bg-terminal-amber/10 text-terminal-amber text-sm font-mono">
                {status.message}
              </div>
            )}
            <WorkspaceSelector />
          </div>
        )}
      </div>
    </div>
  );
}
