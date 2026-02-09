import { create } from "zustand";
import * as adminApi from "@/lib/admin-api";
import type { IntegrationStatus, CredentialEntry } from "@/lib/admin-api";

interface Toast {
  message: string;
  type: "success" | "error";
  id: number;
}

interface AdminState {
  // Auth
  authenticated: boolean;
  token: string;
  setToken: (token: string) => void;
  authenticate: () => Promise<boolean>;
  logout: () => void;

  // Navigation
  activePanel: string;
  setActivePanel: (panel: string) => void;

  // Live config (merged file + DB)
  liveConfig: Record<string, any>;
  liveConfigLoading: boolean;
  loadLiveConfig: () => Promise<Record<string, any>>;
  invalidateLiveConfig: () => void;

  // Integration status (powers sidebar dots)
  status: IntegrationStatus;
  loadStatus: () => Promise<void>;

  // Credentials
  credentials: CredentialEntry[];
  credentialsLoading: boolean;
  loadCredentials: () => Promise<void>;

  // Toast notifications
  toasts: Toast[];
  toast: (message: string, type?: "success" | "error") => void;
  dismissToast: (id: number) => void;

  // Config save helpers
  saveConfigSection: (section: string, data: Record<string, any>) => Promise<void>;
  mergeConfigSection: (section: string, patch: Record<string, any>) => Promise<void>;
  saveCredential: (name: string, value: string, type?: string, description?: string) => Promise<void>;
  deleteCredential: (name: string) => Promise<void>;
  testConnection: (endpoint: string, body?: Record<string, any>) => Promise<adminApi.TestResult>;

  // Loading/error
  loading: boolean;
  error: string | null;
}

let _toastId = 0;
let _liveConfigCache: Record<string, any> | null = null;
let _liveConfigTime = 0;

function deepMerge(target: Record<string, any>, source: Record<string, any>): Record<string, any> {
  const result = { ...target };
  for (const [k, v] of Object.entries(source)) {
    if (v && typeof v === "object" && !Array.isArray(v) && typeof result[k] === "object" && !Array.isArray(result[k])) {
      result[k] = deepMerge(result[k], v);
    } else {
      result[k] = v;
    }
  }
  return result;
}

export const useAdminStore = create<AdminState>((set, get) => ({
  // ── Auth ───────────────────────────────────────────────
  authenticated: false,
  token: sessionStorage.getItem("admin_token") || "",

  setToken: (token) => set({ token }),

  authenticate: async () => {
    const { token } = get();
    try {
      await adminApi.listCredentials(token);
      sessionStorage.setItem("admin_token", token);
      set({ authenticated: true, error: null });
      get().loadCredentials();
      get().loadStatus();
      return true;
    } catch {
      set({ error: "Invalid token" });
      return false;
    }
  },

  logout: () => {
    sessionStorage.removeItem("admin_token");
    _liveConfigCache = null;
    set({ authenticated: false, token: "", credentials: [], liveConfig: {}, status: {} });
  },

  // ── Navigation ─────────────────────────────────────────
  activePanel: "google",
  setActivePanel: (panel) => set({ activePanel: panel }),

  // ── Live Config ────────────────────────────────────────
  liveConfig: {},
  liveConfigLoading: false,

  loadLiveConfig: async () => {
    // Cache for 5 seconds
    if (_liveConfigCache && Date.now() - _liveConfigTime < 5000) {
      set({ liveConfig: _liveConfigCache });
      return _liveConfigCache;
    }
    const { token } = get();
    set({ liveConfigLoading: true });
    try {
      const cfg = await adminApi.getLiveConfig(token);
      _liveConfigCache = cfg;
      _liveConfigTime = Date.now();
      set({ liveConfig: cfg, liveConfigLoading: false });
      return cfg;
    } catch (e: any) {
      set({ liveConfigLoading: false });
      get().toast("Failed to load config: " + e.message, "error");
      return {};
    }
  },

  invalidateLiveConfig: () => {
    _liveConfigCache = null;
    _liveConfigTime = 0;
  },

  // ── Status ─────────────────────────────────────────────
  status: {},
  loadStatus: async () => {
    const { token } = get();
    try {
      const s = await adminApi.getStatus(token);
      set({ status: s });
    } catch {
      // Status endpoint not critical
    }
  },

  // ── Credentials ────────────────────────────────────────
  credentials: [],
  credentialsLoading: false,

  loadCredentials: async () => {
    const { token } = get();
    set({ credentialsLoading: true });
    try {
      const creds = await adminApi.listCredentials(token);
      set({ credentials: creds, credentialsLoading: false });
    } catch {
      set({ credentialsLoading: false, error: "Failed to load credentials" });
    }
  },

  // ── Toast ──────────────────────────────────────────────
  toasts: [],
  toast: (message, type = "success") => {
    const id = ++_toastId;
    set((s) => ({ toasts: [...s.toasts, { message, type, id }] }));
    setTimeout(() => get().dismissToast(id), 4000);
  },
  dismissToast: (id) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
  },

  // ── Config helpers ─────────────────────────────────────
  saveConfigSection: async (section, data) => {
    const { token } = get();
    await adminApi.saveConfigSection(token, section, data);
    get().invalidateLiveConfig();
  },

  mergeConfigSection: async (section, patch) => {
    const { token } = get();
    let current: Record<string, any> = {};
    try {
      current = await adminApi.getConfigSection(token, section);
    } catch {
      try {
        const live = await adminApi.getLiveConfig(token);
        current = live[section] || {};
      } catch {
        // start fresh
      }
    }
    const merged = deepMerge(current, patch);
    await adminApi.saveConfigSection(token, section, merged);
    get().invalidateLiveConfig();
  },

  saveCredential: async (name, value, type = "api_key", description) => {
    const { token } = get();
    await adminApi.storeCredential(token, name, value, type, description);
    get().loadCredentials();
  },

  deleteCredential: async (name) => {
    const { token } = get();
    await adminApi.deleteCredential(token, name);
    get().loadCredentials();
  },

  testConnection: async (endpoint, body = {}) => {
    const { token } = get();
    return adminApi.testConnection(token, endpoint, body);
  },

  // ── Loading/Error ──────────────────────────────────────
  loading: false,
  error: null,
}));
