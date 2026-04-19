import type { TelosEntry } from "@/lib/telos-api";
import RefCode from "./RefCode";
import StatusIcon, { type TaskStatus } from "./StatusIcon";

export function taskBucket(t: TelosEntry): TaskStatus {
  const raw = ((t.metadata || {}).task_status || "").toString().toLowerCase();
  if (raw === "inprogress" || raw === "in_progress" || raw === "in progress")
    return "inprogress";
  if (raw === "done" || raw === "complete" || raw === "completed") return "done";
  if (raw === "backlog" || raw === "todo" || raw === "pending" || raw === "")
    return "backlog";
  return "other";
}

interface Props {
  task: TelosEntry;
  accent: string;
}

export default function TaskLine({ task, accent }: Props) {
  const bucket = taskBucket(task);
  const lines = (task.content || "").split("\n");
  const title = lines[0] || task.ref_code || "";
  const note = lines.slice(1).join(" ").trim().slice(0, 200);
  const age = formatAge(task.updated_at);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "9px 14px",
        borderBottom: "1px solid var(--border-soft)",
      }}
      data-test={`projects-task-${task.ref_code}`}
    >
      <span style={{ paddingTop: 1 }}>
        <StatusIcon status={bucket} />
      </span>
      <RefCode code={task.ref_code || ""} color={accent} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            color: "var(--text)",
            lineHeight: 1.4,
            textDecoration: bucket === "done" ? "line-through" : "none",
            opacity: bucket === "done" ? 0.55 : 1,
          }}
        >
          {title}
        </div>
        {note && (
          <div
            style={{
              fontSize: 11,
              color: "var(--text-dim)",
              fontStyle: "italic",
              marginTop: 2,
              lineHeight: 1.45,
            }}
          >
            {note}
          </div>
        )}
      </div>
      {age && (
        <span
          style={{
            fontFamily: "var(--p-mono)",
            fontSize: 10,
            color: "var(--text-dim)",
            flex: "none",
          }}
        >
          {age}
        </span>
      )}
    </div>
  );
}

function formatAge(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (!then) return null;
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo`;
  return `${Math.floor(months / 12)}y`;
}
