import { useState } from "react";
import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  bucketTasks,
  selectMilestonesForProject,
  selectTasksForMilestone,
  selectUnmilestonedTasks,
  useProjectsStore,
} from "@/stores/projects-store";
import PIcon from "./shared/PIcon";
import RefCode from "./shared/RefCode";
import ProgressBar from "./shared/ProgressBar";
import TaskLine from "./shared/TaskLine";
import { accentFor } from "./shared/projectAccent";

interface Props {
  project: TelosEntry;
}

export default function MilestonesTab({ project }: Props) {
  const accent = accentFor(project.ref_code || "");
  const milestones = useProjectsStore(
    useShallow((s) => selectMilestonesForProject(s, project.ref_code!)),
  );
  const unmilestoned = useProjectsStore(
    useShallow((s) => selectUnmilestonedTasks(s, project.ref_code!)),
  );
  const openTaskEditor = useProjectsStore((s) => s.openTaskEditor);

  return (
    <div
      className="projects-milestones-tab"
      style={{
        padding: "18px 22px",
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
      data-test="projects-milestones-tab"
    >
      {milestones.length === 0 && unmilestoned.length === 0 && (
        <div
          style={{
            padding: 30,
            textAlign: "center",
            fontFamily: "var(--p-mono)",
            fontSize: 12,
            color: "var(--text-dim)",
            border: "1px dashed var(--p-border)",
            borderRadius: 8,
          }}
        >
          No milestones yet — add one to start grouping tasks.
        </div>
      )}

      {milestones.map((m) => (
        <MilestoneCard key={m.entry_id} milestone={m} accent={accent} />
      ))}

      {unmilestoned.length > 0 && (
        <div
          style={{
            borderRadius: 8,
            overflow: "hidden",
            background: "color-mix(in oklch, var(--amber) 5%, var(--surface))",
            border: "1px solid color-mix(in oklch, var(--amber) 38%, var(--p-border))",
          }}
          data-test="projects-unmilestoned"
        >
          <div
            style={{
              padding: "10px 14px",
              display: "flex",
              alignItems: "center",
              gap: 8,
              borderBottom: "1px solid color-mix(in oklch, var(--amber) 25%, var(--p-border))",
            }}
          >
            <span style={{ color: "var(--amber)" }}>⚠</span>
            <span
              style={{
                fontFamily: "var(--p-mono)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.16em",
                color: "var(--amber)",
              }}
            >
              UNMILESTONED
            </span>
            <span style={{ flex: 1 }} />
            <span
              style={{
                fontFamily: "var(--p-mono)",
                fontSize: 10,
                color: "var(--text-mute)",
              }}
            >
              {unmilestoned.length} task{unmilestoned.length === 1 ? "" : "s"} need triage
            </span>
          </div>
          {unmilestoned.map((t) => (
            <TaskLine key={t.entry_id} task={t} accent={accent} onClick={openTaskEditor} />
          ))}
        </div>
      )}
    </div>
  );
}

function MilestoneCard({
  milestone,
  accent,
}: {
  milestone: TelosEntry;
  accent: string;
}) {
  const [open, setOpen] = useState(true);
  const tasks = useProjectsStore(
    useShallow((s) => selectTasksForMilestone(s, milestone.ref_code!)),
  );
  const b = bucketTasks(tasks);
  const total = tasks.length;
  const pct = total ? Math.round((b.done.length / total) * 100) : 0;
  const title = (milestone.content || "").split("\n")[0];
  const target = (milestone.metadata || {}).target as string | undefined;

  return (
    <div
      style={{
        borderRadius: 8,
        overflow: "hidden",
        background: "var(--surface)",
        border: "1px solid var(--p-border)",
        borderLeft: "3px solid var(--violet)",
      }}
      data-test={`projects-milestone-${milestone.ref_code}`}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "11px 14px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: `color-mix(in oklch, var(--violet) 6%, transparent)`,
          borderBottom: open ? "1px solid var(--border-soft)" : "none",
        }}
      >
        <span
          style={{
            color: "var(--text-dim)",
            transition: "transform 120ms",
            transform: `rotate(${open ? 90 : 0}deg)`,
            display: "inline-flex",
          }}
        >
          <PIcon name="chev" size={12} />
        </span>
        <span style={{ color: "var(--violet)", display: "inline-flex" }}>
          <PIcon name="flag" size={13} />
        </span>
        <RefCode code={milestone.ref_code || ""} color="var(--violet)" />
        <span
          style={{
            flex: 1,
            fontFamily: "var(--sans)",
            fontSize: 14,
            fontWeight: 600,
            color: "var(--text)",
            minWidth: 0,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {title}
        </span>
        {target && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontFamily: "var(--p-mono)",
              fontSize: 10,
              color: "var(--text-dim)",
            }}
          >
            <PIcon name="clock" size={10} />
            {target}
          </span>
        )}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            minWidth: 140,
          }}
        >
          <div style={{ width: 80 }}>
            <ProgressBar pct={pct} color="var(--violet)" height={3} />
          </div>
          <span
            style={{
              fontFamily: "var(--p-mono)",
              fontSize: 11,
              color: "var(--text)",
              fontWeight: 600,
              width: 56,
              textAlign: "right",
            }}
          >
            {b.done.length}/{total}
          </span>
        </span>
      </button>

      {open && total > 0 && (
        <div>
          <TaskGroup label="IN PROGRESS" tasks={b.inprogress} accent={accent} />
          <TaskGroup label="BACKLOG" tasks={b.backlog} accent={accent} />
          <TaskGroup label="OTHER" tasks={b.other} accent={accent} />
          <TaskGroup label="DONE" tasks={b.done} accent={accent} collapsedByDefault />
        </div>
      )}

      {open && total === 0 && (
        <div
          style={{
            padding: "10px 14px",
            fontFamily: "var(--p-mono)",
            fontSize: 11,
            color: "var(--text-dim)",
            fontStyle: "italic",
          }}
        >
          no tasks yet
        </div>
      )}

      {open &&
        milestone.content &&
        (milestone.content.split("\n").slice(1).join("\n").trim() !== "") && (
          <div
            style={{
              padding: "10px 14px",
              borderTop: "1px solid var(--border-soft)",
              fontSize: 12,
              color: "var(--text-mute)",
              lineHeight: 1.5,
              fontStyle: "italic",
            }}
          >
            {milestone.content.split("\n").slice(1).join("\n").trim()}
          </div>
        )}
    </div>
  );
}

function TaskGroup({
  label,
  tasks,
  accent,
  collapsedByDefault,
}: {
  label: string;
  tasks: TelosEntry[];
  accent: string;
  collapsedByDefault?: boolean;
}) {
  const [open, setOpen] = useState(!collapsedByDefault);
  const openTaskEditor = useProjectsStore((s) => s.openTaskEditor);
  if (tasks.length === 0) return null;
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "6px 14px",
          fontFamily: "var(--p-mono)",
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.16em",
          color: "var(--text-dim)",
          background: "var(--bg-sunk)",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          style={{
            transition: "transform 120ms",
            transform: `rotate(${open ? 90 : 0}deg)`,
            display: "inline-flex",
          }}
        >
          <PIcon name="chev" size={10} />
        </span>
        <span>
          {label} · {tasks.length}
        </span>
      </button>
      {open && tasks.map((t) => <TaskLine key={t.entry_id} task={t} accent={accent} onClick={openTaskEditor} />)}
    </div>
  );
}
