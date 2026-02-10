import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  FormInput,
  FormToggle,
  FormDropdown,
  ActionBar,
} from "@/components/admin/FormFields";

const PRIORITY_OPTIONS = [
  { value: "min", label: "Min" },
  { value: "low", label: "Low" },
  { value: "default", label: "Default" },
  { value: "high", label: "High" },
  { value: "max", label: "Max" },
];

// ── ntfy Panel ─────────────────────────────────────────────
export function NtfyPanel() {
  const { loadLiveConfig, mergeConfigSection, toast, token } = useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [url, setUrl] = useState("https://ntfy.sh");
  const [topic, setTopic] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [defaultPriority, setDefaultPriority] = useState("default");
  const [clickBaseUrl, setClickBaseUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const ntfy = cfg?.integrations?.ntfy ?? {};
      setEnabled(ntfy.enabled ?? false);
      setUrl(ntfy.url ?? "https://ntfy.sh");
      setTopic(ntfy.topic ?? "");
      setAccessToken(ntfy.token ? "***" : "");
      setDefaultPriority(ntfy.default_priority ?? "default");
      setClickBaseUrl(ntfy.click_base_url ?? "");
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, any> = {
        enabled,
        url,
        topic,
        default_priority: defaultPriority,
        click_base_url: clickBaseUrl,
      };
      // Only send token if user changed it (not the masked value)
      if (accessToken && accessToken !== "***") {
        payload.token = accessToken;
      }
      await mergeConfigSection("integrations", { ntfy: payload });
      toast("ntfy settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const body: Record<string, any> = { url, topic };
      if (accessToken && accessToken !== "***") {
        body.token = accessToken;
      }
      const resp = await fetch("/admin/api/test/ntfy", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (data.status === "ok") {
        toast(data.message);
      } else {
        toast(data.message, "error");
      }
    } catch (e: any) {
      toast("Test failed: " + e.message, "error");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <h2 className="text-lg font-semibold mb-6">Push Notifications (ntfy)</h2>

      <Card title="ntfy Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Server URL"
          value={url}
          onChange={setUrl}
          placeholder="https://ntfy.sh"
        />
        <FormInput
          label="Topic"
          value={topic}
          onChange={setTopic}
          placeholder="my-radbot-topic"
        />
        <FormInput
          label="Access Token"
          value={accessToken}
          onChange={setAccessToken}
          placeholder="(optional, for private topics)"
          type="password"
        />
        <FormDropdown
          label="Default Priority"
          value={defaultPriority}
          onChange={setDefaultPriority}
          options={PRIORITY_OPTIONS}
        />
        <FormInput
          label="Click Base URL"
          value={clickBaseUrl}
          onChange={setClickBaseUrl}
          placeholder="https://radbot.example.com"
        />
        <ActionBar
          onSave={handleSave}
          saving={saving}
          onTest={handleTest}
          testing={testing}
        />
      </Card>
    </div>
  );
}
