import { useEffect, useState, useMemo } from "react";
import { useTerminalStore } from "@/stores/terminal-store";
import { cn } from "@/lib/utils";
import CloneForm from "./CloneForm";
import type { Workspace } from "@/types/terminal";

// Inline SVG icons
function GitBranchIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 3v12M18 9a3 3 0 100-6 3 3 0 000 6zM6 21a3 3 0 100-6 3 3 0 000 6zM18 9a9 9 0 01-9 9" />
    </svg>
  );
}

function TerminalIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

function SearchIcon({ className = "w-3.5 h-3.5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const date = new Date(dateStr).getTime();
  const diff = now - date;
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function WorkerStatusBadge({ status }: { status: Workspace["worker_status"] }) {
  if (!status || status === "stopped") return null;
  const config = {
    running: { color: "bg-terminal-green", text: "Running", textColor: "text-terminal-green" },
    starting: { color: "bg-terminal-amber", text: "Starting", textColor: "text-terminal-amber" },
    unhealthy: { color: "bg-terminal-red", text: "Unhealthy", textColor: "text-terminal-red" },
  } as const;
  const c = config[status as keyof typeof config];
  if (!c) return null;
  return (
    <span className={cn("flex items-center gap-1 text-xs font-mono", c.textColor)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", c.color)} />
      {c.text}
    </span>
  );
}

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
          Delete workspace &ldquo;{displayName}&rdquo;?
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
    <div className={cn(
      "group border bg-bg-secondary p-3 flex items-center justify-between gap-3 transition-colors hover:bg-bg-tertiary",
      isScratch ? "border-l-[3px] border-l-terminal-green border-t-border border-r-border border-b-border" : "border-l-[3px] border-l-accent-blue border-t-border border-r-border border-b-border",
    )}>
      <div className="min-w-0 flex-1">
        <div className="font-mono text-sm text-txt-primary truncate flex items-center gap-2">
          {isScratch ? (
            <>
              <TerminalIcon className="w-3.5 h-3.5 text-terminal-green flex-shrink-0" />
              <span className="text-terminal-green">{displayName}</span>
            </>
          ) : (
            <>
              <GitBranchIcon className="w-3.5 h-3.5 text-accent-blue flex-shrink-0" />
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
          <div className="text-xs text-txt-secondary font-mono mt-0.5 truncate italic ml-5.5">
            {ws.description}
          </div>
        )}
        <div className="flex items-center gap-3 mt-1 text-xs text-txt-secondary font-mono ml-5.5">
          {!isScratch && (
            <span className="flex items-center gap-1">
              <GitBranchIcon className="w-3 h-3" />
              {ws.branch}
            </span>
          )}
          {ws.last_used_at && (
            <span>{relativeTime(ws.last_used_at)}</span>
          )}
          {ws.last_session_id && (
            <span className="truncate">
              session: {ws.last_session_id.slice(0, 8)}...
            </span>
          )}
          <WorkerStatusBadge status={ws.worker_status} />
        </div>
      </div>

      <div className="flex gap-2 flex-shrink-0 items-center">
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
          className="px-2 py-1.5 border border-border text-txt-secondary text-xs font-mono hover:text-terminal-red hover:border-terminal-red transition-all cursor-pointer opacity-30 group-hover:opacity-100"
          aria-label="Delete workspace"
        >
          &times;
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
  const startHealthPolling = useTerminalStore((s) => s.startHealthPolling);
  const stopHealthPolling = useTerminalStore((s) => s.stopHealthPolling);

  const [showScratchForm, setShowScratchForm] = useState(false);
  const [scratchName, setScratchName] = useState("");
  const [scratchDesc, setScratchDesc] = useState("");
  const [searchFilter, setSearchFilter] = useState("");

  useEffect(() => {
    loadWorkspaces();
    loadSessions();
    startHealthPolling();
    return () => stopHealthPolling();
  }, [loadWorkspaces, loadSessions, startHealthPolling, stopHealthPolling]);

  const filteredWorkspaces = useMemo(() => {
    if (!searchFilter) return workspaces;
    const q = searchFilter.toLowerCase();
    return workspaces.filter((ws) => {
      const name = (ws.name || "").toLowerCase();
      const owner = (ws.owner || "").toLowerCase();
      const repo = (ws.repo || "").toLowerCase();
      const desc = (ws.description || "").toLowerCase();
      return name.includes(q) || owner.includes(q) || repo.includes(q) || desc.includes(q);
    });
  }, [workspaces, searchFilter]);

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
            {showScratchForm ? "Cancel" : "+ Scratch Workspace"}
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
            New Scratch Workspace
          </div>
          <input
            type="text"
            value={scratchName}
            onChange={(e) => setScratchName(e.target.value)}
            placeholder="Workspace name (optional)..."
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

      {/* Search filter — shown when >4 workspaces */}
      {workspaces.length > 4 && (
        <div className="relative">
          <SearchIcon className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-txt-secondary" />
          <input
            type="text"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            placeholder="Filter workspaces..."
            className="w-full bg-bg-secondary text-txt-primary border border-border pl-7 pr-2 py-1.5 font-mono text-xs outline-none focus:border-accent-blue"
          />
        </div>
      )}

      {workspaces.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <TerminalIcon className="w-10 h-10 text-txt-secondary mb-4 opacity-40" />
          <p className="text-sm font-mono text-txt-primary mb-1">No workspaces yet</p>
          <p className="text-xs font-mono text-txt-secondary mb-6 max-w-xs">
            Create a scratch workspace to start coding, or clone a repository from GitHub.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => setShowScratchForm(true)}
              className="px-4 py-2 border border-accent-blue text-accent-blue text-xs font-mono uppercase tracking-wider hover:bg-accent-blue hover:text-bg-primary transition-all cursor-pointer"
            >
              + Scratch Workspace
            </button>
            <button
              onClick={() => setShowCloneForm(true)}
              className="px-4 py-2 border border-terminal-green text-terminal-green text-xs font-mono uppercase tracking-wider hover:bg-terminal-green hover:text-bg-primary transition-all cursor-pointer"
            >
              + Clone Repo
            </button>
          </div>
        </div>
      ) : filteredWorkspaces.length === 0 ? (
        <div className="text-center py-8 text-txt-secondary font-mono text-xs">
          No workspaces match &ldquo;{searchFilter}&rdquo;
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filteredWorkspaces.map((ws) => (
            <WorkspaceItem key={String(ws.workspace_id)} ws={ws} />
          ))}
        </div>
      )}
    </div>
  );
}
