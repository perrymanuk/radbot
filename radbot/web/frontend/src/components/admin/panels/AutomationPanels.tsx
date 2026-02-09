import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  Note,
  FormInput,
  FormToggle,
  ActionBar,
} from "@/components/admin/FormFields";

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
  "UTC",
];

// ── Scheduler Panel ───────────────────────────────────────
export function SchedulerPanel() {
  const { loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [timezone, setTimezone] = useState("UTC");
  const [maxConcurrentJobs, setMaxConcurrentJobs] = useState("10");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const sched = cfg?.scheduler ?? {};
      setEnabled(sched.enabled ?? false);
      setTimezone(sched.timezone ?? "UTC");
      setMaxConcurrentJobs(
        sched.max_concurrent_jobs != null
          ? String(sched.max_concurrent_jobs)
          : "10",
      );
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mergeConfigSection("scheduler", {
        enabled,
        timezone,
        max_concurrent_jobs: parseInt(maxConcurrentJobs, 10),
      });
      toast("Scheduler settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <h2 className="text-lg font-semibold mb-6">Scheduler</h2>

      <Card title="Scheduler Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Timezone"
          value={timezone}
          onChange={setTimezone}
          datalist={TIMEZONES}
        />
        <FormInput
          label="Max Concurrent Jobs"
          value={maxConcurrentJobs}
          onChange={setMaxConcurrentJobs}
          type="number"
        />
        <ActionBar onSave={handleSave} saving={saving} />
      </Card>
    </div>
  );
}

// ── Webhooks Panel ────────────────────────────────────────
export function WebhooksPanel() {
  const { loadLiveConfig, mergeConfigSection, toast } = useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const wh = cfg?.webhooks ?? {};
      setEnabled(wh.enabled ?? false);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mergeConfigSection("webhooks", {
        enabled,
      });
      toast("Webhooks settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <h2 className="text-lg font-semibold mb-6">Webhooks</h2>

      <Card title="Webhooks Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <Note>
          Webhook definitions are managed through the chat interface using the
          webhook tools.
        </Note>
        <ActionBar onSave={handleSave} saving={saving} />
      </Card>
    </div>
  );
}
