import { cn } from "@/lib/utils";
import { useNotificationStore } from "@/stores/notification-store";
import type { NotificationType } from "@/types";

const TYPE_OPTIONS: { value: NotificationType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "scheduled_task", label: "Scheduled" },
  { value: "reminder", label: "Reminders" },
  { value: "alert", label: "Alerts" },
  { value: "ntfy_outbound", label: "ntfy" },
];

const READ_OPTIONS: { value: "all" | "unread" | "read"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "unread", label: "Unread" },
  { value: "read", label: "Read" },
];

const selectClass = cn(
  "bg-bg-primary border border-border text-txt-primary text-[0.7rem] font-mono",
  "px-2 py-1.5 rounded-sm focus:outline-none focus:ring-1 focus:ring-accent-blue",
  "cursor-pointer appearance-none",
);

export default function NotificationFilters() {
  const typeFilter = useNotificationStore((s) => s.typeFilter);
  const readFilter = useNotificationStore((s) => s.readFilter);
  const setTypeFilter = useNotificationStore((s) => s.setTypeFilter);
  const setReadFilter = useNotificationStore((s) => s.setReadFilter);

  return (
    <div className="flex items-center gap-2">
      <select
        value={typeFilter}
        onChange={(e) => setTypeFilter(e.target.value as NotificationType | "all")}
        className={selectClass}
        aria-label="Filter by type"
      >
        {TYPE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <select
        value={readFilter}
        onChange={(e) => setReadFilter(e.target.value as "all" | "unread" | "read")}
        className={selectClass}
        aria-label="Filter by read status"
      >
        {READ_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
