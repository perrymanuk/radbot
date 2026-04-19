import { useShallow } from "zustand/shallow";
import type { TelosEntry } from "@/lib/telos-api";
import {
  bucketTasks,
  selectMilestonesForProject,
  selectTasksForProject,
  useProjectsStore,
} from "@/stores/projects-store";
import PIcon from "./shared/PIcon";
import RefCode from "./shared/RefCode";
import ProgressBar from "./shared/ProgressBar";
import { MiniStat } from "./shared/Misc";
import { accentFor } from "./shared/projectAccent";

interface Props {
  project: TelosEntry;
  onRefresh: () => void;
  refreshing: boolean;
}

export default function DetailHeader({ project, onRefresh, refreshing }: Props) {
  const accent = accentFor(project.ref_code || "");
  const stats = useProjectsStore(
    useShallow((s) => {
      const tasks = selectTasksForProject(s, project.ref_code!);
      const milestones = selectMilestonesForProject(s, project.ref_code!);
      const b = bucketTasks(tasks);
      const total = tasks.length;
      return {
        total,
        done: b.done.length,
        inprogress: b.inprogress.length,
        backlog: b.backlog.length,
        milestones: milestones.length,
        pct: total === 0 ? 0 : Math.round((b.done.length / total) * 100),
      };
    }),
  );

  const lines = (project.content || "").split("\n");
  const title = lines[0] || project.ref_code || "";
  const subtitle = lines[1] && !lines[1].startsWith("#") ? lines[1].trim() : "";
  const url = (project.metadata || {}).url as string | undefined;
  const updated = project.updated_at ? formatRelative(project.updated_at) : null;

  return (
    <div
      className="projects-detail-header"
      style={{
        padding: "14px 20px 0",
        borderBottom: "1px solid var(--p-border)",
        background: `linear-gradient(180deg, color-mix(in oklch, ${accent} 10%, var(--surface-2)), var(--surface))`,
        position: "relative",
        flex: "none",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 12,
          marginBottom: 10,
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            flex: "none",
            borderRadius: 8,
            background: `color-mix(in oklch, ${accent} 20%, var(--surface))`,
            border: `1px solid color-mix(in oklch, ${accent} 50%, transparent)`,
            color: accent,
            display: "grid",
            placeItems: "center",
            boxShadow: `0 0 16px -4px ${accent}`,
          }}
        >
          <PIcon name="folder" size={18} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
            <RefCode code={project.ref_code || ""} color={accent} />
            <span
              style={{
                fontFamily: "var(--p-mono)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.14em",
                color: project.status === "active" ? "var(--crt)" : "var(--text-dim)",
              }}
            >
              {project.status.toUpperCase()}
            </span>
            {updated && (
              <span
                style={{
                  fontFamily: "var(--p-mono)",
                  fontSize: 10,
                  color: "var(--text-dim)",
                }}
              >
                updated {updated} ago
              </span>
            )}
          </div>

          <h1
            style={{
              margin: 0,
              fontFamily: "var(--sans)",
              fontSize: 22,
              fontWeight: 700,
              color: "var(--text)",
              lineHeight: 1.15,
            }}
          >
            {title}
            {subtitle && (
              <span style={{ color: "var(--text-mute)", fontWeight: 500 }}> {subtitle}</span>
            )}
          </h1>

          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                marginTop: 4,
                fontFamily: "var(--p-mono)",
                fontSize: 11,
                color: "var(--text-mute)",
              }}
            >
              <PIcon name="git" size={12} />
              <span>{url.replace(/^https?:\/\//, "")}</span>
            </a>
          )}
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={onRefresh}
            disabled={refreshing}
            style={{
              padding: "6px 10px",
              borderRadius: 5,
              fontFamily: "var(--p-mono)",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.08em",
              color: "var(--text-mute)",
              border: "1px solid var(--p-border)",
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              opacity: refreshing ? 0.5 : 1,
            }}
            data-test="projects-refresh"
          >
            <PIcon name="refresh" size={11} />
            REFRESH
          </button>
        </div>
      </div>

      <div
        className="projects-detail-stats"
        style={{
          display: "flex",
          gap: 16,
          marginBottom: 10,
          fontFamily: "var(--p-mono)",
          fontSize: 11,
          color: "var(--text-mute)",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <MiniStat label="TASKS" value={`${stats.done}/${stats.total}`} color={accent} />
        <MiniStat label="IN PROGRESS" value={stats.inprogress} color="var(--sunset)" />
        <MiniStat label="BACKLOG" value={stats.backlog} color="var(--sky)" />
        <MiniStat label="DONE" value={stats.done} color="var(--crt)" />
        <MiniStat label="MILESTONES" value={stats.milestones} color="var(--violet)" />
        <div style={{ flex: 1, minWidth: 80 }} />
        <div
          className="projects-detail-completion"
          style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 180 }}
        >
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--text-dim)",
            }}
          >
            COMPLETION
          </span>
          <div style={{ flex: 1, minWidth: 80 }}>
            <ProgressBar pct={stats.pct} color={accent} height={4} />
          </div>
          <span
            style={{
              fontFamily: "var(--p-mono)",
              fontSize: 11,
              fontWeight: 600,
              color: accent,
            }}
          >
            {stats.pct}%
          </span>
        </div>
      </div>
    </div>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (!then) return "";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo`;
  return `${Math.floor(months / 12)}y`;
}
