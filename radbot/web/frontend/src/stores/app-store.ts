import { create } from "zustand";
import type {
  Message,
  Session,
  AgentEvent,
  AgentInfo,
  ConnectionStatus,
  PanelType,
  EventCategory,
} from "@/types";
import * as api from "@/lib/api";
import { uuid } from "@/lib/utils";

interface AppState {
  // ── Session ─────────────────────────────────────────────
  sessionId: string | null;
  sessions: Session[];
  initSession: () => Promise<void>;
  setSessionId: (id: string) => void;
  loadSessions: () => Promise<void>;
  switchSession: (id: string) => void;
  createNewSession: (name?: string, description?: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  updateSession: (id: string, data: { name?: string; description?: string }) => Promise<void>;

  // ── Messages ────────────────────────────────────────────
  messages: Message[];
  addMessage: (msg: Message) => void;
  setMessages: (msgs: Message[]) => void;
  clearMessages: () => void;

  // ── Connection ──────────────────────────────────────────
  connectionStatus: ConnectionStatus;
  setConnectionStatus: (status: ConnectionStatus) => void;

  // ── Agent Info ──────────────────────────────────────────
  agentInfo: AgentInfo | null;
  loadAgentInfo: () => Promise<void>;

  // ── Events ──────────────────────────────────────────────
  events: AgentEvent[];
  addEvents: (evts: AgentEvent[]) => void;
  clearEvents: () => void;
  eventFilter: EventCategory | "all";
  setEventFilter: (f: EventCategory | "all") => void;

  // ── Panels ──────────────────────────────────────────────
  activePanel: PanelType;
  togglePanel: (panel: PanelType) => void;
  setActivePanel: (panel: PanelType) => void;

  // ── Input History ───────────────────────────────────────
  inputHistory: string[];
  inputHistoryIndex: number;
  addToInputHistory: (text: string) => void;
  navigateHistory: (direction: "up" | "down") => string;

  // ── Memory mode ─────────────────────────────────────────
  memoryMode: boolean;
  setMemoryMode: (on: boolean) => void;

  // ── Unread notifications ────────────────────────────────
  unreadNotificationCount: number;
  setUnreadNotificationCount: (n: number) => void;
  incrementUnreadNotifications: () => void;

  // ── Session stats (tokens + cost) ──────────────────────
  sessionStats: SessionStats | null;
  setSessionStats: (stats: SessionStats | null) => void;
  refreshSessionStats: () => Promise<void>;

  // ── Split mode (chat + panel side-by-side toggle) ──────
  splitMode: boolean;
  toggleSplitMode: () => void;
}

export interface SessionStats {
  inputTokens: number;
  outputTokens: number;
  contextTokens: number;
  contextWindow: number;
  costUsd: number;
  costTodayUsd: number;
  costMonthUsd: number;
  model?: string;
}

export const useAppStore = create<AppState>((set, get) => ({
  // ── Session ─────────────────────────────────────────────
  sessionId: null,
  sessions: [],

  initSession: async () => {
    try {
      const sessions = await api.fetchSessions();
      set({ sessions });
      if (sessions.length > 0) {
        set({ sessionId: sessions[0].id });
      } else {
        set({ sessionId: uuid() });
      }
    } catch {
      set({ sessionId: uuid() });
    }
    get().loadAgentInfo();
    // Load unread notification count for badge
    api.fetchUnreadCount().then(({ count }) => set({ unreadNotificationCount: count })).catch(() => {});
    get().refreshSessionStats();
  },

  setSessionId: (id) => set({ sessionId: id }),

  loadSessions: async () => {
    try {
      const sessions = await api.fetchSessions();
      set({ sessions });
    } catch {
      // Sessions API may not be available
    }
  },

  switchSession: (id) => {
    if (id === get().sessionId) return;
    set({
      sessionId: id,
      messages: [],
      events: [],
      connectionStatus: "connecting",
      sessionStats: null,
    });
    get().refreshSessionStats();
  },

  createNewSession: async (name, description) => {
    try {
      const session = await api.createSession(name, description);
      get().switchSession(session.id);
      get().loadSessions();
    } catch {
      // Fallback: generate locally
      const id = uuid();
      get().switchSession(id);
    }
  },

  deleteSession: async (id) => {
    try {
      await api.deleteSession(id);
      const { sessions, sessionId } = get();
      const remaining = sessions.filter((s) => s.id !== id);
      set({ sessions: remaining });
      if (sessionId === id) {
        if (remaining.length > 0) {
          get().switchSession(remaining[0].id);
        } else {
          await get().createNewSession();
        }
      }
    } catch {
      // Reload sessions to get accurate state
      get().loadSessions();
    }
  },

  updateSession: async (id, data) => {
    try {
      await api.updateSession(id, data);
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === id
            ? { ...sess, ...(data.name && { name: data.name }), ...(data.description !== undefined && { description: data.description }) }
            : sess,
        ),
      }));
    } catch {
      // Ignore
    }
  },

  // ── Messages ────────────────────────────────────────────
  messages: [],
  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, msg],
    })),
  setMessages: (msgs) => set({ messages: msgs }),
  clearMessages: () => set({ messages: [] }),

  // ── Connection ──────────────────────────────────────────
  connectionStatus: "disconnected",
  setConnectionStatus: (status) => set({ connectionStatus: status }),

  // ── Agent Info ──────────────────────────────────────────
  agentInfo: null,
  loadAgentInfo: async () => {
    try {
      const info = await api.fetchAgentInfo();
      set({ agentInfo: info });
    } catch {
      // Agent info API may not be available
    }
  },

  // ── Events ──────────────────────────────────────────────
  events: [],
  addEvents: (evts) =>
    set((s) => ({
      events: [...s.events, ...evts],
    })),
  clearEvents: () => set({ events: [] }),
  eventFilter: "all",
  setEventFilter: (f) => set({ eventFilter: f }),

  // ── Panels ──────────────────────────────────────────────
  activePanel: null,
  togglePanel: (panel) =>
    set((s) => ({
      activePanel: s.activePanel === panel ? null : panel,
    })),
  setActivePanel: (panel) => set({ activePanel: panel }),

  // ── Input History ───────────────────────────────────────
  inputHistory: [],
  inputHistoryIndex: -1,
  addToInputHistory: (text) =>
    set((s) => ({
      inputHistory: [...s.inputHistory, text],
      inputHistoryIndex: -1,
    })),
  navigateHistory: (direction) => {
    const { inputHistory, inputHistoryIndex } = get();
    if (inputHistory.length === 0) return "";

    let newIndex: number;
    if (direction === "up") {
      newIndex =
        inputHistoryIndex === -1
          ? inputHistory.length - 1
          : Math.max(0, inputHistoryIndex - 1);
    } else {
      newIndex =
        inputHistoryIndex === -1
          ? -1
          : inputHistoryIndex >= inputHistory.length - 1
            ? -1
            : inputHistoryIndex + 1;
    }

    set({ inputHistoryIndex: newIndex });
    return newIndex === -1 ? "" : inputHistory[newIndex];
  },

  // ── Memory mode ─────────────────────────────────────────
  memoryMode: false,
  setMemoryMode: (on) => set({ memoryMode: on }),

  // ── Unread notifications ────────────────────────────────
  unreadNotificationCount: 0,
  setUnreadNotificationCount: (n) => set({ unreadNotificationCount: n }),
  incrementUnreadNotifications: () =>
    set((s) => ({ unreadNotificationCount: s.unreadNotificationCount + 1 })),

  // ── Session stats ──────────────────────────────────────
  sessionStats: null,
  setSessionStats: (stats) => set({ sessionStats: stats }),
  refreshSessionStats: async () => {
    const id = get().sessionId;
    if (!id) return;
    try {
      const stats = await api.fetchSessionStats(id);
      set({ sessionStats: stats });
    } catch {
      // API may be unavailable; keep prior state.
    }
  },

  // ── Split mode ─────────────────────────────────────────
  splitMode: false,
  toggleSplitMode: () => set((s) => ({ splitMode: !s.splitMode })),
}));
