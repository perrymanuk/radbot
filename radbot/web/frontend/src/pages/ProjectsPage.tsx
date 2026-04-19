import { useEffect } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useParams } from "react-router-dom";
import ProjectList from "@/components/projects/ProjectList";
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

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  return (
    <div
      className="flex flex-col h-screen bg-bg-primary text-txt-primary"
      data-test="projects-page"
    >
      <div className="flex items-center justify-between px-4 py-2.5 bg-bg-tertiary border-b border-border flex-shrink-0">
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="text-[0.7rem] font-mono text-txt-secondary hover:text-txt-primary no-underline"
          >
            &lt; CHAT
          </a>
          <div className="w-px h-5 bg-border" />
          <h1 className="text-sm font-mono tracking-wider text-txt-secondary uppercase m-0">
            Projects
          </h1>
          {orphanCount > 0 && (
            <span
              className="text-[0.65rem] font-mono bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded border border-red-500/40"
              title="Entries whose parent ref_code points at a missing project or milestone"
              data-test="projects-orphan-badge"
            >
              {orphanCount} orphan{orphanCount === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <button
          onClick={() => loadAll()}
          disabled={loading}
          className="px-2.5 py-1 text-[0.7rem] font-mono uppercase tracking-wider text-txt-secondary hover:text-txt-primary disabled:opacity-40"
          data-test="projects-refresh"
        >
          {loading ? "…" : "refresh"}
        </button>
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/40 text-[0.75rem] font-mono text-red-400">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-hidden">
        {!loaded && loading ? (
          <div className="flex items-center justify-center h-full text-[0.8rem] font-mono text-txt-secondary animate-pulse">
            Loading projects…
          </div>
        ) : (
          <PanelGroup direction="horizontal">
            <Panel defaultSize={28} minSize={18} maxSize={40}>
              <ProjectList />
            </Panel>
            <PanelResizeHandle className="w-px bg-border hover:bg-accent-blue/40 transition-colors" />
            <Panel defaultSize={72}>
              {project ? (
                <ProjectDetail project={project} />
              ) : (
                <div className="flex items-center justify-center h-full text-[0.8rem] font-mono text-txt-secondary">
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
