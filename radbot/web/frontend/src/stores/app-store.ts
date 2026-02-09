import { create } from "zustand";
import type {
  Message,
  Session,
  Task,
  Project,
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
  createNewSession: (name?: string) => Promise<void>;

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

  // ── Tasks ───────────────────────────────────────────────
  tasks: Task[];
  projects: Project[];
  loadTasks: () => Promise<void>;
  loadProjects: () => Promise<void>;
  taskStatusFilter: string;
  taskProjectFilter: string;
  taskSearch: string;
  setTaskStatusFilter: (f: string) => void;
  setTaskProjectFilter: (f: string) => void;
  setTaskSearch: (s: string) => void;

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
    });
  },

  createNewSession: async (name) => {
    try {
      const session = await api.createSession(name);
      get().switchSession(session.id);
      get().loadSessions();
    } catch {
      // Fallback: generate locally
      const id = uuid();
      get().switchSession(id);
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

  // ── Tasks ───────────────────────────────────────────────
  tasks: [],
  projects: [],

  loadTasks: async () => {
    try {
      const tasks = await api.fetchTasks();
      set({ tasks: Array.isArray(tasks) ? tasks : [] });
    } catch {
      // Tasks API may not be available
    }
  },

  loadProjects: async () => {
    try {
      const projects = await api.fetchProjects();
      set({ projects: Array.isArray(projects) ? projects : [] });
    } catch {
      // Projects API may not be available
    }
  },

  taskStatusFilter: "all",
  taskProjectFilter: "all",
  taskSearch: "",
  setTaskStatusFilter: (f) => set({ taskStatusFilter: f }),
  setTaskProjectFilter: (f) => set({ taskProjectFilter: f }),
  setTaskSearch: (s) => set({ taskSearch: s }),

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
}));
