/** Telos admin panel — wizard for first-time onboarding, editor after. */

import { useEffect, useMemo, useState } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { Card, Note, FormInput, FormTextarea } from "@/components/admin/FormFields";
import {
  TelosEntry,
  TelosStatus,
  telosAddEntry,
  telosArchive,
  telosBulk,
  telosExportMarkdown,
  telosGetSection,
  telosGetStatus,
  telosImportMarkdown,
  telosResolvePrediction,
  telosUpdateEntry,
  TelosBulkEntry,
} from "@/lib/admin-api";
import { cn } from "@/lib/utils";

// Section order + display metadata for the editor.
const SECTIONS: Array<{
  key: string;
  label: string;
  single?: boolean;
  prose?: boolean;
  hint?: string;
}> = [
  { key: "identity", label: "Identity", single: true, prose: true, hint: "Who you are — one entry only." },
  { key: "mission", label: "Mission", prose: true, hint: "What you want to put into the world." },
  { key: "problems", label: "Problems", hint: "Big things you're trying to solve." },
  { key: "narratives", label: "Narratives", hint: "How you describe yourself in a sentence or two." },
  { key: "goals", label: "Goals", hint: "Concrete targets (deadline / KPI optional in metadata)." },
  { key: "projects", label: "Projects", hint: "Current active work." },
  { key: "challenges", label: "Challenges", hint: "What's actively blocking you." },
  { key: "strategies", label: "Strategies", hint: "How you're tackling the problems." },
  { key: "wisdom", label: "Wisdom", hint: "Principles you live by." },
  { key: "ideas", label: "Ideas", hint: "Strong opinions / hot takes." },
  { key: "predictions", label: "Predictions" },
  { key: "wrong_about", label: "Wrong About", hint: "Things you got wrong — calibration history." },
  { key: "best_books", label: "Best Books" },
  { key: "best_movies", label: "Best Movies" },
  { key: "best_music", label: "Best Music" },
  { key: "taste", label: "Taste", hint: "Misc preferences (food, tools, games, …)." },
  { key: "history", label: "History", prose: true, hint: "Background that shapes how you think." },
  { key: "traumas", label: "Traumas", hint: "Sensitive — never auto-loaded; opt-in only." },
  { key: "metrics", label: "Metrics", hint: "Long-lived KPIs you track over time." },
  { key: "journal", label: "Recent Journal" },
];

// ── Top-level panel ─────────────────────────────────────────

export function TelosPanel() {
  const token = useAdminStore((s) => s.token);
  const toast = useAdminStore((s) => s.toast);
  const [status, setStatus] = useState<TelosStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = async () => {
    try {
      const s = await telosGetStatus(token);
      setStatus(s);
    } catch (e: any) {
      toast("Failed to load Telos: " + e.message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (loading) {
    return <div className="text-txt-secondary text-sm">Loading Telos…</div>;
  }
  if (!status) {
    return <div className="text-terminal-red text-sm">Could not reach Telos API.</div>;
  }

  return (
    <div>
      <h2 className="text-lg font-semibold mb-1">Telos</h2>
      <p className="text-txt-secondary text-sm mb-5">
        Persistent user-context store that beto reads every turn.
      </p>
      {status.has_identity ? (
        <TelosEditor onReset={reload} />
      ) : (
        <TelosWizard
          onComplete={async () => {
            await reload();
          }}
        />
      )}
    </div>
  );
}

// ── Wizard (first-run onboarding) ───────────────────────────

interface WizardData {
  // Identity
  name: string;
  location: string;
  role: string;
  pronouns: string;
  // Section lists: one item per line in each textarea
  problems: string;
  mission: string;
  goals: string;
  projects: string;
  challenges: string;
  wisdom: string;
  bestBook: string;
  bestMovie: string;
  bestMusic: string;
  history: string;
}

const EMPTY_WIZARD: WizardData = {
  name: "", location: "", role: "", pronouns: "",
  problems: "", mission: "", goals: "", projects: "",
  challenges: "", wisdom: "",
  bestBook: "", bestMovie: "", bestMusic: "",
  history: "",
};

function TelosWizard({ onComplete }: { onComplete: () => void | Promise<void> }) {
  const token = useAdminStore((s) => s.token);
  const toast = useAdminStore((s) => s.toast);
  const [step, setStep] = useState(0);
  const [data, setData] = useState<WizardData>(EMPTY_WIZARD);
  const [submitting, setSubmitting] = useState(false);

  const steps = [
    "Identity",
    "Problems",
    "Mission",
    "Goals",
    "Projects",
    "Challenges",
    "Wisdom",
    "Taste",
    "History",
  ];
  const total = steps.length;

  const canProceed = step !== 0 || data.name.trim().length > 0;

  const submit = async () => {
    if (!data.name.trim()) {
      toast("Name is required.", "error");
      setStep(0);
      return;
    }
    setSubmitting(true);
    try {
      const entries: TelosBulkEntry[] = [];

      // Identity (singleton, ref_code = ME)
      const identityBits = [data.name.trim()];
      if (data.location.trim()) identityBits.push(`based in ${data.location.trim()}`);
      if (data.role.trim()) identityBits.push(data.role.trim());
      entries.push({
        section: "identity",
        ref_code: "ME",
        content: identityBits.join(", "),
        metadata: {
          name: data.name.trim(),
          location: data.location.trim() || undefined,
          role: data.role.trim() || undefined,
          pronouns: data.pronouns.trim() || undefined,
        },
      });

      const addLines = (section: string, blob: string, prefix?: string) => {
        const lines = blob.split(/\n+/).map((l) => l.trim()).filter(Boolean);
        lines.forEach((content, i) => {
          entries.push({
            section,
            content,
            ref_code: prefix ? `${prefix}${i + 1}` : null,
            sort_order: i,
          });
        });
      };

      if (data.mission.trim()) {
        entries.push({ section: "mission", ref_code: "M1", content: data.mission.trim() });
      }
      addLines("problems", data.problems, "P");
      addLines("goals", data.goals, "G");
      addLines("projects", data.projects, "PRJ");
      addLines("challenges", data.challenges, "C");
      addLines("wisdom", data.wisdom);
      if (data.bestBook.trim()) {
        entries.push({
          section: "best_books",
          content: data.bestBook.trim(),
          metadata: { sentiment: "love" },
        });
      }
      if (data.bestMovie.trim()) {
        entries.push({
          section: "best_movies",
          content: data.bestMovie.trim(),
          metadata: { sentiment: "love" },
        });
      }
      if (data.bestMusic.trim()) {
        entries.push({
          section: "best_music",
          content: data.bestMusic.trim(),
          metadata: { sentiment: "love" },
        });
      }
      if (data.history.trim()) {
        entries.push({ section: "history", content: data.history.trim() });
      }

      await telosBulk(token, entries, false);
      toast(`Onboarded — saved ${entries.length} entries.`);
      await onComplete();
    } catch (e: any) {
      toast("Onboarding failed: " + e.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <Note>
        One-time setup (~5 min). Each step is optional except Identity — skip
        anything you'd rather let beto learn from conversations.
      </Note>

      <div className="flex items-center gap-2 mb-4 text-xs text-txt-secondary">
        <span className="font-mono">Step {step + 1}/{total}</span>
        <div className="flex-1 h-1 bg-bg-tertiary rounded-full overflow-hidden">
          <div
            className="h-full bg-radbot-sunset transition-all"
            style={{ width: `${((step + 1) / total) * 100}%` }}
          />
        </div>
        <span>{steps[step]}</span>
      </div>

      <Card title={steps[step]}>
        {step === 0 && (
          <>
            <FormInput label="Name" value={data.name} onChange={(v) => setData({ ...data, name: v })} hint="Required — commits the onboarding sentinel so beto stops asking." />
            <FormInput label="Location" value={data.location} onChange={(v) => setData({ ...data, location: v })} />
            <FormInput label="Role / occupation" value={data.role} onChange={(v) => setData({ ...data, role: v })} />
            <FormInput label="Pronouns (optional)" value={data.pronouns} onChange={(v) => setData({ ...data, pronouns: v })} />
          </>
        )}
        {step === 1 && (
          <FormTextarea label="Problems (one per line)" value={data.problems} onChange={(v) => setData({ ...data, problems: v })} placeholder="P1: ...\nP2: ..." />
        )}
        {step === 2 && (
          <FormTextarea label="Mission" value={data.mission} onChange={(v) => setData({ ...data, mission: v })} placeholder="What you want to put into the world." />
        )}
        {step === 3 && (
          <FormTextarea label="Goals (one per line)" value={data.goals} onChange={(v) => setData({ ...data, goals: v })} placeholder="Ship telos phase 2\nSleep 8h nightly" />
        )}
        {step === 4 && (
          <FormTextarea label="Projects (one per line)" value={data.projects} onChange={(v) => setData({ ...data, projects: v })} />
        )}
        {step === 5 && (
          <FormTextarea label="Challenges (one per line)" value={data.challenges} onChange={(v) => setData({ ...data, challenges: v })} />
        )}
        {step === 6 && (
          <FormTextarea label="Wisdom / principles (one per line)" value={data.wisdom} onChange={(v) => setData({ ...data, wisdom: v })} />
        )}
        {step === 7 && (
          <>
            <FormInput label="Best book" value={data.bestBook} onChange={(v) => setData({ ...data, bestBook: v })} />
            <FormInput label="Best movie" value={data.bestMovie} onChange={(v) => setData({ ...data, bestMovie: v })} />
            <FormInput label="Best music / album / artist" value={data.bestMusic} onChange={(v) => setData({ ...data, bestMusic: v })} />
          </>
        )}
        {step === 8 && (
          <FormTextarea label="History (optional prose)" value={data.history} onChange={(v) => setData({ ...data, history: v })} large placeholder="Anything about your background that shapes how you think." />
        )}
      </Card>

      <div className="flex items-center gap-2 mt-3">
        <button
          disabled={step === 0}
          onClick={() => setStep(step - 1)}
          className="px-3 py-2 border border-border rounded-md text-sm bg-bg-tertiary hover:border-radbot-sunset disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          Back
        </button>
        {step < total - 1 && (
          <button
            disabled={!canProceed}
            onClick={() => setStep(step + 1)}
            className="px-3 py-2 border border-border rounded-md text-sm bg-bg-tertiary hover:border-radbot-sunset disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            Next
          </button>
        )}
        <div className="flex-1" />
        <button
          disabled={submitting || !data.name.trim()}
          onClick={submit}
          className="px-4 py-2 bg-radbot-sunset text-bg-primary rounded-md text-sm font-medium hover:bg-radbot-sunset/80 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          {submitting ? "Saving…" : "Finish & Save"}
        </button>
      </div>
    </div>
  );
}

// ── Editor (post-onboarding) ────────────────────────────────

function TelosEditor({ onReset }: { onReset: () => void }) {
  const token = useAdminStore((s) => s.token);
  const toast = useAdminStore((s) => s.toast);
  const [activeSection, setActiveSection] = useState<string>("identity");
  const [entries, setEntries] = useState<TelosEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const activeMeta = useMemo(
    () => SECTIONS.find((s) => s.key === activeSection)!,
    [activeSection],
  );

  const loadSection = async (key: string) => {
    setLoading(true);
    try {
      const res = await telosGetSection(token, key, false);
      setEntries(res.entries);
    } catch (e: any) {
      toast("Load failed: " + e.message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSection(activeSection);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection, token]);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs text-txt-secondary">
          Identity present — beto has your Telos.
        </div>
        <button
          onClick={() => setShowImport((v) => !v)}
          className="px-3 py-1.5 border border-border rounded-md text-xs bg-bg-tertiary hover:border-radbot-sunset cursor-pointer"
        >
          {showImport ? "Hide Import / Export" : "Import / Export markdown"}
        </button>
      </div>

      {showImport && <ImportExportCard />}

      <div className="grid grid-cols-[180px_1fr] gap-4">
        <div className="bg-bg-secondary border border-border rounded-md overflow-hidden self-start">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              onClick={() => setActiveSection(s.key)}
              className={cn(
                "w-full text-left px-3 py-1.5 text-sm border-l-[3px] border-transparent",
                "hover:bg-bg-tertiary",
                activeSection === s.key && "bg-bg-tertiary border-l-radbot-sunset text-txt-primary",
                activeSection !== s.key && "text-txt-secondary",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div>
          <SectionEditor
            sectionMeta={activeMeta}
            entries={entries}
            loading={loading}
            onReload={() => loadSection(activeSection)}
          />
        </div>
      </div>

      <div className="mt-6 pt-3 border-t border-border text-xs text-txt-secondary">
        Raw reset only available via CLI: <code className="font-mono text-[0.72rem]">python -m radbot.tools.telos.cli reset</code> in the container.
        <button
          onClick={onReset}
          className="ml-3 underline hover:text-radbot-sunset cursor-pointer"
        >
          Refresh status
        </button>
      </div>
    </div>
  );
}

// ── Section editor ──────────────────────────────────────────

function SectionEditor({
  sectionMeta,
  entries,
  loading,
  onReload,
}: {
  sectionMeta: (typeof SECTIONS)[number];
  entries: TelosEntry[];
  loading: boolean;
  onReload: () => void;
}) {
  const token = useAdminStore((s) => s.token);
  const toast = useAdminStore((s) => s.toast);
  const [adding, setAdding] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  const isIdentity = sectionMeta.key === "identity";
  const identityEntry = isIdentity ? entries[0] : null;

  const doAdd = async () => {
    if (!newContent.trim()) return;
    try {
      await telosAddEntry(token, sectionMeta.key, { content: newContent.trim() });
      toast(`Added to ${sectionMeta.label}.`);
      setNewContent("");
      setAdding(false);
      onReload();
    } catch (e: any) {
      toast("Add failed: " + e.message, "error");
    }
  };

  const doUpsertIdentity = async () => {
    if (!newContent.trim()) return;
    try {
      await telosAddEntry(token, "identity", {
        content: newContent.trim(),
        ref_code: "ME",
      });
      toast("Identity saved.");
      setNewContent("");
      onReload();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    }
  };

  const doUpdate = async (section: string, refCode: string) => {
    try {
      await telosUpdateEntry(token, section, refCode, { content: editContent });
      toast("Updated.");
      setEditingId(null);
      onReload();
    } catch (e: any) {
      toast("Update failed: " + e.message, "error");
    }
  };

  const doArchive = async (section: string, refCode: string) => {
    if (!confirm(`Archive ${section}:${refCode}?`)) return;
    try {
      await telosArchive(token, section, refCode);
      toast("Archived.");
      onReload();
    } catch (e: any) {
      toast("Archive failed: " + e.message, "error");
    }
  };

  const doResolvePrediction = async (refCode: string, outcome: boolean) => {
    try {
      const res = await telosResolvePrediction(token, refCode, outcome);
      toast(
        res.miscalibrated
          ? "Resolved (miscalibrated — added to wrong_about)."
          : "Resolved.",
      );
      onReload();
    } catch (e: any) {
      toast("Resolve failed: " + e.message, "error");
    }
  };

  return (
    <Card title={sectionMeta.label}>
      {sectionMeta.hint && (
        <div className="text-[0.72rem] text-txt-secondary/60 mb-3">{sectionMeta.hint}</div>
      )}

      {loading && <div className="text-sm text-txt-secondary">Loading…</div>}

      {!loading && isIdentity && (
        <div>
          {identityEntry ? (
            <>
              <div className="text-sm text-txt-primary whitespace-pre-wrap mb-3 p-3 bg-bg-tertiary rounded-md border border-border">
                {identityEntry.content}
              </div>
              <FormTextarea
                label="Replace identity content"
                value={newContent}
                onChange={setNewContent}
                placeholder={identityEntry.content}
              />
              <button
                onClick={doUpsertIdentity}
                disabled={!newContent.trim()}
                className="px-3 py-1.5 bg-radbot-sunset text-bg-primary rounded-md text-sm font-medium hover:bg-radbot-sunset/80 disabled:opacity-40 cursor-pointer"
              >
                Save
              </button>
            </>
          ) : (
            <div className="text-sm text-txt-secondary">No identity yet — onboarding should have caught this.</div>
          )}
        </div>
      )}

      {!loading && !isIdentity && (
        <>
          {entries.length === 0 && (
            <div className="text-sm text-txt-secondary/60 italic mb-3">No entries yet.</div>
          )}

          <div className="flex flex-col gap-2 mb-4">
            {entries.map((e) => (
              <div
                key={e.entry_id}
                className="flex items-start gap-2 p-2 bg-bg-tertiary rounded-md border border-border"
              >
                {e.ref_code && (
                  <span className="font-mono text-[0.7rem] text-radbot-sunset flex-shrink-0 pt-0.5">
                    {e.ref_code}
                  </span>
                )}
                <div className="flex-1 min-w-0">
                  {editingId === e.entry_id ? (
                    <textarea
                      value={editContent}
                      onChange={(ev) => setEditContent(ev.target.value)}
                      className="w-full p-1.5 bg-bg-primary border border-border rounded-md text-sm font-mono resize-y"
                      rows={3}
                      autoFocus
                    />
                  ) : (
                    <div className="text-sm text-txt-primary break-words whitespace-pre-wrap">
                      {e.content}
                    </div>
                  )}
                  {e.metadata && Object.keys(e.metadata).length > 0 && (
                    <div className="text-[0.7rem] text-txt-secondary/60 mt-1 font-mono">
                      {Object.entries(e.metadata)
                        .filter(([, v]) => v !== null && v !== undefined && v !== "")
                        .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)
                        .join("  ·  ")}
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-1 flex-shrink-0">
                  {editingId === e.entry_id ? (
                    <>
                      <button
                        onClick={() => e.ref_code && doUpdate(e.section, e.ref_code)}
                        className="px-2 py-0.5 text-[0.7rem] border border-terminal-green/50 text-terminal-green rounded hover:bg-terminal-green/10 cursor-pointer"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="px-2 py-0.5 text-[0.7rem] border border-border text-txt-secondary rounded hover:border-radbot-sunset cursor-pointer"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      {e.ref_code && (
                        <button
                          onClick={() => {
                            setEditingId(e.entry_id);
                            setEditContent(e.content);
                          }}
                          className="px-2 py-0.5 text-[0.7rem] border border-border text-txt-secondary rounded hover:border-radbot-sunset cursor-pointer"
                        >
                          Edit
                        </button>
                      )}
                      {e.ref_code && sectionMeta.key === "predictions" && e.status === "active" && (
                        <>
                          <button
                            onClick={() => doResolvePrediction(e.ref_code!, true)}
                            className="px-2 py-0.5 text-[0.7rem] border border-terminal-green/50 text-terminal-green rounded hover:bg-terminal-green/10 cursor-pointer"
                          >
                            True
                          </button>
                          <button
                            onClick={() => doResolvePrediction(e.ref_code!, false)}
                            className="px-2 py-0.5 text-[0.7rem] border border-terminal-red/50 text-terminal-red rounded hover:bg-terminal-red/10 cursor-pointer"
                          >
                            False
                          </button>
                        </>
                      )}
                      {e.ref_code && (
                        <button
                          onClick={() => doArchive(e.section, e.ref_code!)}
                          className="px-2 py-0.5 text-[0.7rem] border border-border text-txt-secondary rounded hover:border-terminal-red hover:text-terminal-red cursor-pointer"
                        >
                          Archive
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          {adding ? (
            <div>
              <FormTextarea
                label={`New ${sectionMeta.label.toLowerCase()} entry`}
                value={newContent}
                onChange={setNewContent}
              />
              <div className="flex gap-2">
                <button
                  onClick={doAdd}
                  disabled={!newContent.trim()}
                  className="px-3 py-1.5 bg-radbot-sunset text-bg-primary rounded-md text-sm font-medium hover:bg-radbot-sunset/80 disabled:opacity-40 cursor-pointer"
                >
                  Save
                </button>
                <button
                  onClick={() => { setAdding(false); setNewContent(""); }}
                  className="px-3 py-1.5 border border-border rounded-md text-sm hover:border-radbot-sunset cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAdding(true)}
              className="px-3 py-1.5 border border-border rounded-md text-sm bg-bg-tertiary hover:border-radbot-sunset cursor-pointer"
            >
              + Add entry
            </button>
          )}
        </>
      )}
    </Card>
  );
}

// ── Markdown import / export ────────────────────────────────

function ImportExportCard() {
  const token = useAdminStore((s) => s.token);
  const toast = useAdminStore((s) => s.toast);
  const [markdown, setMarkdown] = useState("");
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);

  const doExport = async () => {
    setBusy(true);
    try {
      const md = await telosExportMarkdown(token);
      setMarkdown(md);
      toast("Exported current Telos to the textarea.");
    } catch (e: any) {
      toast("Export failed: " + e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const doImport = async () => {
    if (!markdown.trim()) {
      toast("Nothing to import.", "error");
      return;
    }
    if (replace && !confirm("This will DELETE all existing Telos entries before importing. Continue?")) {
      return;
    }
    setBusy(true);
    try {
      const res = await telosImportMarkdown(token, markdown, replace);
      toast(`Imported ${res.imported} entries.`);
    } catch (e: any) {
      toast("Import failed: " + e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Import / Export markdown">
      <Note>
        Canonical Telos markdown (`## IDENTITY`, `## PROBLEMS`, …). Export first
        to see the current format, edit, then import back. "Replace" wipes all
        entries before importing — leave off to merge.
      </Note>
      <FormTextarea
        label="Markdown"
        value={markdown}
        onChange={setMarkdown}
        large
        placeholder="# TELOS\n\n## IDENTITY\n..."
      />
      <div className="flex items-center gap-2">
        <button
          onClick={doExport}
          disabled={busy}
          className="px-3 py-1.5 border border-border rounded-md text-sm bg-bg-tertiary hover:border-radbot-sunset disabled:opacity-40 cursor-pointer"
        >
          Export current
        </button>
        <button
          onClick={doImport}
          disabled={busy || !markdown.trim()}
          className="px-3 py-1.5 bg-radbot-sunset text-bg-primary rounded-md text-sm font-medium hover:bg-radbot-sunset/80 disabled:opacity-40 cursor-pointer"
        >
          Import
        </button>
        <label className="flex items-center gap-1.5 text-xs text-txt-secondary cursor-pointer ml-2">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
          replace all (danger)
        </label>
      </div>
    </Card>
  );
}
