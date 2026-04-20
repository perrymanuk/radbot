import { useEffect } from "react";
import { cn } from "@/lib/utils";
import { useNotificationStore } from "@/stores/notification-store";
import NotificationItem from "@/components/notifications/NotificationItem";
import NotificationFilters from "@/components/notifications/NotificationFilters";
import type { Notification } from "@/types";

function groupByDate(notifications: Notification[]): Map<string, Notification[]> {
  const groups = new Map<string, Notification[]>();
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);

  for (const n of notifications) {
    const d = new Date(n.created_at);
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());

    let label: string;
    if (day.getTime() === today.getTime()) {
      label = "Today";
    } else if (day.getTime() === yesterday.getTime()) {
      label = "Yesterday";
    } else {
      label = day.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
    }

    const group = groups.get(label) ?? [];
    group.push(n);
    groups.set(label, group);
  }

  return groups;
}

export default function NotificationsPage() {
  const notifications = useNotificationStore((s) => s.notifications);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const total = useNotificationStore((s) => s.total);
  const loading = useNotificationStore((s) => s.loading);
  const loadNotifications = useNotificationStore((s) => s.loadNotifications);
  const loadMore = useNotificationStore((s) => s.loadMore);
  const loadUnreadCount = useNotificationStore((s) => s.loadUnreadCount);
  const markAllRead = useNotificationStore((s) => s.markAllRead);

  useEffect(() => {
    loadNotifications();
    loadUnreadCount();
  }, [loadNotifications, loadUnreadCount]);

  const grouped = groupByDate(notifications);
  const hasMore = notifications.length < total;

  return (
    <div
      className="flex flex-col h-screen bg-bg-primary text-txt-primary"
      data-test="notifications-page"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5 bg-bg-tertiary border-b border-border flex-shrink-0"
        data-test="notifications-header"
      >
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="text-[0.7rem] font-mono text-txt-secondary hover:text-txt-primary no-underline"
          >
            &lt; CHAT
          </a>
          <div className="w-px h-5 bg-border" />
          <h1 className="text-sm font-mono tracking-wider text-txt-secondary uppercase m-0">
            Notifications
          </h1>
          {unreadCount > 0 && (
            <span className="text-[0.65rem] font-mono bg-accent-blue/20 text-accent-blue px-1.5 py-0.5 rounded">
              {unreadCount} unread
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <NotificationFilters />
          {unreadCount > 0 && (
            <button
              onClick={markAllRead}
              className={cn(
                "px-2.5 py-1.5 text-[0.7rem] font-mono uppercase tracking-wider",
                "bg-bg-tertiary text-accent-blue border border-accent-blue/40 rounded-sm",
                "hover:bg-accent-blue/15 transition-all cursor-pointer",
                "focus:outline-none focus:ring-1 focus:ring-accent-blue",
              )}
            >
              Mark All Read
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {notifications.length === 0 && !loading ? (
          <div
            className="flex flex-col items-center justify-center h-64 text-txt-secondary"
            data-test="notifications-empty-state"
          >
            <span className="text-2xl mb-2 opacity-40">--</span>
            <span className="text-[0.8rem] font-mono">No notifications</span>
            <span className="text-[0.7rem] font-mono mt-1 opacity-60">
              Scheduled tasks and alerts will appear here
            </span>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-4">
            {Array.from(grouped.entries()).map(([dateLabel, items]) => (
              <div key={dateLabel}>
                <div className="text-[0.65rem] font-mono text-txt-secondary uppercase tracking-wider mb-2 px-1">
                  {dateLabel}
                </div>
                <div className="space-y-1.5">
                  {items.map((n) => (
                    <NotificationItem key={n.notification_id} notification={n} />
                  ))}
                </div>
              </div>
            ))}

            {/* Load More */}
            {hasMore && (
              <div className="flex justify-center py-4">
                <button
                  onClick={loadMore}
                  disabled={loading}
                  className={cn(
                    "px-4 py-2 text-[0.7rem] font-mono uppercase tracking-wider",
                    "bg-bg-secondary text-txt-secondary border border-border rounded-sm",
                    "hover:bg-bg-tertiary hover:text-txt-primary transition-all cursor-pointer",
                    "focus:outline-none focus:ring-1 focus:ring-accent-blue",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                  )}
                >
                  {loading ? "Loading..." : `Load More (${total - notifications.length} remaining)`}
                </button>
              </div>
            )}
          </div>
        )}

        {loading && notifications.length === 0 && (
          <div className="flex justify-center py-12">
            <span className="text-[0.8rem] font-mono text-txt-secondary animate-pulse">
              Loading notifications...
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
