import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { entryKey } from "@/lib/telos-api";
import { useProjectsStore } from "@/stores/projects-store";
import PIcon from "./shared/PIcon";
import RefCode from "./shared/RefCode";
import { accentFor } from "./shared/projectAccent";
import { taskBucket, type TaskStatus } from "./shared/TaskLine";

const STATUS_OPTIONS: { key: TaskStatus; label: string; color: string; metaValue: string }[] = [
  { key: "backlog", label: "Backlog", color: "var(--sky)", metaValue: "backlog" },
  { key: "inprogress", label: "In progress", color: "var(--sunset)", metaValue: "inprogress" },
  { key: "done", label: "Done", color: "var(--crt)", metaValue: "done" },
];

export default function TaskEditDialog() {
  const refCode = useProjectsStore((s) => s.editingTaskRef);
  const close = useProjectsStore((s) => s.closeTaskEditor);
  const entries = useProjectsStore((s) => s.entries);
  const updateTask = useProjectsStore((s) => s.updateTask);

  const task = refCode ? entries[entryKey("project_tasks", refCode)] : undefined;
  const parentProject = task ? (task.metadata || {}).parent_project : undefined;

  const initialStatus = useMemo<TaskStatus>(
    () => (task ? taskBucket(task) : "backlog"),
    [task],
  );
  const initialContent = task ? task.content || "" : "";

  const [content, setContent] = useState(initialContent);
  const [status, setStatus] = useState<TaskStatus>(initialStatus);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setContent(initialContent);
    setStatus(initialStatus);
    setErr(null);
  }, [refCode, initialContent, initialStatus]);

  useEffect(() => {
    if (refCode && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(
        textareaRef.current.value.length,
        textareaRef.current.value.length,
      );
    }
  }, [refCode]);

  if (!refCode || !task) return null;

  const accent = parentProject ? accentFor(parentProject) : "var(--sunset)";
  const dirty = content !== initialContent || status !== initialStatus;

  const onSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    setErr(null);
    try {
      const patch: { content?: string; metadata_merge?: Record<string, any> } = {};
      if (content !== initialContent) patch.content = content;
      if (status !== initialStatus) {
        patch.metadata_merge = { task_status: STATUS_OPTIONS.find((s) => s.key === status)!.metaValue };
      }
      await updateTask(refCode, patch);
      close();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      onSave();
    }
  };

  return createPortal(
    <div
      onClick={close}
      onKeyDown={onKeyDown}
      role="dialog"
      aria-modal="true"
      data-test="projects-task-edit-dialog"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        background: "rgba(0, 0, 0, 0.55)",
        backdropFilter: "blur(2px)",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(640px, 100%)",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          background: "var(--surface)",
          border: `1px solid color-mix(in oklch, ${accent} 30%, var(--p-border))`,
          borderRadius: 10,
          boxShadow: `0 30px 80px -20px rgba(0,0,0,0.6), 0 0 24px -8px ${accent}`,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: `linear-gradient(180deg, color-mix(in oklch, ${accent} 10%, var(--surface-2)), var(--surface))`,
            borderBottom: "1px solid var(--p-border)",
          }}
        >
          <RefCode code={task.ref_code || ""} color={accent} />
          {parentProject && (
            <span
              style={{
                fontFamily: "var(--p-mono)",
                fontSize: 10,
                color: "var(--text-dim)",
                letterSpacing: "0.1em",
              }}
            >
              in {parentProject}
            </span>
          )}
          <span style={{ flex: 1 }} />
          <button
            onClick={close}
            aria-label="Close"
            style={{
              width: 28,
              height: 28,
              display: "grid",
              placeItems: "center",
              color: "var(--text-dim)",
              border: "1px solid var(--p-border)",
              borderRadius: 6,
            }}
            data-test="projects-task-edit-close"
          >
            <PIcon name="close" size={12} />
          </button>
        </div>

        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", gap: 6 }}>
            {STATUS_OPTIONS.map((opt) => {
              const active = status === opt.key;
              return (
                <button
                  key={opt.key}
                  onClick={() => setStatus(opt.key)}
                  data-test={`projects-task-edit-status-${opt.key}`}
                  style={{
                    padding: "6px 12px",
                    borderRadius: 6,
                    fontFamily: "var(--p-mono)",
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: "0.12em",
                    color: active ? opt.color : "var(--text-mute)",
                    background: active
                      ? `color-mix(in oklch, ${opt.color} 14%, transparent)`
                      : "transparent",
                    border: `1px solid ${active ? `color-mix(in oklch, ${opt.color} 40%, transparent)` : "var(--p-border)"}`,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: opt.color,
                      boxShadow: active && opt.key === "inprogress" ? `0 0 6px ${opt.color}` : "none",
                    }}
                  />
                  {opt.label}
                </button>
              );
            })}
          </div>

          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 6,
              fontFamily: "var(--p-mono)",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.16em",
              color: "var(--text-dim)",
            }}
          >
            CONTENT
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={onKeyDown}
              rows={10}
              data-test="projects-task-edit-content"
              style={{
                width: "100%",
                minHeight: 160,
                padding: "10px 12px",
                background: "var(--bg-sunk)",
                border: "1px solid var(--p-border)",
                borderRadius: 6,
                fontFamily: "var(--p-mono)",
                fontSize: 12,
                lineHeight: 1.5,
                color: "var(--text)",
                resize: "vertical",
                letterSpacing: "normal",
                fontWeight: 400,
              }}
            />
          </label>

          {err && (
            <div
              style={{
                padding: "8px 12px",
                background: "color-mix(in oklch, var(--magenta) 10%, transparent)",
                border: "1px solid color-mix(in oklch, var(--magenta) 40%, transparent)",
                borderRadius: 6,
                fontFamily: "var(--p-mono)",
                fontSize: 11,
                color: "var(--magenta)",
              }}
            >
              {err}
            </div>
          )}
        </div>

        <div
          style={{
            padding: "12px 16px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            borderTop: "1px solid var(--p-border)",
            background: "var(--bg-sunk)",
          }}
        >
          <span
            style={{
              fontFamily: "var(--p-mono)",
              fontSize: 10,
              color: "var(--text-dim)",
              letterSpacing: "0.08em",
            }}
          >
            <span className="kbd">⌘</span>
            <span className="kbd" style={{ marginLeft: 3 }}>↵</span>
            <span style={{ marginLeft: 8 }}>save</span>
            <span style={{ marginLeft: 10 }} className="kbd">
              esc
            </span>
            <span style={{ marginLeft: 6 }}>cancel</span>
          </span>
          <span style={{ flex: 1 }} />
          <button
            onClick={close}
            disabled={saving}
            style={{
              padding: "6px 12px",
              fontFamily: "var(--p-mono)",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "var(--text-mute)",
              border: "1px solid var(--p-border)",
              borderRadius: 5,
              opacity: saving ? 0.5 : 1,
            }}
            data-test="projects-task-edit-cancel"
          >
            CANCEL
          </button>
          <button
            onClick={onSave}
            disabled={!dirty || saving}
            data-test="projects-task-edit-save"
            style={{
              padding: "6px 14px",
              fontFamily: "var(--p-mono)",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "var(--bg)",
              background: accent,
              border: `1px solid ${accent}`,
              borderRadius: 5,
              boxShadow: dirty && !saving ? `0 0 16px -6px ${accent}` : "none",
              opacity: !dirty || saving ? 0.4 : 1,
              cursor: !dirty || saving ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "SAVING…" : "SAVE"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
