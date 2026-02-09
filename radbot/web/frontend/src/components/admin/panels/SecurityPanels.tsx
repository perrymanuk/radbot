import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  Note,
  FormToggle,
  FormDropdown,
  ActionBar,
} from "@/components/admin/FormFields";

const STRICTNESS_OPTIONS = [
  { value: "relaxed", label: "Relaxed — zero-width, bidi, tags, control chars" },
  { value: "standard", label: "Standard — + soft hyphen, variation selectors, interlinear" },
  { value: "strict", label: "Strict — + Private Use Area" },
];

// ── Sanitization Panel ──────────────────────────────────
export function SanitizationPanel() {
  const { loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [enabled, setEnabled] = useState(true);
  const [strictness, setStrictness] = useState("standard");
  const [logDetections, setLogDetections] = useState(true);
  const [callbackEnabled, setCallbackEnabled] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const sanitize = cfg?.security?.sanitize ?? {};
      setEnabled(sanitize.enabled ?? true);
      setStrictness(sanitize.strictness ?? "standard");
      setLogDetections(sanitize.log_detections ?? true);
      setCallbackEnabled(sanitize.callback_enabled ?? true);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mergeConfigSection("security", {
        sanitize: {
          enabled,
          strictness,
          log_detections: logDetections,
          callback_enabled: callbackEnabled,
        },
      });
      toast("Sanitization settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <h2 className="text-lg font-semibold mb-6">Input Sanitization</h2>

      <Card title="Unicode Sanitization">
        <Note>
          Strips invisible and control Unicode characters from external content
          (emails, webhooks, calendar events, etc.) before they reach the LLM.
          Defends against prompt injection via zero-width spaces, bidi overrides,
          tag characters, and other invisible encoding tricks.
        </Note>

        <FormToggle
          label="Enable sanitization"
          checked={enabled}
          onChange={setEnabled}
        />

        <FormDropdown
          label="Strictness Level"
          value={strictness}
          onChange={setStrictness}
          options={STRICTNESS_OPTIONS}
        />

        <FormToggle
          label="Log detections"
          checked={logDetections}
          onChange={setLogDetections}
        />

        <FormToggle
          label="Before-model callback (catch-all)"
          checked={callbackEnabled}
          onChange={setCallbackEnabled}
        />

        <Note>
          Per-tool sanitization runs at each external content ingestion point
          (Gmail, webhooks, scheduler, memory, Home Assistant, calendar, Jira,
          Overseerr). The before-model callback is an additional catch-all that
          sanitizes all LLM request content, covering MCP tools and any other
          paths.
        </Note>

        <ActionBar onSave={handleSave} saving={saving} />
      </Card>
    </div>
  );
}
