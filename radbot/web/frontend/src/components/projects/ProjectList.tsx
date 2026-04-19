import { useMemo, useState, forwardRef, useRef, useImperativeHandle } from "react";
import { Link, useParams } from "react-router-dom";
import { useShallow } from "zustand/shallow";
import type { ProjectSummary } from "@/lib/telos-api";
import { useProjectsStore } from "@/stores/projects-store";
import PIcon from "./shared/PIcon";
import RefCode from "./shared/RefCode";
import ProgressBar from "./shared/ProgressBar";
import { accentFor } from "./shared/projectAccent";

export type ProjectListHandle = {
  focusFilter: () => void;
};

const ProjectList = forwardRef<ProjectListHandle>(function ProjectList(_, ref) {
  const summary = useProjectsStore((s) => s.summary);
  const { refCode } = useParams<{ refCode?: string }>();
  const [q, setQ] = useState("");
  const [showArchived, setShowArchived] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(ref, () => ({
    focusFilter: () => inputRef.current?.focus(),
  }));

  const { active, archived } = useMemo(() => {
    const a: ProjectSummary[] = [];
    const arch: ProjectSummary[] = [];
    for (const p of summary) {
      if (p.status === "archived") arch.push(p);
      else a.push(p);
    }
    return { active: a, archived: arch };
  }, [summary]);

  const filt = (list: ProjectSummary[]) => {
    const s = q.trim().toLowerCase();
    if (!s) return list;
    return list.filter((p) =>
      `${p.ref_code} ${p.title}`.toLowerCase().includes(s),
    );
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "var(--bg-sunk)",
        borderRight: "1px solid var(--p-border)",
      }}
      data-test="projects-list"
    >
      <div
        style={{
          padding: "10px 12px 8px",
          borderBottom: "1px solid var(--border-soft)",
          background: "var(--bg-sunk)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 10px",
            background: "var(--surface)",
            border: "1px solid var(--p-border)",
            borderRadius: 6,
          }}
        >
          <span style={{ color: "var(--text-dim)", display: "inline-flex" }}>
            <PIcon name="search" size={12} />
          </span>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="filter projects…"
            style={{
              flex: 1,
              fontFamily: "var(--p-mono)",
              fontSize: 11,
              color: "var(--text)",
            }}
            data-test="projects-filter"
          />
          <span className="kbd">/</span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        <div
          style={{
            padding: "8px 12px 4px",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span
            style={{
              fontFamily: "var(--p-mono)",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.16em",
              color: "var(--text-dim)",
            }}
          >
            ACTIVE · {active.length}
          </span>
          <span style={{ flex: 1, height: 1, background: "var(--border-soft)" }} />
        </div>

        {filt(active).map((p) => (
          <ProjectListItem
            key={p.ref_code}
            p={p}
            active={p.ref_code === refCode}
          />
        ))}

        {archived.length > 0 && (
          <>
            <button
              onClick={() => setShowArchived((v) => !v)}
              style={{
                padding: "12px 12px 4px",
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 8,
                textAlign: "left",
              }}
            >
              <span
                style={{
                  transition: "transform 120ms",
                  transform: `rotate(${showArchived ? 90 : 0}deg)`,
                  display: "inline-flex",
                  color: "var(--text-dim)",
                }}
              >
                <PIcon name="chev" size={10} />
              </span>
              <span
                style={{
                  fontFamily: "var(--p-mono)",
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "0.16em",
                  color: "var(--text-dim)",
                }}
              >
                ARCHIVED · {archived.length}
              </span>
              <span style={{ flex: 1, height: 1, background: "var(--border-soft)" }} />
            </button>
            {showArchived &&
              filt(archived).map((p) => (
                <ProjectListItem
                  key={p.ref_code}
                  p={p}
                  active={p.ref_code === refCode}
                />
              ))}
          </>
        )}

        {active.length === 0 && archived.length === 0 && (
          <div
            style={{
              padding: 16,
              fontFamily: "var(--p-mono)",
              fontSize: 11,
              color: "var(--text-dim)",
            }}
          >
            No projects yet.
          </div>
        )}
      </div>

      <ListFooter activeCount={active.length} />
    </div>
  );
});

export default ProjectList;

function ProjectListItem({ p, active }: { p: ProjectSummary; active: boolean }) {
  const accent = accentFor(p.ref_code);
  const total = p.active_task_count + p.done_task_count;
  const pct = total === 0 ? 0 : Math.round((p.done_task_count / total) * 100);

  return (
    <Link
      to={`/projects/${encodeURIComponent(p.ref_code)}`}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 3,
        padding: "11px 12px",
        borderBottom: "1px solid var(--border-soft)",
        background: active
          ? `linear-gradient(90deg, color-mix(in oklch, ${accent} 10%, transparent), transparent 60%)`
          : "transparent",
        borderLeft: active ? `2px solid ${accent}` : "2px solid transparent",
        color: "inherit",
        textDecoration: "none",
      }}
      data-test={`projects-list-item-${p.ref_code}`}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <RefCode code={p.ref_code} color={accent} />
        {p.status === "archived" && (
          <span
            style={{
              fontFamily: "var(--p-mono)",
              fontSize: 8,
              fontWeight: 700,
              letterSpacing: "0.12em",
              color: "var(--text-dim)",
              padding: "1px 4px",
              borderRadius: 2,
              border: "1px solid var(--border-soft)",
            }}
          >
            ARCHIVED
          </span>
        )}
        <span style={{ flex: 1 }} />
        {p.updated_at && (
          <span
            style={{
              fontFamily: "var(--p-mono)",
              fontSize: 9,
              color: "var(--text-dim)",
            }}
          >
            {formatRelative(p.updated_at)}
          </span>
        )}
      </div>

      <div
        style={{
          fontFamily: "var(--sans)",
          fontSize: 13,
          fontWeight: 600,
          color: "var(--text)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {p.title}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 3,
          fontFamily: "var(--p-mono)",
          fontSize: 10,
          color: "var(--text-dim)",
        }}
      >
        <span>
          {p.done_task_count}/{total} tasks
        </span>
        {p.milestone_count > 0 && (
          <>
            <span>·</span>
            <span>{p.milestone_count} ms</span>
          </>
        )}
        <span style={{ flex: 1 }} />
        {total > 0 && <span style={{ color: accent }}>{pct}%</span>}
      </div>

      {total > 0 && (
        <div style={{ marginTop: 2 }}>
          <ProgressBar pct={pct} color={accent} height={2} />
        </div>
      )}
    </Link>
  );
}

function ListFooter({ activeCount }: { activeCount: number }) {
  const openTasks = useProjectsStore(
    useShallow((s) => {
      let n = 0;
      for (const e of Object.values(s.entries)) {
        if (e.section !== "project_tasks") continue;
        const status = ((e.metadata || {}).task_status || "").toString().toLowerCase();
        if (status !== "done" && status !== "complete" && status !== "completed") n++;
      }
      return n;
    }),
  );
  return (
    <div
      style={{
        padding: "8px 12px",
        borderTop: "1px solid var(--border-soft)",
        fontFamily: "var(--p-mono)",
        fontSize: 10,
        color: "var(--text-dim)",
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "var(--crt)",
          boxShadow: "0 0 6px var(--crt)",
        }}
      />
      <span>
        {activeCount} live · {openTasks} open tasks
      </span>
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
