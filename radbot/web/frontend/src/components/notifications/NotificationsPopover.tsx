import { useEffect, useRef, useState, type RefObject } from "react";
import { cn } from "@/lib/utils";
import type { Notification, NotificationType } from "@/types";
import { useNotificationStore } from "@/stores/notification-store";

interface Props {
  buttonRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onSelect: (n: Notification) => void;
}

const TYPE_LABEL: Record<NotificationType, string> = {
  scheduled_task: "SCHED",
  reminder: "REMIND",
  alert: "ALERT",
  ntfy_outbound: "NTFY",
};

const TYPE_COLOR: Record<NotificationType, string> = {
  scheduled_task: "text-accent-blue",
  reminder: "text-terminal-amber",
  alert: "text-terminal-red",
  ntfy_outbound: "text-terminal-green",
};

const TYPE_BG: Record<NotificationType, string> = {
  scheduled_task: "bg-accent-blue/15 border-accent-blue/40",
  reminder: "bg-terminal-amber/15 border-terminal-amber/40",
  alert: "bg-terminal-red/15 border-terminal-red/40",
  ntfy_outbound: "bg-terminal-green/15 border-terminal-green/40",
};

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  if (hours < 24) return `${hours}h`;
  if (days < 7) return `${days}d`;
  return d.toLocaleDateString();
}

export default function NotificationsPopover({
  buttonRef,
  onClose,
  onSelect,
}: Props) {
  const popRef = useRef<HTMLDivElement>(null);
  const [tab, setTab] = useState<"all" | "unread">("all");
  const [pos, setPos] = useState<{ top: number; right: number }>({ top: 56, right: 12 });

  const notifications = useNotificationStore((s) => s.notifications);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const loading = useNotificationStore((s) => s.loading);

  // Position beneath the bell button
  useEffect(() => {
    const place = () => {
      const el = buttonRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setPos({
        top: rect.bottom + 6,
        right: Math.max(12, window.innerWidth - rect.right),
      });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [buttonRef]);

  // Dismiss on outside click + ESC
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (popRef.current?.contains(target)) return;
      if (buttonRef.current?.contains(target)) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose, buttonRef]);

  const items =
    tab === "unread" ? notifications.filter((n) => !n.read) : notifications;

  return (
    <div
      ref={popRef}
      role="dialog"
      aria-label="Notifications"
      className="fixed z-[800] w-[380px] max-w-[calc(100vw-24px)] bg-bg-secondary border border-border rounded-sm shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)] flex flex-col max-h-[70vh]"
      style={{ top: pos.top, right: pos.right }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-bg-tertiary flex-none">
        <div className="flex items-center gap-2">
          <span className="text-[0.65rem] font-mono font-bold tracking-[0.14em] text-txt-primary uppercase">
            Notifications
          </span>
          {unreadCount > 0 && (
            <span className="text-[0.6rem] font-mono bg-accent-blue/20 text-accent-blue px-1.5 py-0.5 rounded-sm border border-accent-blue/30">
              {unreadCount}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          <TabBtn active={tab === "all"} onClick={() => setTab("all")}>
            ALL
          </TabBtn>
          <TabBtn active={tab === "unread"} onClick={() => setTab("unread")}>
            UNREAD
          </TabBtn>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading && items.length === 0 ? (
          <div className="px-3 py-6 text-center text-[0.7rem] font-mono text-txt-secondary/70">
            LOADING…
          </div>
        ) : items.length === 0 ? (
          <div className="px-3 py-6 text-center text-[0.7rem] font-mono text-txt-secondary/70">
            NO NOTIFICATIONS
          </div>
        ) : (
          items.map((n, i) => (
            <button
              key={n.notification_id}
              onClick={() => onSelect(n)}
              className={cn(
                "w-full text-left flex gap-2.5 px-3 py-2.5 cursor-pointer transition-colors",
                "hover:bg-bg-tertiary",
                i < items.length - 1 && "border-b border-border/60",
                !n.read && "bg-bg-tertiary/40",
              )}
            >
              {/* Unread dot */}
              <div className="flex-none pt-1">
                {!n.read ? (
                  <span className="inline-block w-2 h-2 rounded-full bg-accent-blue shadow-[0_0_4px_rgba(53,132,228,0.5)]" />
                ) : (
                  <span className="inline-block w-2 h-2" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span
                    className={cn(
                      "text-[0.55rem] font-mono font-bold tracking-[0.12em] px-1 py-px rounded-sm border",
                      TYPE_BG[n.type],
                      TYPE_COLOR[n.type],
                    )}
                  >
                    {TYPE_LABEL[n.type]}
                  </span>
                  <span className="text-[0.7rem] text-txt-primary font-mono truncate flex-1">
                    {n.title}
                  </span>
                  <span className="text-[0.6rem] text-txt-secondary/70 font-mono flex-none">
                    {formatTime(n.created_at)}
                  </span>
                </div>
                <div className="text-[0.68rem] text-txt-secondary font-mono line-clamp-2 leading-snug">
                  {n.message}
                </div>
              </div>
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-t border-border bg-bg-tertiary flex-none">
        <button
          onClick={markAllRead}
          disabled={unreadCount === 0}
          className="text-[0.62rem] font-mono tracking-[0.12em] uppercase text-txt-secondary hover:text-txt-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Mark all read
        </button>
        <a
          href="/notifications"
          className="text-[0.62rem] font-mono tracking-[0.12em] uppercase text-accent-blue hover:underline no-underline"
        >
          View all →
        </a>
      </div>
    </div>
  );
}

function TabBtn({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2 py-0.5 text-[0.6rem] font-mono font-bold tracking-[0.12em] rounded-sm transition-colors",
        active
          ? "bg-accent-blue/20 text-accent-blue"
          : "text-txt-secondary hover:text-txt-primary",
      )}
    >
      {children}
    </button>
  );
}
