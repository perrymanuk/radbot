import { create } from "zustand";
import type { Notification, NotificationType } from "@/types";
import * as api from "@/lib/api";

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  total: number;
  typeFilter: NotificationType | "all";
  readFilter: "all" | "unread" | "read";
  loading: boolean;

  loadNotifications: (reset?: boolean) => Promise<void>;
  loadMore: () => Promise<void>;
  loadUnreadCount: () => Promise<void>;
  incrementUnread: () => void;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  removeNotification: (id: string) => Promise<void>;
  setTypeFilter: (f: NotificationType | "all") => void;
  setReadFilter: (f: "all" | "unread" | "read") => void;
}

const PAGE_SIZE = 30;

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  total: 0,
  typeFilter: "all",
  readFilter: "all",
  loading: false,

  loadNotifications: async (reset = true) => {
    const { typeFilter, readFilter } = get();
    set({ loading: true });
    try {
      const params: Record<string, string | number> = { limit: PAGE_SIZE, offset: 0 };
      if (typeFilter !== "all") params.type = typeFilter;
      if (readFilter === "unread") params.read = "false";
      else if (readFilter === "read") params.read = "true";

      const data = await api.fetchNotifications(params as Parameters<typeof api.fetchNotifications>[0]);
      set({
        notifications: reset ? data.notifications : [...get().notifications, ...data.notifications],
        total: data.total,
      });
    } catch {
      // API may not be available
    } finally {
      set({ loading: false });
    }
  },

  loadMore: async () => {
    const { notifications, total, typeFilter, readFilter } = get();
    if (notifications.length >= total) return;

    set({ loading: true });
    try {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset: notifications.length,
      };
      if (typeFilter !== "all") params.type = typeFilter;
      if (readFilter === "unread") params.read = "false";
      else if (readFilter === "read") params.read = "true";

      const data = await api.fetchNotifications(params as Parameters<typeof api.fetchNotifications>[0]);
      set({
        notifications: [...notifications, ...data.notifications],
        total: data.total,
      });
    } catch {
      // ignore
    } finally {
      set({ loading: false });
    }
  },

  loadUnreadCount: async () => {
    try {
      const { count } = await api.fetchUnreadCount();
      set({ unreadCount: count });
    } catch {
      // ignore
    }
  },

  incrementUnread: () => set((s) => ({ unreadCount: s.unreadCount + 1 })),

  markRead: async (id) => {
    await api.markNotificationRead(id);
    set((s) => ({
      notifications: s.notifications.map((n) =>
        n.notification_id === id ? { ...n, read: true } : n,
      ),
      unreadCount: Math.max(0, s.unreadCount - 1),
    }));
  },

  markAllRead: async () => {
    const { typeFilter } = get();
    await api.markAllNotificationsRead(typeFilter !== "all" ? typeFilter : undefined);
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }));
  },

  removeNotification: async (id) => {
    const n = get().notifications.find((n) => n.notification_id === id);
    await api.deleteNotification(id);
    set((s) => ({
      notifications: s.notifications.filter((n) => n.notification_id !== id),
      total: Math.max(0, s.total - 1),
      unreadCount: n && !n.read ? Math.max(0, s.unreadCount - 1) : s.unreadCount,
    }));
  },

  setTypeFilter: (f) => {
    set({ typeFilter: f });
    get().loadNotifications();
  },

  setReadFilter: (f) => {
    set({ readFilter: f });
    get().loadNotifications();
  },
}));
