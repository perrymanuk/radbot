import PIcon from "./PIcon";

export type TaskStatus = "inprogress" | "backlog" | "done" | "other";

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
