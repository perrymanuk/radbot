import { useState, useEffect, useCallback } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  Note,
  FormInput,
  FormRow,
  FormToggle,
  ActionBar,
  StatusBadge,
} from "@/components/admin/FormFields";
import type { TestResult } from "@/lib/admin-api";

// ── Nomad Panel ──────────────────────────────────────────────
export function NomadPanel() {
  const {
    liveConfig,
    loadLiveConfig,
    status,
    saveCredential,
    mergeConfigSection,
    testConnection,
    toast,
  } = useAdminStore();

  const [addr, setAddr] = useState("");
  const [token, setToken] = useState("***");
  const [namespace, setNamespace] = useState("default");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const nomad = cfg?.integrations?.nomad ?? {};
      setAddr(nomad.addr ?? "");
      setNamespace(nomad.namespace ?? "default");
    });
  }, []);

  const nomadStatus = status?.nomad?.status;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testConnection("nomad", {
        addr,
        token: token === "***" ? undefined : token,
      });
      setTestResult(result);
    } catch (e: any) {
      setTestResult({ status: "error", message: e.message });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (token && token !== "***") {
        await saveCredential("nomad_token", token, "api_key", "Nomad ACL token");
      }
      await mergeConfigSection("integrations", {
        nomad: { addr, namespace, enabled: true },
      });
      toast("Nomad settings saved");

    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-lg font-semibold">Nomad</h2>
        {nomadStatus && <StatusBadge status={nomadStatus} />}
      </div>

      <Card title="Connection Settings">
        <FormInput
          label="Nomad Address"
          value={addr}
          onChange={setAddr}
          placeholder="http://nomad.service.consul:4646"
        />
        <FormInput
          label="ACL Token"
          value={token}
          onChange={setToken}
          type="password"
        />
        <FormInput
          label="Namespace"
          value={namespace}
          onChange={setNamespace}
          placeholder="default"
        />
        <ActionBar
          onTest={handleTest}
          onSave={handleSave}
          testResult={testResult}
          testing={testing}
          saving={saving}
        />
      </Card>
    </div>
  );
}

// ── Alertmanager Panel ───────────────────────────────────────

interface AlertEvent {
  alert_id: string;
  alertname: string;
  status: string;
  severity: string | null;
  instance: string | null;
  summary: string | null;
  remediation_action: string | null;
  remediation_result: string | null;
  created_at: string | null;
  resolved_at: string | null;
}

interface Policy {
  policy_id: string;
  alertname_pattern: string;
  severity: string | null;
  action: string;
  max_auto_remediations: number;
  window_minutes: number;
  enabled: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  received: "bg-blue-500",
  analyzing: "bg-yellow-500",
  remediating: "bg-orange-500",
  remediated: "bg-green-500",
  resolved: "bg-green-700",
  failed: "bg-red-500",
  ignored: "bg-gray-500",
};

export function AlertmanagerPanel() {
  const { liveConfig, loadLiveConfig, mergeConfigSection, saveCredential, status, toast, loadStatus } = useAdminStore();
  const token = useAdminStore((s) => s.token);

  const [subscribeTopic, setSubscribeTopic] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("***");
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [alertTotal, setAlertTotal] = useState(0);
  const [alertPage, setAlertPage] = useState(0);
  const alertPageSize = 10;
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  // New policy form
  const [newPattern, setNewPattern] = useState("");
  const [newAction, setNewAction] = useState("auto");
  const [newMax, setNewMax] = useState("3");
  const [newWindow, setNewWindow] = useState("60");

  const alertmanagerStatus = status?.alertmanager?.status;

  const loadAlerts = useCallback(async (page: number) => {
    try {
      const offset = page * alertPageSize;
      const resp = await fetch(
        `/api/alerts/?limit=${alertPageSize}&offset=${offset}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (resp.ok) {
        const data = await resp.json();
        setAlerts(data.alerts ?? []);
        setAlertTotal(data.total ?? 0);
      }
    } catch (e) {
      console.error("Failed to load alerts:", e);
    }
  }, [token]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // Load config
      const cfg = await loadLiveConfig();
      const ntfyCfg = cfg?.integrations?.ntfy ?? {};
      const topics = ntfyCfg.subscribe_topics ?? [];
      setSubscribeTopic(topics.join(", "));

      // Load alerts (first page)
      await loadAlerts(0);
      setAlertPage(0);

      // Load policies
      const policyResp = await fetch("/api/alerts/policies/", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (policyResp.ok) {
        const data = await policyResp.json();
        setPolicies(data.policies ?? []);
      }
    } catch (e) {
      console.error("Failed to load alertmanager data:", e);
    } finally {
      setLoading(false);
    }
  }, [token, loadLiveConfig, loadAlerts]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handlePageChange = (newPage: number) => {
    setAlertPage(newPage);
    loadAlerts(newPage);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const topics = subscribeTopic
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await mergeConfigSection("integrations", {
        ntfy: { subscribe_topics: topics },
      });
      if (webhookSecret && webhookSecret !== "***") {
        await saveCredential(
          "alertmanager_webhook_secret",
          webhookSecret,
          "api_key",
          "Alertmanager webhook HMAC secret"
        );
      }
      toast("Alertmanager settings saved");

    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleAddPolicy = async () => {
    if (!newPattern) return;
    try {
      const resp = await fetch("/api/alerts/policies/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          alertname_pattern: newPattern,
          action: newAction,
          max_auto_remediations: parseInt(newMax, 10),
          window_minutes: parseInt(newWindow, 10),
        }),
      });
      if (resp.ok) {
        toast("Policy created");
        setNewPattern("");
        loadData();
      } else {
        const err = await resp.json();
        toast("Failed: " + (err.detail || "Unknown error"), "error");
      }
    } catch (e: any) {
      toast("Failed: " + e.message, "error");
    }
  };

  const handleDeletePolicy = async (policyId: string) => {
    try {
      const resp = await fetch(`/api/alerts/policies/${policyId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        toast("Policy deleted");
        loadData();
      }
    } catch (e: any) {
      toast("Failed: " + e.message, "error");
    }
  };

  const handleDismiss = async (alertId: string) => {
    try {
      const resp = await fetch(`/api/alerts/${alertId}/dismiss`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        toast("Alert dismissed");
        loadData();
      }
    } catch (e: any) {
      toast("Failed: " + e.message, "error");
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-[800px]">
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-lg font-semibold">Alertmanager</h2>
        {alertmanagerStatus && <StatusBadge status={alertmanagerStatus} />}
      </div>

      <Note>
        Radbot subscribes to ntfy topics to receive alertmanager alerts.
        Configure the topic name below and set up alertmanager to publish
        alerts to that ntfy topic. A direct webhook endpoint is also available
        at <code>/api/alerts/alertmanager</code>.
      </Note>

      {/* Configuration */}
      <Card title="Alert Ingestion">
        <FormInput
          label="ntfy Subscribe Topics"
          value={subscribeTopic}
          onChange={setSubscribeTopic}
          placeholder="alerts (comma-separated for multiple)"
        />
        <FormInput
          label="Webhook Secret (optional)"
          value={webhookSecret}
          onChange={setWebhookSecret}
          type="password"
          placeholder="HMAC secret for direct webhook"
        />
        <div className="flex justify-end gap-2 pt-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-[#e94560] text-white text-sm rounded hover:bg-[#b83350] disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </Card>

      {/* Policies */}
      <Card title="Remediation Policies">
        <div className="space-y-2 mb-4">
          {policies.length === 0 ? (
            <p className="text-[#666] text-sm">
              No policies configured. Without policies, all alerts use default
              auto-remediation (max 3 per hour).
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[#999] text-left border-b border-[#2a3a5c]">
                  <th className="py-1 pr-2">Pattern</th>
                  <th className="py-1 pr-2">Action</th>
                  <th className="py-1 pr-2">Limit</th>
                  <th className="py-1"></th>
                </tr>
              </thead>
              <tbody>
                {policies.map((p) => (
                  <tr key={p.policy_id} className="border-b border-[#2a3a5c]/50">
                    <td className="py-1.5 pr-2 font-mono text-xs">{p.alertname_pattern}</td>
                    <td className="py-1.5 pr-2">{p.action}</td>
                    <td className="py-1.5 pr-2 text-[#999]">
                      {p.max_auto_remediations}/{p.window_minutes}min
                    </td>
                    <td className="py-1.5 text-right">
                      <button
                        onClick={() => handleDeletePolicy(p.policy_id)}
                        className="text-[#c0392b] text-xs hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Add policy form */}
        <div className="border-t border-[#2a3a5c] pt-3 space-y-2">
          <p className="text-xs text-[#999] mb-2">Add Policy</p>
          <FormRow>
            <FormInput
              label="Alertname Pattern (regex)"
              value={newPattern}
              onChange={setNewPattern}
              placeholder="HighMemoryUsage|OOM.*"
            />
            <div>
              <label className="block text-xs text-[#999] mb-1">Action</label>
              <select
                value={newAction}
                onChange={(e) => setNewAction(e.target.value)}
                className="w-full p-2 border border-[#2a3a5c] rounded bg-[#1a1a2e] text-[#eee] text-sm"
              >
                <option value="auto">Auto (investigate + fix)</option>
                <option value="restart">Restart allocation</option>
                <option value="ignore">Ignore</option>
              </select>
            </div>
          </FormRow>
          <FormRow>
            <FormInput
              label="Max Remediations"
              value={newMax}
              onChange={setNewMax}
              type="number"
            />
            <FormInput
              label="Window (minutes)"
              value={newWindow}
              onChange={setNewWindow}
              type="number"
            />
          </FormRow>
          <button
            onClick={handleAddPolicy}
            disabled={!newPattern}
            className="px-3 py-1.5 bg-[#0f3460] text-white text-sm rounded hover:bg-[#16213e] disabled:opacity-50 transition-colors"
          >
            Add Policy
          </button>
        </div>
      </Card>

      {/* Recent Alerts */}
      <Card title={`Alerts (${alertTotal})`}>
        {loading ? (
          <p className="text-[#666] text-sm">Loading...</p>
        ) : alerts.length === 0 ? (
          <p className="text-[#666] text-sm">No alerts received yet.</p>
        ) : (
          <div className="space-y-2">
            {alerts.map((a) => (
              <div
                key={a.alert_id}
                className="border border-[#2a3a5c] rounded p-3 bg-[#1a1a2e]"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`w-2 h-2 rounded-full ${STATUS_COLORS[a.status] ?? "bg-gray-500"}`}
                  />
                  <span className="font-mono text-sm font-semibold">{a.alertname}</span>
                  <span className="text-xs text-[#999]">{a.status}</span>
                  {a.severity && (
                    <span className="text-xs text-[#999] ml-auto">{a.severity}</span>
                  )}
                </div>
                {a.summary && (
                  <p className="text-xs text-[#999] mb-1">{a.summary}</p>
                )}
                {a.remediation_action && (
                  <p className="text-xs text-green-400">Action: {a.remediation_action}</p>
                )}
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs text-[#666]">
                    {a.created_at ? new Date(a.created_at).toLocaleString() : ""}
                  </span>
                  {a.status !== "resolved" && a.status !== "ignored" && (
                    <button
                      onClick={() => handleDismiss(a.alert_id)}
                      className="text-xs text-[#999] hover:text-[#eee] ml-auto"
                    >
                      Dismiss
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {alertTotal > alertPageSize && (
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#2a3a5c]">
            <button
              onClick={() => handlePageChange(alertPage - 1)}
              disabled={alertPage === 0}
              className="px-3 py-1.5 text-xs border border-[#2a3a5c] rounded text-[#999] hover:text-[#eee] hover:border-[#e94560] disabled:opacity-30 disabled:hover:text-[#999] disabled:hover:border-[#2a3a5c] transition-colors"
            >
              Previous
            </button>
            <span className="text-xs text-[#999]">
              {alertPage * alertPageSize + 1}–{Math.min((alertPage + 1) * alertPageSize, alertTotal)} of {alertTotal}
            </span>
            <button
              onClick={() => handlePageChange(alertPage + 1)}
              disabled={(alertPage + 1) * alertPageSize >= alertTotal}
              className="px-3 py-1.5 text-xs border border-[#2a3a5c] rounded text-[#999] hover:text-[#eee] hover:border-[#e94560] disabled:opacity-30 disabled:hover:text-[#999] disabled:hover:border-[#2a3a5c] transition-colors"
            >
              Next
            </button>
          </div>
        )}

        <button
          onClick={() => { setAlertPage(0); loadAlerts(0); }}
          disabled={loading}
          className="mt-3 px-3 py-1.5 text-xs border border-[#2a3a5c] rounded text-[#999] hover:text-[#eee] hover:border-[#e94560] transition-colors"
        >
          Refresh
        </button>
      </Card>
    </div>
  );
}
