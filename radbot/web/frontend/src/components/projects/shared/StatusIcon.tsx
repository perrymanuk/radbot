import PIcon from "./PIcon";

export type TaskStatus = "inprogress" | "backlog" | "done" | "other";

export function StatusDot({ status, size = 6 }: { status: TaskStatus; size?: number }) {
  const c =
    status === "inprogress"
      ? "var(--sunset)"
      : status === "done"
      ? "var(--crt)"
      : status === "backlog"
      ? "var(--sky)"
      : "var(--text-dim)";
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: c,
        boxShadow: status === "inprogress" ? `0 0 6px ${c}` : "none",
        flex: "none",
      }}
    />
  );
}

export default function StatusIcon({ status }: { status: TaskStatus }) {
  if (status === "inprogress")
    return (
      <span style={{ color: "var(--sunset)", display: "inline-flex" }}>
        <PIcon name="half" />
      </span>
    );
  if (status === "done")
    return (
      <span style={{ color: "var(--crt)", display: "inline-flex" }}>
        <PIcon name="check" />
      </span>
    );
  return (
    <span style={{ color: "var(--text-dim)", display: "inline-flex" }}>
      <PIcon name="circle" />
    </span>
  );
}
