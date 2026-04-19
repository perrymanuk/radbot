import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  bucketTasks,
  selectExplorationsForProject,
  selectGoalsForProject,
  selectMilestonesForProject,
  selectTasksForMilestone,
  selectTasksForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import PIcon from "./shared/PIcon";
import RefCode from "./shared/RefCode";
import ProgressBar from "./shared/ProgressBar";
import StatusIcon from "./shared/StatusIcon";
import { Legend, SectionLabel } from "./shared/Misc";
import { taskBucket } from "./shared/TaskLine";
import { accentFor } from "./shared/projectAccent";

interface Props {
  project: TelosEntry;
}

export default function OverviewTab({ project }: Props) {
  const accent = accentFor(project.ref_code || "");
  const openTaskEditor = useProjectsStore((s) => s.openTaskEditor);
  const tasks = useProjectsStore(
    useShallow((s) => selectTasksForProject(s, project.ref_code!)),
  );
  const milestones = useProjectsStore(
    useShallow((s) => selectMilestonesForProject(s, project.ref_code!)),
  );
  const goals = useProjectsStore(
    useShallow((s) => selectGoalsForProject(s, project.ref_code!)),
  );
  const explorations = useProjectsStore(
    useShallow((s) => selectExplorationsForProject(s, project.ref_code!)),
  );

  const b = bucketTasks(tasks);
  const total = tasks.length;
  const pct = total === 0 ? 0 : Math.round((b.done.length / total) * 100);
  const recent = [...tasks]
    .sort((a, z) => (z.updated_at || "").localeCompare(a.updated_at || ""))
    .slice(0, 5);

  return (
    <div
      style={{
        padding: "18px 22px",
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)",
        gap: 20,
      }}
      data-test="projects-overview-tab"
    >
      {/* Left column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20, minWidth: 0 }}>
        <div>
          <SectionLabel>README</SectionLabel>
          <div
            style={{
              padding: "14px 16px",
              borderRadius: 8,
              background: "var(--surface)",
              border: "1px solid var(--border-soft)",
              fontFamily: "var(--sans)",
              fontSize: 14,
              lineHeight: 1.65,
              color: "var(--text)",
              whiteSpace: "pre-wrap",
            }}
          >
            {(project.content || "").split("\n").map((line, i) => {
              if (line.startsWith("# "))
                return (
                  <h2
                    key={i}
                    style={{
                      margin: "0 0 8px",
                      fontSize: 18,
                      fontWeight: 700,
                      color: "var(--text)",
                    }}
                  >
                    {line.slice(2)}
                  </h2>
                );
              if (line.startsWith("## "))
                return (
                  <h3
                    key={i}
                    style={{
                      margin: "10px 0 6px",
                      fontSize: 15,
                      fontWeight: 700,
                      color: "var(--text)",
                    }}
                  >
                    {line.slice(3)}
                  </h3>
                );
              return (
                <div
                  key={i}
                  style={{
                    marginBottom: line ? 6 : 0,
                    color: "var(--text-mute)",
                  }}
                >
                  {line}
                </div>
              );
            })}
          </div>
        </div>

        {goals.length > 0 && (
          <div>
            <SectionLabel color="var(--sky)">GOALS · {goals.length}</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {goals.map((g) => (
                <div
                  key={g.entry_id}
                  style={{
                    padding: "12px 14px",
                    borderRadius: 7,
                    background: "color-mix(in oklch, var(--sky) 8%, var(--surface))",
                    border: "1px solid color-mix(in oklch, var(--sky) 30%, var(--p-border))",
                    borderLeft: "3px solid var(--sky)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      marginBottom: 4,
                    }}
                  >
                    <span style={{ color: "var(--sky)", display: "inline-flex" }}>
                      <PIcon name="target" size={13} />
                    </span>
                    <RefCode code={g.ref_code || ""} color="var(--sky)" />
                    <span
                      style={{
                        fontFamily: "var(--sans)",
                        fontSize: 14,
                        fontWeight: 600,
                        color: "var(--text)",
                      }}
                    >
                      {(g.content || "").split("\n")[0]}
                    </span>
                  </div>
                  {(g.content || "").split("\n").slice(1).join("\n").trim() && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--text-mute)",
                        lineHeight: 1.5,
                      }}
                    >
                      {(g.content || "").split("\n").slice(1).join("\n").trim()}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {recent.length > 0 && (
          <div>
            <SectionLabel>RECENT ACTIVITY</SectionLabel>
            <div
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border-soft)",
                borderRadius: 7,
                overflow: "hidden",
              }}
            >
              {recent.map((t) => {
                const bucket = taskBucket(t);
                const title = (t.content || "").split("\n")[0];
                const clickable = !!t.ref_code;
                const onClick = clickable
                  ? () => openTaskEditor(t.ref_code!)
                  : undefined;
                return (
                  <div
                    key={t.entry_id}
                    role={clickable ? "button" : undefined}
                    tabIndex={clickable ? 0 : undefined}
                    onClick={onClick}
                    onKeyDown={
                      clickable
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              onClick?.();
                            }
                          }
                        : undefined
                    }
                    data-test={`projects-overview-recent-${t.ref_code}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "10px 14px",
                      borderBottom: "1px solid var(--border-soft)",
                      cursor: clickable ? "pointer" : "default",
                      transition: "background 120ms",
                    }}
                    onMouseEnter={(e) => {
                      if (clickable)
                        e.currentTarget.style.background =
                          "color-mix(in oklch, var(--text) 4%, transparent)";
                    }}
                    onMouseLeave={(e) => {
                      if (clickable) e.currentTarget.style.background = "";
                    }}
                  >
                    <StatusIcon status={bucket} />
                    <RefCode code={t.ref_code || ""} color={accent} />
                    <span
                      style={{
                        flex: 1,
                        fontSize: 13,
                        color: "var(--text)",
                        minWidth: 0,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        textDecoration: bucket === "done" ? "line-through" : "none",
                        opacity: bucket === "done" ? 0.6 : 1,
                      }}
                    >
                      {title}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Right column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 0 }}>
        <div
          style={{
            padding: "14px 16px",
            borderRadius: 8,
            background: "var(--surface-2)",
            border: "1px solid var(--p-border)",
          }}
        >
          <SectionLabel color={accent}>PROGRESS</SectionLabel>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
            <span
              style={{
                fontFamily: "var(--pixel)",
                fontSize: 36,
                color: accent,
                textShadow: `0 0 14px color-mix(in oklch, ${accent} 60%, transparent)`,
                lineHeight: 1,
              }}
            >
              {pct}%
            </span>
            <span
              style={{
                fontFamily: "var(--p-mono)",
                fontSize: 11,
                color: "var(--text-mute)",
              }}
            >
              {b.done.length}/{total} tasks done
            </span>
          </div>
          <ProgressBar pct={pct} color={accent} height={6} />
          <div
            style={{
              display: "flex",
              gap: 10,
              marginTop: 12,
              fontFamily: "var(--p-mono)",
              fontSize: 10,
              color: "var(--text-dim)",
              flexWrap: "wrap",
            }}
          >
            <Legend color="var(--sunset)" label={`${b.inprogress.length} in progress`} />
            <Legend color="var(--sky)" label={`${b.backlog.length} backlog`} />
            <Legend color="var(--crt)" label={`${b.done.length} done`} />
          </div>
        </div>

        {milestones.length > 0 && (
          <MilestonePreview milestones={milestones} />
        )}

        {explorations.length > 0 && (
          <div>
            <SectionLabel color="var(--magenta)">
              EXPLORATIONS · {explorations.length}
            </SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {explorations.slice(0, 2).map((e) => (
                <div
                  key={e.entry_id}
                  style={{
                    padding: "9px 12px",
                    borderRadius: 6,
                    background: "color-mix(in oklch, var(--magenta) 6%, var(--surface))",
                    border: "1px dashed color-mix(in oklch, var(--magenta) 32%, var(--p-border))",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      marginBottom: 3,
                    }}
                  >
                    <span style={{ color: "var(--magenta)", display: "inline-flex" }}>
                      <PIcon name="flask" size={12} />
                    </span>
                    <RefCode code={e.ref_code || ""} color="var(--magenta)" />
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: "var(--text)",
                      marginBottom: 3,
                    }}
                  >
                    {(e.content || "").split("\n")[0]}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MilestonePreview({ milestones }: { milestones: TelosEntry[] }) {
  return (
    <div>
      <SectionLabel color="var(--violet)">
        NEXT MILESTONES · {milestones.length}
      </SectionLabel>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {milestones.slice(0, 3).map((m) => (
          <MilestoneRow key={m.entry_id} milestone={m} />
        ))}
      </div>
    </div>
  );
}

function MilestoneRow({ milestone }: { milestone: TelosEntry }) {
  const tasks = useProjectsStore(
    useShallow((s) => selectTasksForMilestone(s, milestone.ref_code!)),
  );
  const b = bucketTasks(tasks);
  const pct = tasks.length ? Math.round((b.done.length / tasks.length) * 100) : 0;
  const title = (milestone.content || "").split("\n")[0];

  return (
    <div
      style={{
        padding: "10px 12px",
        borderRadius: 6,
        background: "var(--surface)",
        border: "1px solid var(--border-soft)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: 5,
        }}
      >
        <RefCode code={milestone.ref_code || ""} color="var(--violet)" />
        <span
          style={{
            fontSize: 12,
            color: "var(--text)",
            flex: 1,
            minWidth: 0,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {title}
        </span>
        <span
          style={{
            fontFamily: "var(--p-mono)",
            fontSize: 10,
            color: "var(--text-mute)",
          }}
        >
          {pct}%
        </span>
      </div>
      <ProgressBar pct={pct} color="var(--violet)" height={3} />
    </div>
  );
}
