import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ProjectList, { type ProjectListHandle } from "@/components/projects/ProjectList";
import ProjectDetail from "@/components/projects/ProjectDetail";
import {
  selectOrphans,
  selectProject,
  useProjectsStore,
} from "@/stores/projects-store";

export default function ProjectsPage() {
  const { refCode } = useParams<{ refCode?: string }>();
  const loadAll = useProjectsStore((s) => s.loadAll);
  const loading = useProjectsStore((s) => s.loading);
  const loaded = useProjectsStore((s) => s.loaded);
  const error = useProjectsStore((s) => s.error);
  const orphanCount = useProjectsStore((s) => selectOrphans(s).length);
  const project = useProjectsStore((s) =>
    refCode ? selectProject(s, refCode) : undefined,
  );
  const summary = useProjectsStore((s) => s.summary);
  const entries = useProjectsStore((s) => s.entries);
  const listRef = useRef<ProjectListHandle>(null);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Global "/" focuses the project filter input
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/") return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      e.preventDefault();
      listRef.current?.focusFilter();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Default-select first active project if nothing in URL
  const effectiveProject = (() => {
    if (project) return project;
    if (refCode) return undefined;
    const first = summary.find((p) => p.status === "active") ?? summary[0];
    return first ? entries[`projects:${first.ref_code}`] : undefined;
  })();

  return (
    <div
      className="projects-scope"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        position: "relative",
      }}
      data-test="projects-page"
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 16px",
          borderBottom: "1px solid var(--p-border)",
          background: "var(--bg-sunk)",
          flex: "none",
          position: "relative",
          zIndex: 2,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a
            href="/"
            style={{
              fontFamily: "var(--p-mono)",
              fontSize: 11,
              color: "var(--text-dim)",
              textDecoration: "none",
            }}
          >
            &lt; CHAT
          </a>
          <span style={{ width: 1, height: 18, background: "var(--p-border)" }} />
          <span
            style={{
              fontFamily: "var(--pixel)",
              fontSize: 18,
              color: "var(--sunset)",
              textShadow:
                "0 0 10px color-mix(in oklch, var(--sunset) 60%, transparent)",
              letterSpacing: "0.05em",
            }}
          >
            PROJECTS
          </span>
          {orphanCount > 0 && (
            <span
              style={{
                fontFamily: "var(--p-mono)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.12em",
                color: "var(--magenta)",
                padding: "2px 6px",
                borderRadius: 3,
                background:
                  "color-mix(in oklch, var(--magenta) 12%, transparent)",
                border:
                  "1px solid color-mix(in oklch, var(--magenta) 36%, transparent)",
              }}
              title="Entries whose parent ref_code points at a missing project or milestone"
              data-test="projects-orphan-badge"
            >
              {orphanCount} ORPHAN{orphanCount === 1 ? "" : "S"}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: "8px 16px",
            background: "color-mix(in oklch, var(--magenta) 10%, transparent)",
            borderBottom:
              "1px solid color-mix(in oklch, var(--magenta) 40%, transparent)",
            fontFamily: "var(--p-mono)",
            fontSize: 11,
            color: "var(--magenta)",
          }}
        >
          {error}
        </div>
      )}

      <div style={{ flex: 1, overflow: "hidden", position: "relative", zIndex: 2 }}>
        {!loaded && loading ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              fontFamily: "var(--p-mono)",
              fontSize: 12,
              color: "var(--text-dim)",
            }}
          >
            Loading projects…
          </div>
        ) : (
          <PanelGroup direction="horizontal">
            <Panel defaultSize={25} minSize={18} maxSize={40}>
              <ProjectList ref={listRef} />
            </Panel>
            <PanelResizeHandle style={{ width: 1, background: "var(--p-border)" }} />
            <Panel defaultSize={75}>
              {effectiveProject ? (
                <ProjectDetail
                  project={effectiveProject}
                  onRefresh={() => loadAll()}
                  refreshing={loading}
                />
              ) : (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: "100%",
                    fontFamily: "var(--p-mono)",
                    fontSize: 12,
                    color: "var(--text-dim)",
                  }}
                >
                  {refCode
                    ? `No project ${refCode}.`
                    : "Select a project from the list."}
                </div>
              )}
            </Panel>
          </PanelGroup>
        )}
      </div>
    </div>
  );
}
