import { useState } from "react";
import { cn } from "@/lib/utils";
import type { Notification, NotificationType } from "@/types";
import { useNotificationStore } from "@/stores/notification-store";

const TYPE_CONFIG: Record<NotificationType, { label: string; color: string; border: string }> = {
  scheduled_task: {
    label: "SCHED",
    color: "bg-accent-blue/20 text-accent-blue border-accent-blue/40",
    border: "border-l-accent-blue",
  },
  reminder: {
    label: "REMIND",
    color: "bg-terminal-amber/20 text-terminal-amber border-terminal-amber/40",
    border: "border-l-terminal-amber",
  },
  alert: {
    label: "ALERT",
    color: "bg-terminal-red/20 text-terminal-red border-terminal-red/40",
    border: "border-l-terminal-red",
  },
  ntfy_outbound: {
    label: "NTFY",
    color: "bg-terminal-green/20 text-terminal-green border-terminal-green/40",
    border: "border-l-terminal-green",
  },
};

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

export default function NotificationItem({ notification }: { notification: Notification }) {
  const [expanded, setExpanded] = useState(false);
  const markRead = useNotificationStore((s) => s.markRead);
  const removeNotification = useNotificationStore((s) => s.removeNotification);

  const config = TYPE_CONFIG[notification.type] ?? TYPE_CONFIG.ntfy_outbound;

  const handleClick = () => {
    if (!notification.read) {
      markRead(notification.notification_id);
    }
    setExpanded(!expanded);
  };

  return (
    <div
      className={cn(
        "border-l-2 border border-border bg-bg-secondary rounded-sm cursor-pointer transition-all hover:bg-bg-tertiary",
        !notification.read ? config.border : "border-l-border",
        !notification.read && "bg-bg-secondary/80",
      )}
      onClick={handleClick}
    >
      <div className="px-3 py-2.5 flex items-start gap-3">
        {/* Unread dot */}
        <div className="flex-shrink-0 pt-1">
          {!notification.read ? (
            <span className="inline-block w-2 h-2 rounded-full bg-accent-blue shadow-[0_0_4px_rgba(53,132,228,0.5)]" />
          ) : (
            <span className="inline-block w-2 h-2" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={cn(
                "text-[0.6rem] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border",
                config.color,
              )}
            >
              {config.label}
            </span>
            <span className="text-[0.75rem] text-txt-primary font-mono truncate">
              {notification.title}
            </span>
            <span className="text-[0.65rem] text-txt-secondary ml-auto flex-shrink-0 font-mono">
              {formatTime(notification.created_at)}
            </span>
          </div>

          {/* Message preview or full */}
          <div
            className={cn(
              "text-[0.75rem] text-txt-secondary font-mono leading-relaxed",
              !expanded && "line-clamp-2",
            )}
          >
            <pre className="whitespace-pre-wrap font-mono m-0 text-inherit">
              {notification.message}
            </pre>
          </div>

          {/* Expanded actions */}
          {expanded && (
            <div className="flex items-center gap-3 mt-2 pt-2 border-t border-border/50">
              {notification.session_id && (
                <a
                  href={`/?session=${notification.session_id}`}
                  className="text-[0.65rem] text-accent-blue hover:underline font-mono"
                  onClick={(e) => e.stopPropagation()}
                >
                  VIEW SESSION
                </a>
              )}
              <button
                className="text-[0.65rem] text-terminal-red hover:text-terminal-red/80 font-mono ml-auto"
                onClick={(e) => {
                  e.stopPropagation();
                  removeNotification(notification.notification_id);
                }}
              >
                DELETE
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
