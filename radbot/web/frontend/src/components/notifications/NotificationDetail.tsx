import { useEffect } from "react";
import { cn } from "@/lib/utils";
import type { Notification, NotificationType } from "@/types";
import { useNotificationStore } from "@/stores/notification-store";

interface Props {
  notification: Notification;
  onClose: () => void;
}

const TYPE_LABEL: Record<NotificationType, string> = {
  scheduled_task: "SCHEDULED TASK",
  reminder: "REMINDER",
  alert: "ALERT",
  ntfy_outbound: "NTFY",
};

const TYPE_ACCENT_VAR: Record<NotificationType, string> = {
  scheduled_task: "#3584e4",
  reminder: "#FFBF00",
  alert: "#CC0000",
  ntfy_outbound: "#33FF33",
};

const TYPE_PILL: Record<NotificationType, string> = {
  scheduled_task: "bg-accent-blue/20 text-accent-blue border-accent-blue/40",
  reminder: "bg-terminal-amber/20 text-terminal-amber border-terminal-amber/40",
  alert: "bg-terminal-red/20 text-terminal-red border-terminal-red/40",
  ntfy_outbound: "bg-terminal-green/20 text-terminal-green border-terminal-green/40",
};

function formatFullTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function NotificationDetail({ notification, onClose }: Props) {
  const markRead = useNotificationStore((s) => s.markRead);
  const removeNotification = useNotificationStore((s) => s.removeNotification);

  const accent = TYPE_ACCENT_VAR[notification.type];

  // Mark as read on open
  useEffect(() => {
    if (!notification.read) {
      markRead(notification.notification_id);
    }
  }, [notification.notification_id, notification.read, markRead]);

  // ESC to close, body scroll lock
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  const handleDelete = async () => {
    await removeNotification(notification.notification_id);
    onClose();
  };

  const metadataEntries = notification.metadata
    ? Object.entries(notification.metadata)
    : [];

  return (
    <>
      {/* Scrim */}
      <div
        onClick={onClose}
        aria-hidden
        className="fixed inset-0 z-[900] bg-black/55 backdrop-blur-[3px]"
      />
      {/* Drawer */}
      <div
        role="dialog"
        aria-label={notification.title}
        className="fixed top-0 right-0 bottom-0 z-[901] w-[min(540px,calc(100vw-24px))] bg-bg-primary flex flex-col animate-drawer-in"
        style={{
          borderLeft: `2px solid ${accent}`,
          boxShadow: `-30px 0 60px -20px rgba(0,0,0,0.7), 0 0 100px -40px ${accent}`,
        }}
      >
        {/* Header */}
        <div
          className="flex items-start gap-3 px-5 py-3.5 border-b border-border flex-none"
          style={{
            background: `linear-gradient(180deg, color-mix(in oklch, ${accent} 12%, var(--tw-bg-tertiary, #1b2939)), #121c2b)`,
          }}
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span
                className={cn(
                  "text-[0.6rem] font-mono font-bold tracking-[0.14em] px-1.5 py-0.5 rounded-sm border",
                  TYPE_PILL[notification.type],
                )}
              >
                {TYPE_LABEL[notification.type]}
              </span>
              {notification.priority && notification.priority !== "normal" && (
                <span className="text-[0.6rem] font-mono tracking-[0.14em] uppercase text-txt-secondary">
                  · {notification.priority}
                </span>
              )}
              <span className="text-[0.6rem] font-mono text-txt-secondary/80">
                · {formatFullTime(notification.created_at)}
              </span>
            </div>
            <h2 className="text-[17px] font-bold text-txt-primary leading-tight [text-wrap:pretty] m-0">
              {notification.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-[30px] h-[30px] flex-none rounded-sm grid place-items-center text-txt-secondary border border-border hover:text-txt-primary hover:bg-bg-tertiary transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 pt-4 pb-6">
          {/* Message */}
          <DrawerSection label="MESSAGE">
            <pre className="text-[0.85rem] text-txt-primary font-mono leading-relaxed whitespace-pre-wrap m-0">
              {notification.message}
            </pre>
          </DrawerSection>

          {/* Linked session */}
          {notification.session_id && (
            <DrawerSection label="SESSION">
              <Row label="session_id" value={notification.session_id} mono />
            </DrawerSection>
          )}

          {/* Source */}
          {notification.source_id && (
            <DrawerSection label="SOURCE">
              <Row label="source_id" value={notification.source_id} mono />
            </DrawerSection>
          )}

          {/* Metadata */}
          {metadataEntries.length > 0 && (
            <DrawerSection label="METADATA">
              <div className="flex flex-col">
                {metadataEntries.map(([k, v]) => (
                  <Row
                    key={k}
                    label={k}
                    value={
                      typeof v === "object"
                        ? JSON.stringify(v, null, 2)
                        : String(v)
                    }
                    mono
                  />
                ))}
              </div>
            </DrawerSection>
          )}

          {/* System ids */}
          <DrawerSection label="SYSTEM">
            <Row label="notification_id" value={notification.notification_id} mono />
            <Row
              label="status"
              value={notification.read ? "read" : "unread"}
            />
          </DrawerSection>
        </div>

        {/* Footer actions */}
        <div className="flex items-center gap-2 flex-wrap px-5 py-3 border-t border-border bg-bg-tertiary flex-none">
          {notification.session_id && (
            <PrimaryBtn
              href={`/?session=${notification.session_id}`}
              color={accent}
            >
              VIEW SESSION
            </PrimaryBtn>
          )}
          <GhostBtn onClick={handleDelete} danger>
            DELETE
          </GhostBtn>
          <div className="flex-1" />
          <GhostBtn onClick={onClose}>ESC ✕</GhostBtn>
        </div>
      </div>
    </>
  );
}

function DrawerSection({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-4 first:mt-2">
      <div className="font-mono text-[9px] font-bold tracking-[0.16em] text-txt-secondary uppercase mb-1.5">
        {label}
      </div>
      {children}
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="row-dashed flex gap-3 py-1.5 items-start">
      <span className="text-[0.7rem] font-mono text-txt-secondary min-w-[110px] flex-none">
        {label}
      </span>
      <span
        className={cn(
          "text-[0.75rem] text-txt-primary break-all flex-1",
          mono && "font-mono",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function PrimaryBtn({
  children,
  color,
  href,
  onClick,
}: {
  children: React.ReactNode;
  color: string;
  href?: string;
  onClick?: () => void;
}) {
  const className = cn(
    "inline-flex items-center gap-1.5 px-3 py-1.5 text-[0.7rem] font-mono font-bold tracking-[0.12em] uppercase rounded-sm",
    "no-underline transition-colors cursor-pointer",
  );
  const style = {
    color: "#0e1419",
    background: color,
    boxShadow: `0 0 20px -6px ${color}`,
  };
  if (href) {
    return (
      <a href={href} className={className} style={style}>
        {children}
      </a>
    );
  }
  return (
    <button onClick={onClick} className={className} style={style}>
      {children}
    </button>
  );
}

function GhostBtn({
  children,
  onClick,
  danger,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[0.7rem] font-mono font-bold tracking-[0.12em] uppercase rounded-sm",
        "bg-transparent border border-border transition-colors cursor-pointer",
        danger
          ? "text-terminal-red hover:bg-terminal-red/10 hover:border-terminal-red/40"
          : "text-txt-secondary hover:text-txt-primary hover:bg-bg-secondary",
      )}
    >
      {children}
    </button>
  );
}
