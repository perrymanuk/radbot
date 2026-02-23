import { useEffect } from "react";
import { useTerminalStore } from "@/stores/terminal-store";
import { cn } from "@/lib/utils";
import CloneForm from "./CloneForm";

export default function WorkspaceSelector() {
  const workspaces = useTerminalStore((s) => s.workspaces);
  const sessions = useTerminalStore((s) => s.sessions);
  const loadWorkspaces = useTerminalStore((s) => s.loadWorkspaces);
  const loadSessions = useTerminalStore((s) => s.loadSessions);
  const openTerminal = useTerminalStore((s) => s.openTerminal);
  const showCloneForm = useTerminalStore((s) => s.showCloneForm);
  const setShowCloneForm = useTerminalStore((s) => s.setShowCloneForm);
  const error = useTerminalStore((s) => s.error);
  const clearError = useTerminalStore((s) => s.clearError);

  useEffect(() => {
    loadWorkspaces();
    loadSessions();
  }, [loadWorkspaces, loadSessions]);

  // Find active terminal sessions for a workspace
  const getActiveSession = (workspaceId: string) =>
    sessions.find((s) => s.workspace_id === workspaceId && !s.closed);

  return (
    <div className="flex flex-col gap-4 p-4 max-w-2xl mx-auto w-full">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-mono text-accent-blue uppercase tracking-wider">
          Workspaces
        </h2>
        <button
          onClick={() => setShowCloneForm(!showCloneForm)}
          className={cn(
            "px-3 py-1.5 border text-xs font-mono uppercase tracking-wider transition-all cursor-pointer",
            showCloneForm
              ? "bg-accent-blue text-bg-primary border-accent-blue"
              : "bg-bg-tertiary text-terminal-green border-terminal-green hover:bg-terminal-green hover:text-bg-primary",
          )}
        >
          {showCloneForm ? "Cancel" : "+ Clone Repo"}
        </button>
      </div>

      {error && (
        <div className="p-3 border border-terminal-red bg-terminal-red/10 text-terminal-red text-sm font-mono">
          {error}
          <button
            onClick={clearError}
            className="ml-2 text-xs underline hover:no-underline"
          >
            dismiss
          </button>
        </div>
      )}

      {showCloneForm && <CloneForm />}

      {workspaces.length === 0 ? (
        <div className="text-center py-12 text-txt-secondary font-mono">
          <p className="text-sm">No workspaces found.</p>
          <p className="text-xs mt-2">
            Clone a repository to get started.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {workspaces.map((ws) => {
            const activeSession = getActiveSession(String(ws.workspace_id));

            return (
              <div
                key={String(ws.workspace_id)}
                className="border border-border bg-bg-secondary p-3 flex items-center justify-between gap-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-sm text-txt-primary truncate">
                    <span className="text-terminal-amber">{ws.owner}</span>
                    <span className="text-txt-secondary">/</span>
                    <span className="text-accent-blue">{ws.repo}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-txt-secondary font-mono">
                    <span>branch: {ws.branch}</span>
                    {ws.last_session_id && (
                      <span className="truncate">
                        session: {ws.last_session_id.slice(0, 8)}...
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex gap-2 flex-shrink-0">
                  {activeSession ? (
                    <button
                      onClick={() =>
                        useTerminalStore.setState({
                          activeTerminalId: activeSession.terminal_id,
                        })
                      }
                      className="px-3 py-1.5 border border-terminal-amber text-terminal-amber text-xs font-mono uppercase tracking-wider hover:bg-terminal-amber hover:text-bg-primary transition-all cursor-pointer"
                    >
                      Reconnect
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => openTerminal(String(ws.workspace_id))}
                        className="px-3 py-1.5 border border-terminal-green text-terminal-green text-xs font-mono uppercase tracking-wider hover:bg-terminal-green hover:text-bg-primary transition-all cursor-pointer"
                      >
                        Open
                      </button>
                      {ws.last_session_id && (
                        <button
                          onClick={() =>
                            openTerminal(
                              String(ws.workspace_id),
                              ws.last_session_id!,
                            )
                          }
                          className="px-3 py-1.5 border border-accent-blue text-accent-blue text-xs font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer"
                        >
                          Resume
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
