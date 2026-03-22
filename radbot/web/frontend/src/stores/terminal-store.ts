import { create } from "zustand";
import type { Workspace, TerminalSession, TerminalStatus } from "@/types/terminal";
import * as termApi from "@/lib/terminal-api";

interface TerminalState {
  // Workspaces
  workspaces: Workspace[];
  loadWorkspaces: () => Promise<void>;

  // Terminal sessions
  sessions: TerminalSession[];
  loadSessions: () => Promise<void>;

  // Active terminal
  activeTerminalId: string | null;
  setActiveTerminalId: (id: string | null) => void;

  // Status
  status: TerminalStatus | null;
  loadStatus: () => Promise<void>;

  // Clone form
  showCloneForm: boolean;
  setShowCloneForm: (show: boolean) => void;

  // Actions
  openTerminal: (workspaceId: string, resumeSessionId?: string) => Promise<void>;
  killTerminal: (terminalId: string) => Promise<void>;
  cloneRepo: (owner: string, repo: string, branch: string) => Promise<{ status: string; message?: string }>;
  deleteWorkspace: (workspaceId: string) => Promise<void>;
  updateWorkspace: (workspaceId: string, data: { name?: string; description?: string }) => Promise<void>;
  createScratchWorkspace: (name?: string, description?: string) => Promise<void>;

  // Error
  error: string | null;
  clearError: () => void;
}

export const useTerminalStore = create<TerminalState>((set, get) => ({
  workspaces: [],
  sessions: [],
  activeTerminalId: null,
  status: null,
  showCloneForm: false,
  error: null,

  loadWorkspaces: async () => {
    try {
      const workspaces = await termApi.fetchWorkspaces();
      set({ workspaces });
    } catch (e) {
      set({ error: `Failed to load workspaces: ${e}` });
    }
  },

  loadSessions: async () => {
    try {
      const sessions = await termApi.listTerminalSessions();
      set({ sessions });
    } catch (e) {
      set({ error: `Failed to load sessions: ${e}` });
    }
  },

  setActiveTerminalId: (id) => set({ activeTerminalId: id }),

  loadStatus: async () => {
    try {
      const status = await termApi.getTerminalStatus();
      set({ status });
    } catch (e) {
      set({ status: { status: "error", message: String(e), cli_available: false, token_configured: false } });
    }
  },

  setShowCloneForm: (show) => set({ showCloneForm: show }),

  openTerminal: async (workspaceId, resumeSessionId) => {
    try {
      set({ error: null });
      const session = await termApi.createTerminalSession(workspaceId, resumeSessionId);
      set((s) => ({
        activeTerminalId: session.terminal_id,
        sessions: [...s.sessions, session],
      }));
    } catch (e) {
      set({ error: `Failed to create terminal: ${e}` });
    }
  },

  killTerminal: async (terminalId) => {
    try {
      await termApi.killTerminalSession(terminalId);
      set((s) => ({
        sessions: s.sessions.filter((sess) => sess.terminal_id !== terminalId),
        activeTerminalId: s.activeTerminalId === terminalId ? null : s.activeTerminalId,
      }));
    } catch (e) {
      set({ error: `Failed to kill terminal: ${e}` });
    }
  },

  cloneRepo: async (owner, repo, branch) => {
    try {
      set({ error: null });
      const result = await termApi.cloneRepository(owner, repo, branch);
      if (result.status === "success") {
        await get().loadWorkspaces();
        set({ showCloneForm: false });
      }
      return result;
    } catch (e) {
      const msg = `Failed to clone repository: ${e}`;
      set({ error: msg });
      return { status: "error", message: msg };
    }
  },

  deleteWorkspace: async (workspaceId) => {
    try {
      set({ error: null });
      await termApi.deleteWorkspace(workspaceId);
      set((s) => ({
        workspaces: s.workspaces.filter((ws) => String(ws.workspace_id) !== workspaceId),
        // If active terminal was in this workspace, go back to selector
        activeTerminalId:
          s.sessions.find(
            (sess) => sess.workspace_id === workspaceId && sess.terminal_id === s.activeTerminalId,
          )
            ? null
            : s.activeTerminalId,
      }));
    } catch (e) {
      set({ error: `Failed to delete workspace: ${e}` });
    }
  },

  updateWorkspace: async (workspaceId, data) => {
    try {
      await termApi.updateWorkspace(workspaceId, data);
      set((s) => ({
        workspaces: s.workspaces.map((ws) =>
          String(ws.workspace_id) === workspaceId
            ? { ...ws, ...(data.name !== undefined && { name: data.name }), ...(data.description !== undefined && { description: data.description }) }
            : ws,
        ),
      }));
    } catch (e) {
      set({ error: `Failed to update workspace: ${e}` });
    }
  },

  createScratchWorkspace: async (name, description) => {
    try {
      set({ error: null });
      const ws = await termApi.createScratchWorkspace(name, description);
      set((s) => ({
        workspaces: [ws, ...s.workspaces],
        showCloneForm: false,
      }));
    } catch (e) {
      set({ error: `Failed to create scratch workspace: ${e}` });
    }
  },

  clearError: () => set({ error: null }),
}));
