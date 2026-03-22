import { useEffect, useState, useCallback, useRef } from "react";
import { useTerminalStore } from "@/stores/terminal-store";
import { cn } from "@/lib/utils";
import { useSTT } from "@/hooks/use-stt";
import TerminalEmulator from "@/components/terminal/TerminalEmulator";
import WorkspaceSelector from "@/components/terminal/WorkspaceSelector";

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
  const [terminalClosed, setTerminalClosed] = useState(false);

  // STT: ref to sendInput from TerminalEmulator
  const sendInputRef = useRef<((data: string) => void) | null>(null);

  const handleSendInputRef = useCallback((fn: (data: string) => void) => {
    sendInputRef.current = fn;
  }, []);

  const handleTranscript = useCallback((text: string) => {
    sendInputRef.current?.(text);
  }, []);

  const { state: sttState, toggle: sttToggle } = useSTT(handleTranscript);

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
  }, [setActiveTerminalId]);

  const handleKill = useCallback(async () => {
    if (activeTerminalId) {
      await killTerminal(activeTerminalId);
      setTerminalClosed(false);
    }
  }, [activeTerminalId, killTerminal]);

  const activeSession = sessions.find(
    (s) => s.terminal_id === activeTerminalId,
  );

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
        </div>

        {/* Center: workspace tabs — horizontally scrollable */}
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
          </div>
        )}

        {/* Right: action buttons */}
        <div className="flex gap-1.5 flex-shrink-0">
          {activeTerminalId && (
            <>
              <button
                onClick={sttToggle}
                disabled={sttState === "processing"}
                className={cn(
                  "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                  "flex items-center min-h-[40px] sm:min-h-0",
                  sttState === "recording"
                    ? "bg-bg-tertiary text-terminal-red border-terminal-red animate-pulse"
                    : sttState === "processing"
                      ? "bg-bg-tertiary text-terminal-amber border-terminal-amber opacity-70 cursor-not-allowed"
                      : "bg-bg-tertiary text-txt-primary border-border hover:bg-accent-blue hover:text-bg-primary",
                )}
              >
                {sttState === "recording" ? "Rec" : sttState === "processing" ? "..." : "Mic"}
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
              <button
                onClick={handleKill}
                className={cn(
                  "px-2 py-1.5 sm:py-0.5 border text-[0.72rem] sm:text-[0.75rem] font-mono uppercase tracking-wider transition-all cursor-pointer",
                  "flex items-center min-h-[40px] sm:min-h-0",
                  "bg-bg-tertiary text-terminal-red border-terminal-red hover:bg-terminal-red hover:text-bg-primary",
                )}
              >
                Kill
              </button>
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
            <div className="flex-1 bg-[#1a1a2e]">
              <TerminalEmulator
                terminalId={activeTerminalId}
                onClosed={handleClosed}
                onSendInputRef={handleSendInputRef}
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
