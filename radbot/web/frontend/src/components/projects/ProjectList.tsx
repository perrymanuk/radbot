import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useProjectsStore } from "@/stores/projects-store";

export default function ProjectList() {
  const summary = useProjectsStore((s) => s.summary);
  const { refCode } = useParams<{ refCode?: string }>();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return summary;
    return summary.filter(
      (p) =>
        p.ref_code.toLowerCase().includes(q) ||
        p.title.toLowerCase().includes(q),
    );
  }, [summary, query]);

  return (
    <div
      className="flex flex-col h-full bg-bg-primary border-r border-border"
      data-test="projects-list"
    >
      <div className="px-3 py-2 bg-bg-tertiary border-b border-border">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter projects…"
          className={cn(
            "w-full bg-bg-primary border border-border rounded-sm px-2 py-1",
            "text-[0.75rem] font-mono text-txt-primary placeholder:text-txt-secondary",
            "focus:outline-none focus:border-accent-blue",
          )}
          data-test="projects-filter"
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="p-3 text-[0.7rem] font-mono text-txt-secondary">
            {summary.length === 0 ? "No projects yet." : "No matches."}
          </div>
        ) : (
          filtered.map((p) => {
            const active = p.ref_code === refCode;
            const completion =
              p.active_task_count + p.done_task_count === 0
                ? 0
                : Math.round(
                    (p.done_task_count /
                      (p.active_task_count + p.done_task_count)) *
                      100,
                  );
            return (
              <Link
                key={p.ref_code}
                to={`/projects/${encodeURIComponent(p.ref_code)}`}
                className={cn(
                  "block px-3 py-2 border-b border-border/40 no-underline",
                  "hover:bg-bg-tertiary transition-colors",
                  active && "bg-bg-tertiary border-l-2 border-l-accent-blue",
                )}
                data-test={`projects-list-item-${p.ref_code}`}
              >
                <div className="flex items-baseline gap-2">
                  <span className="text-[0.65rem] font-mono text-accent-blue uppercase tracking-wider">
                    {p.ref_code}
                  </span>
                  {p.status !== "active" && (
                    <span className="text-[0.6rem] font-mono text-txt-secondary uppercase">
                      {p.status}
                    </span>
                  )}
                </div>
                <div className="text-[0.8rem] font-mono text-txt-primary truncate">
                  {p.title}
                </div>
                <div className="flex items-center gap-2 mt-1 text-[0.65rem] font-mono text-txt-secondary">
                  <span>{p.milestone_count} ms</span>
                  <span>·</span>
                  <span>
                    {p.done_task_count}/
                    {p.active_task_count + p.done_task_count} tasks
                  </span>
                  {p.active_task_count + p.done_task_count > 0 && (
                    <span className="ml-auto text-accent-blue">{completion}%</span>
                  )}
                </div>
              </Link>
            );
          })
        )}
      </div>
    </div>
  );
}
