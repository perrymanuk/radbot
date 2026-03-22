import { useEffect, useState } from "react";
import { useTerminalStore } from "@/stores/terminal-store";
import { cn } from "@/lib/utils";
import CloneForm from "./CloneForm";
import type { Workspace } from "@/types/terminal";

function WorkspaceItem({ ws }: { ws: Workspace }) {
  const sessions = useTerminalStore((s) => s.sessions);
  const openTerminal = useTerminalStore((s) => s.openTerminal);
  const deleteWorkspace = useTerminalStore((s) => s.deleteWorkspace);
  const [confirming, setConfirming] = useState(false);

  const activeSession = sessions.find(
    (s) => s.workspace_id === String(ws.workspace_id) && !s.closed,
  );

  const isScratch = ws.owner === "_scratch";
  const displayName = ws.name || (isScratch ? "Scratch" : `${ws.owner}/${ws.repo}`);

  if (confirming) {
    return (
      <div className="border border-terminal-red/50 bg-terminal-red/10 p-3">
        <div className="text-terminal-red font-mono text-sm mb-2">
          Delete workspace "{displayName}"?
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              deleteWorkspace(String(ws.workspace_id));
              setConfirming(false);
            }}
            className="px-3 py-1 border border-terminal-red text-terminal-red text-xs font-mono uppercase hover:bg-terminal-red hover:text-bg-primary transition-all"
          >
            Yes, Delete
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="px-3 py-1 border border-border text-txt-secondary text-xs font-mono uppercase hover:text-txt-primary transition-all"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group border border-border bg-bg-secondary p-3 flex items-center justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="font-mono text-sm text-txt-primary truncate flex items-center gap-2">
          {isScratch ? (
            <span className="text-terminal-green">{displayName}</span>
          ) : (
            <>
              <span className="text-terminal-amber">{ws.owner}</span>
              <span className="text-txt-secondary">/</span>
              <span className="text-accent-blue">{ws.repo}</span>
            </>
          )}
          {ws.name && !isScratch && (
            <span className="text-txt-secondary text-xs">({ws.name})</span>
          )}
        </div>
        {ws.description && (
          <div className="text-xs text-txt-secondary font-mono mt-0.5 truncate italic">
            {ws.description}
          </div>
        )}
        <div className="flex items-center gap-3 mt-1 text-xs text-txt-secondary font-mono">
          {!isScratch && <span>branch: {ws.branch}</span>}
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
                  openTerminal(String(ws.workspace_id), ws.last_session_id!)
                }
                className="px-3 py-1.5 border border-accent-blue text-accent-blue text-xs font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer"
              >
                Resume
              </button>
            )}
          </>
        )}
        <button
          onClick={() => setConfirming(true)}
          className="px-2 py-1.5 border border-border text-txt-secondary text-xs font-mono hover:text-terminal-red hover:border-terminal-red transition-all cursor-pointer opacity-0 group-hover:opacity-100"
          aria-label="Delete workspace"
        >
          ×
        </button>
      </div>
    </div>
  );
}

export default function WorkspaceSelector() {
  const workspaces = useTerminalStore((s) => s.workspaces);
  const loadWorkspaces = useTerminalStore((s) => s.loadWorkspaces);
  const loadSessions = useTerminalStore((s) => s.loadSessions);
  const createScratchWorkspace = useTerminalStore((s) => s.createScratchWorkspace);
  const showCloneForm = useTerminalStore((s) => s.showCloneForm);
  const setShowCloneForm = useTerminalStore((s) => s.setShowCloneForm);
  const error = useTerminalStore((s) => s.error);
  const clearError = useTerminalStore((s) => s.clearError);

  const [showScratchForm, setShowScratchForm] = useState(false);
  const [scratchName, setScratchName] = useState("");
  const [scratchDesc, setScratchDesc] = useState("");

  useEffect(() => {
    loadWorkspaces();
    loadSessions();
  }, [loadWorkspaces, loadSessions]);

  const handleCreateScratch = async () => {
    await createScratchWorkspace(
      scratchName.trim() || undefined,
      scratchDesc.trim() || undefined,
    );
    setShowScratchForm(false);
    setScratchName("");
    setScratchDesc("");
  };

  return (
    <div className="flex flex-col gap-4 p-4 max-w-2xl mx-auto w-full">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="text-lg font-mono text-accent-blue uppercase tracking-wider">
          Workspaces
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => {
              setShowScratchForm(!showScratchForm);
              if (showCloneForm) setShowCloneForm(false);
            }}
            className={cn(
              "px-3 py-1.5 border text-xs font-mono uppercase tracking-wider transition-all cursor-pointer",
              showScratchForm
                ? "bg-accent-blue text-bg-primary border-accent-blue"
                : "bg-bg-tertiary text-accent-blue border-accent-blue hover:bg-accent-blue hover:text-bg-primary",
            )}
          >
            {showScratchForm ? "Cancel" : "+ New Session"}
          </button>
          <button
            onClick={() => {
              setShowCloneForm(!showCloneForm);
              if (showScratchForm) setShowScratchForm(false);
            }}
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

      {showScratchForm && (
        <div className="border border-accent-blue bg-bg-tertiary p-3">
          <div className="text-xs font-mono text-accent-blue uppercase tracking-wider mb-2">
            New Scratch Session
          </div>
          <input
            type="text"
            value={scratchName}
            onChange={(e) => setScratchName(e.target.value)}
            placeholder="Session name (optional)..."
            autoFocus
            className="w-full bg-bg-secondary text-txt-primary border border-border px-2 py-1 font-mono text-sm outline-none focus:border-accent-blue mb-2"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreateScratch();
              if (e.key === "Escape") setShowScratchForm(false);
            }}
          />
          <textarea
            value={scratchDesc}
            onChange={(e) => setScratchDesc(e.target.value)}
            placeholder="Description (optional)..."
            rows={2}
            className="w-full bg-bg-secondary text-txt-primary border border-border px-2 py-1 font-mono text-xs outline-none focus:border-accent-blue resize-none mb-2"
          />
          <button
            onClick={handleCreateScratch}
            className="px-3 py-1.5 border border-accent-blue text-accent-blue text-xs font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer"
          >
            Create
          </button>
        </div>
      )}

      {showCloneForm && <CloneForm />}

      {workspaces.length === 0 ? (
        <div className="text-center py-12 text-txt-secondary font-mono">
          <p className="text-sm">No workspaces found.</p>
          <p className="text-xs mt-2">
            Clone a repository or create a scratch session to get started.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {workspaces.map((ws) => (
            <WorkspaceItem key={String(ws.workspace_id)} ws={ws} />
          ))}
        </div>
      )}
    </div>
  );
}
