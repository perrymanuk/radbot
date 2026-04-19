import { useEffect, useState } from "react";
import { useAdminStore } from "@/stores/admin-store";
import * as adminApi from "@/lib/admin-api";
import type { McpProject, McpStatus } from "@/lib/admin-api";
import { Card, Note } from "@/components/admin/FormFields";

/** Admin panel for the MCP bridge: token management + project registry. */
export function McpBridgePanel() {
  const { token, toast } = useAdminStore();
  const [status, setStatus] = useState<McpStatus | null>(null);
  const [projects, setProjects] = useState<McpProject[]>([]);
  const [loading, setLoading] = useState(true);

  // Reveal / rotate modal state
  const [revealed, setRevealed] = useState<string | null>(null);
  const [revealKind, setRevealKind] = useState<"reveal" | "rotated" | null>(null);
  const [rotating, setRotating] = useState(false);

  const reload = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [s, p] = await Promise.all([
        adminApi.getMcpStatus(token),
        adminApi.listMcpProjects(token),
      ]);
      setStatus(s);
      setProjects(p);
    } catch (e: any) {
      toast(`MCP status load failed: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const handleReveal = async () => {
    if (!token) return;
    try {
      const r = await adminApi.revealMcpToken(token);
      setRevealed(r.token);
      setRevealKind("reveal");
    } catch (e: any) {
      toast(`Reveal failed: ${e.message}`, "error");
    }
  };

  const handleRotate = async () => {
    if (!token) return;
    if (!window.confirm(
      "Rotate MCP token? All clients using the old token will 401 until you re-copy " +
      "the new one into their shell profiles."
    )) return;
    setRotating(true);
    try {
      const r = await adminApi.rotateMcpToken(token);
      setRevealed(r.token);
      setRevealKind("rotated");
      await reload();
    } catch (e: any) {
      toast(`Rotate failed: ${e.message}`, "error");
    } finally {
      setRotating(false);
    }
  };

  const copyRevealed = () => {
    if (revealed) {
      navigator.clipboard.writeText(revealed);
      toast("Token copied", "success");
    }
  };

  const closeReveal = () => {
    setRevealed(null);
    setRevealKind(null);
  };

  return (
    <div className="space-y-6">
      <Card title="Status">
        {loading || !status ? (
          <div className="text-txt-secondary text-sm">Loading…</div>
        ) : (
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <dt className="text-txt-secondary">Auth configured</dt>
            <dd className={status.auth_configured ? "text-green-400" : "text-yellow-400"}>
              {status.auth_configured ? "yes" : "no — set RADBOT_MCP_TOKEN or rotate below"}
            </dd>
            <dt className="text-txt-secondary">Token source</dt>
            <dd>{status.token_source || "—"}</dd>
            <dt className="text-txt-secondary">Wiki path</dt>
            <dd>
              <code>{status.wiki_path}</code>{" "}
              <span className={status.wiki_mounted ? "text-green-400" : "text-red-400"}>
                ({status.wiki_mounted ? "mounted" : "not mounted"})
              </span>
            </dd>
            <dt className="text-txt-secondary">MCP SSE URL</dt>
            <dd><code>{status.sse_url}</code></dd>
            <dt className="text-txt-secondary">Setup URL</dt>
            <dd>
              <a href={status.setup_url} target="_blank" rel="noreferrer" className="text-blue-400 underline">
                {status.setup_url}
              </a>
            </dd>
          </dl>
        )}
      </Card>

      <Card title="Token">
        <Note>
          Token is managed via the <code>RADBOT_MCP_TOKEN</code> env var or the
          credential store (store wins over env). Rotating generates a new
          secure value in the store; you then copy it into each machine's
          shell profile.
        </Note>
        <div className="flex items-center gap-3 mt-3">
          <code className="text-sm bg-bg-secondary rounded px-2 py-1">
            {status?.token_masked || "(not set)"}
          </code>
          <button
            className="text-sm px-3 py-1 rounded bg-bg-secondary hover:bg-bg-tertiary"
            disabled={!status?.auth_configured}
            onClick={handleReveal}
          >
            Reveal
          </button>
          <button
            className="text-sm px-3 py-1 rounded bg-red-600 hover:bg-red-700 text-white"
            onClick={handleRotate}
            disabled={rotating}
          >
            {rotating ? "Rotating…" : "Rotate"}
          </button>
        </div>
      </Card>

      <Card title="Project registry">
        <Note>
          Registered projects are matched against <code>cwd</code> by the
          <code> SessionStart </code>hook. Each pattern is a substring test — any match
          returns this project. <code>wiki_path</code> (optional) is the wiki
          page whose contents load as session context.
        </Note>
        <ProjectTable
          projects={projects}
          onChange={reload}
          token={token}
        />
      </Card>

      {revealed !== null && (
        <RevealModal
          kind={revealKind}
          token={revealed}
          onCopy={copyRevealed}
          onClose={closeReveal}
        />
      )}
    </div>
  );
}

// ── Project editor table ──────────────────────────────────────

function ProjectTable({
  projects, onChange, token,
}: {
  projects: McpProject[];
  onChange: () => void | Promise<void>;
  token: string | null;
}) {
  const { toast } = useAdminStore();
  const [newName, setNewName] = useState("");
  const [newPatterns, setNewPatterns] = useState("");
  const [newWiki, setNewWiki] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const add = async () => {
    if (!token || !newName.trim()) return;
    setBusy("new");
    try {
      await adminApi.upsertMcpProject(token, {
        name: newName.trim(),
        path_patterns: newPatterns.split(",").map((s) => s.trim()).filter(Boolean),
        wiki_path: newWiki.trim() || null,
      });
      setNewName(""); setNewPatterns(""); setNewWiki("");
      await onChange();
      toast(`Added ${newName.trim()}`, "success");
    } catch (e: any) {
      toast(`Add failed: ${e.message}`, "error");
    } finally {
      setBusy(null);
    }
  };

  const del = async (name: string) => {
    if (!token) return;
    if (!window.confirm(`Delete project "${name}"?`)) return;
    setBusy(name);
    try {
      await adminApi.deleteMcpProject(token, name);
      await onChange();
      toast(`Deleted ${name}`, "success");
    } catch (e: any) {
      toast(`Delete failed: ${e.message}`, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mt-3 space-y-3">
      <table className="w-full text-sm">
        <thead className="text-txt-secondary text-left">
          <tr>
            <th className="py-1 pr-4">Name</th>
            <th className="py-1 pr-4">Path patterns</th>
            <th className="py-1 pr-4">Wiki path</th>
            <th className="py-1"></th>
          </tr>
        </thead>
        <tbody>
          {projects.map((p) => (
            <ProjectRow key={p.name} project={p} onChange={onChange} token={token} busy={busy === p.name} onDelete={() => del(p.name)} />
          ))}
          <tr className="border-t border-border">
            <td className="py-2 pr-4">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="radbot"
                className="bg-bg-secondary rounded px-2 py-1 w-full"
              />
            </td>
            <td className="py-2 pr-4">
              <input
                value={newPatterns}
                onChange={(e) => setNewPatterns(e.target.value)}
                placeholder="/git/me/radbot, /work/foo (comma-separated)"
                className="bg-bg-secondary rounded px-2 py-1 w-full"
              />
            </td>
            <td className="py-2 pr-4">
              <input
                value={newWiki}
                onChange={(e) => setNewWiki(e.target.value)}
                placeholder="wiki/concepts/radbot.md"
                className="bg-bg-secondary rounded px-2 py-1 w-full"
              />
            </td>
            <td className="py-2">
              <button
                className="text-sm px-3 py-1 rounded bg-bg-tertiary hover:bg-bg-secondary"
                onClick={add}
                disabled={busy === "new" || !newName.trim()}
              >
                {busy === "new" ? "Adding…" : "Add"}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ProjectRow({
  project, onChange, token, busy, onDelete,
}: {
  project: McpProject;
  onChange: () => void | Promise<void>;
  token: string | null;
  busy: boolean;
  onDelete: () => void;
}) {
  const { toast } = useAdminStore();
  const [patterns, setPatterns] = useState(project.path_patterns.join(", "));
  const [wiki, setWiki] = useState(project.wiki_path || "");
  const [editing, setEditing] = useState(false);

  const save = async () => {
    if (!token) return;
    try {
      await adminApi.upsertMcpProject(token, {
        name: project.name,
        path_patterns: patterns.split(",").map((s) => s.trim()).filter(Boolean),
        wiki_path: wiki.trim() || null,
      });
      setEditing(false);
      await onChange();
      toast(`Saved ${project.name}`, "success");
    } catch (e: any) {
      toast(`Save failed: ${e.message}`, "error");
    }
  };

  return (
    <tr className="border-t border-border">
      <td className="py-2 pr-4 font-medium">{project.name}</td>
      <td className="py-2 pr-4">
        {editing ? (
          <input
            value={patterns}
            onChange={(e) => setPatterns(e.target.value)}
            className="bg-bg-secondary rounded px-2 py-1 w-full"
          />
        ) : (
          <code className="text-xs">{patterns || "—"}</code>
        )}
      </td>
      <td className="py-2 pr-4">
        {editing ? (
          <input
            value={wiki}
            onChange={(e) => setWiki(e.target.value)}
            className="bg-bg-secondary rounded px-2 py-1 w-full"
          />
        ) : (
          <code className="text-xs">{wiki || "—"}</code>
        )}
      </td>
      <td className="py-2 flex gap-2 justify-end">
        {editing ? (
          <>
            <button className="text-sm px-2 py-1 rounded bg-green-700 text-white" onClick={save}>Save</button>
            <button className="text-sm px-2 py-1 rounded bg-bg-secondary" onClick={() => setEditing(false)}>Cancel</button>
          </>
        ) : (
          <>
            <button className="text-sm px-2 py-1 rounded bg-bg-tertiary hover:bg-bg-secondary" onClick={() => setEditing(true)}>Edit</button>
            <button className="text-sm px-2 py-1 rounded bg-red-700 text-white disabled:opacity-50" onClick={onDelete} disabled={busy}>Delete</button>
          </>
        )}
      </td>
    </tr>
  );
}

// ── Reveal / post-rotate modal ───────────────────────────────

function RevealModal({
  kind, token, onCopy, onClose,
}: {
  kind: "reveal" | "rotated" | null;
  token: string;
  onCopy: () => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 z-[1100] flex items-center justify-center">
      <div className="bg-bg-primary rounded-lg border border-border p-6 max-w-lg w-full space-y-4">
        <h2 className="text-lg font-medium">
          {kind === "rotated" ? "New MCP token" : "MCP token"}
        </h2>
        {kind === "rotated" && (
          <div className="text-sm bg-yellow-900/30 border border-yellow-700 rounded px-3 py-2">
            Rotation succeeded. Existing clients will 401 until you copy this
            token into each machine's shell profile (<code>RADBOT_MCP_TOKEN</code>).
            This token is shown <strong>once</strong> — copy it now.
          </div>
        )}
        <code className="block bg-bg-secondary rounded px-3 py-2 text-sm break-all">
          {token}
        </code>
        <div className="flex justify-end gap-2">
          <button
            className="text-sm px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700"
            onClick={onCopy}
          >
            Copy
          </button>
          <button
            className="text-sm px-3 py-1 rounded bg-bg-secondary hover:bg-bg-tertiary"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
