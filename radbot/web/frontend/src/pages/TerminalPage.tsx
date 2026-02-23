import { useEffect, useState, useCallback } from "react";
import { useTerminalStore } from "@/stores/terminal-store";
import { cn } from "@/lib/utils";
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
  const status = useTerminalStore((s) => s.status);
  const loadStatus = useTerminalStore((s) => s.loadStatus);
  const killTerminal = useTerminalStore((s) => s.killTerminal);
  const [terminalClosed, setTerminalClosed] = useState(false);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

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
      <div className="flex items-center justify-between px-2 py-1 bg-bg-tertiary border-b border-border min-h-[44px] md:min-h-[40px] flex-shrink-0 z-10">
        {/* Left: title + status */}
        <div className="flex items-center gap-2 min-w-0">
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
          {activeSession && (
            <span className="text-xs text-txt-secondary font-mono hidden sm:inline">
              <span className="text-terminal-amber">{activeSession.owner}</span>
              <span>/</span>
              <span className="text-accent-blue">{activeSession.repo}</span>
              <span className="text-txt-secondary ml-1">({activeSession.branch})</span>
            </span>
          )}
        </div>

        {/* Right: action buttons */}
        <div className="flex gap-1.5 flex-shrink-0">
          {activeTerminalId && (
            <>
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
