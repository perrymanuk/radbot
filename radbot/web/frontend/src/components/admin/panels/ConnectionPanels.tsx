import { useState, useEffect, useCallback } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  FormInput,
  FormToggle,
  FormDropdown,
  FormTextarea,
  FormRow,
  Card,
  ActionBar,
  StatusBadge,
  Note,
} from "@/components/admin/FormFields";

// ── Shared constants ──────────────────────────────────────

const TIMEZONE_LIST = [
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

const MASKED = "***";

// ── Helpers ───────────────────────────────────────────────

/** Return a nested value from a config object using dot-delimited path. */
function dig(obj: Record<string, any>, path: string, fallback: any = ""): any {
  return path.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : fallback), obj);
}

// ═══════════════════════════════════════════════════════════
// GmailPanel
// ═══════════════════════════════════════════════════════════

interface GmailAccount {
  account: string;
  email: string;
  source: string;
}

export function GmailPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, deleteCredential, testConnection, toast, loadStatus, token, status } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [oauthClientJson, setOauthClientJson] = useState("");
  const [accounts, setAccounts] = useState<GmailAccount[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [newAccountLabel, setNewAccountLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const loadAccounts = useCallback(async () => {
    setAccountsLoading(true);
    try {
      const res = await fetch("/admin/api/gmail/accounts", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to load accounts");
      const data = await res.json();
      setAccounts(data.accounts || []);
    } catch (e: any) {
      toast("Failed to load Gmail accounts: " + e.message, "error");
    } finally {
      setAccountsLoading(false);
    }
  }, [token, toast]);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      setEnabled(!!dig(cfg, "integrations.gmail.enabled"));
    });
    loadAccounts();
  }, [loadLiveConfig, loadAccounts]);

  const handleTestAccount = async (account: string) => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`/admin/api/test/gmail/${encodeURIComponent(account)}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setTestResult(data);
    } catch (e: any) {
      setTestResult({ status: "error", message: e.message });
    } finally {
      setTesting(false);
    }
  };

  const handleRemoveAccount = async (account: string) => {
    try {
      await deleteCredential(`gmail_token_${account}`);
      toast("Account removed", "success");
      loadAccounts();
      loadStatus();
    } catch (e: any) {
      toast("Failed to remove account: " + e.message, "error");
    }
  };

  const handleAddAccount = (mode?: "link") => {
    if (!newAccountLabel.trim()) {
      toast("Please enter an account label", "error");
      return;
    }
    let url = `/admin/api/credentials/gmail/setup?account=${encodeURIComponent(newAccountLabel.trim())}&token=${encodeURIComponent(token)}`;
    if (mode === "link") {
      url += "&mode=link";
    }
    window.open(url, "_blank");
    setNewAccountLabel("");
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (oauthClientJson.trim()) {
        await saveCredential("gmail_oauth_client", oauthClientJson.trim(), "oauth_client", "Gmail OAuth client credentials");
      }
      await mergeConfigSection("integrations", { gmail: { enabled } });
      toast("Gmail settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const gmailStatus = status?.gmail?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Gmail</h2>
        <StatusBadge status={gmailStatus} />
      </div>

      <Card title="Configuration">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormTextarea
          label="OAuth Client JSON"
          value={oauthClientJson}
          onChange={setOauthClientJson}
          placeholder='{"installed":{...}}'
        />
      </Card>

      <Card title="Accounts">
        {accountsLoading ? (
          <div className="text-sm text-txt-secondary">Loading accounts...</div>
        ) : accounts.length === 0 ? (
          <div className="text-sm text-txt-secondary">No accounts configured.</div>
        ) : (
          <div className="overflow-x-auto mb-3">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-txt-secondary border-b border-border">
                  <th className="py-1.5 pr-3">Account</th>
                  <th className="py-1.5 pr-3">Email</th>
                  <th className="py-1.5 pr-3">Source</th>
                  <th className="py-1.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.account} className="border-b border-border/50">
                    <td className="py-1.5 pr-3 text-txt-primary">{a.account}</td>
                    <td className="py-1.5 pr-3 text-txt-primary/90">{a.email}</td>
                    <td className="py-1.5 pr-3 text-txt-secondary">{a.source}</td>
                    <td className="py-1.5 flex gap-1.5">
                      <button
                        onClick={() => handleTestAccount(a.account)}
                        disabled={testing}
                        className="px-2 py-1 text-xs bg-bg-tertiary text-txt-primary border border-border rounded hover:border-radbot-sunset transition-colors cursor-pointer disabled:opacity-50"
                      >
                        Test
                      </button>
                      <button
                        onClick={() => handleRemoveAccount(a.account)}
                        className="px-2 py-1 text-xs bg-terminal-red/15 text-terminal-red border border-border rounded hover:border-terminal-red transition-colors cursor-pointer"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-3 pt-3 border-t border-border">
          <label className="block text-xs text-txt-secondary mb-1 font-medium">Add Account</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={newAccountLabel}
              onChange={(e) => setNewAccountLabel(e.target.value)}
              placeholder="Account Label"
              className="flex-1 p-2 border border-border rounded-md bg-bg-primary text-txt-primary text-sm outline-none focus:border-radbot-sunset transition-colors"
            />
            <button
              onClick={() => handleAddAccount()}
              className="px-3 py-2 bg-bg-tertiary text-txt-primary border border-border rounded-md text-sm font-medium hover:border-radbot-sunset transition-colors cursor-pointer"
            >
              Add Account
            </button>
            <button
              onClick={() => handleAddAccount("link")}
              className="px-3 py-2 bg-bg-primary text-txt-secondary border border-border rounded-md text-sm font-medium hover:border-radbot-sunset hover:text-txt-primary transition-colors cursor-pointer"
              title="Get a copyable auth link for use in another browser"
            >
              Copy Link
            </button>
          </div>
        </div>
      </Card>

      <ActionBar onSave={handleSave} testResult={testResult} testing={testing} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// CalendarPanel
// ═══════════════════════════════════════════════════════════

export function CalendarPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, testConnection, toast, loadStatus, token, status } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [authMethod, setAuthMethod] = useState("service_account");
  const [serviceAccountJson, setServiceAccountJson] = useState("");
  const [calendarId, setCalendarId] = useState("");
  const [timezone, setTimezone] = useState("");
  const [impersonationEmail, setImpersonationEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const cal = dig(cfg, "integrations.calendar", {});
      setEnabled(!!cal.enabled);
      setAuthMethod(cal.auth_method || "service_account");
      setCalendarId(cal.calendar_id || "");
      setTimezone(cal.timezone || "");
      setImpersonationEmail(cal.impersonation_email || "");
    });
  }, [loadLiveConfig]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testConnection("calendar");
      setTestResult(result);
    } catch (e: any) {
      setTestResult({ status: "error", message: e.message });
    } finally {
      setTesting(false);
    }
  };

  const handleOAuthSetup = () => {
    const url = `/admin/api/credentials/calendar/setup?token=${encodeURIComponent(token)}`;
    window.open(url, "_blank");
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (authMethod === "service_account" && serviceAccountJson.trim()) {
        await saveCredential(
          "calendar_service_account",
          serviceAccountJson.trim(),
          "service_account",
          "Google Calendar service account credentials"
        );
      }
      await mergeConfigSection("integrations", {
        calendar: {
          enabled,
          auth_method: authMethod,
          calendar_id: calendarId || undefined,
          timezone: timezone || undefined,
          impersonation_email: impersonationEmail || undefined,
        },
      });
      toast("Calendar settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const calendarStatus = status?.calendar?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Calendar</h2>
        <StatusBadge status={calendarStatus} />
      </div>

      <Card title="Configuration">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormDropdown
          label="Auth Method"
          value={authMethod}
          onChange={setAuthMethod}
          options={[
            { value: "service_account", label: "Service Account" },
            { value: "oauth", label: "OAuth" },
          ]}
        />

        {authMethod === "service_account" ? (
          <FormTextarea
            label="Service Account JSON"
            value={serviceAccountJson}
            onChange={setServiceAccountJson}
            placeholder='{"type":"service_account",...}'
          />
        ) : (
          <div className="mb-3">
            <button
              onClick={handleOAuthSetup}
              className="px-3 py-2 bg-bg-tertiary text-txt-primary border border-border rounded-md text-sm font-medium hover:border-radbot-sunset transition-colors cursor-pointer"
            >
              Set up OAuth Authentication
            </button>
          </div>
        )}

        <FormInput
          label="Calendar ID"
          value={calendarId}
          onChange={setCalendarId}
          placeholder="primary"
        />
        <FormInput
          label="Timezone"
          value={timezone}
          onChange={setTimezone}
          datalist={TIMEZONE_LIST}
        />
        <FormInput
          label="Impersonation Email"
          value={impersonationEmail}
          onChange={setImpersonationEmail}
        />
      </Card>

      <ActionBar onSave={handleSave} onTest={handleTest} testResult={testResult} testing={testing} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// JiraPanel
// ═══════════════════════════════════════════════════════════

export function JiraPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, testConnection, toast, loadStatus, status } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [jiraUrl, setJiraUrl] = useState("");
  const [email, setEmail] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const jira = dig(cfg, "integrations.jira", {});
      setEnabled(!!jira.enabled);
      setJiraUrl(jira.url || "");
      setEmail(jira.email || "");
      if (jira.api_token) setApiToken(MASKED);
    });
  }, [loadLiveConfig]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const body: Record<string, string> = { url: jiraUrl, email };
      if (apiToken && apiToken !== MASKED) body.api_token = apiToken;
      const result = await testConnection("jira", body);
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
      if (apiToken && apiToken !== MASKED) {
        await saveCredential("jira_api_token", apiToken, "api_key", "Jira API token");
      }
      await mergeConfigSection("integrations", {
        jira: {
          enabled,
          url: jiraUrl || undefined,
          email: email || undefined,
        },
      });
      toast("Jira settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const jiraStatus = status?.jira?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Jira</h2>
        <StatusBadge status={jiraStatus} />
      </div>

      <Card title="Configuration">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Jira URL"
          value={jiraUrl}
          onChange={setJiraUrl}
          placeholder="https://your-org.atlassian.net"
        />
        <FormInput label="Email" value={email} onChange={setEmail} />
        <FormInput
          label="API Token"
          value={apiToken}
          onChange={setApiToken}
          type="password"
        />
      </Card>

      <ActionBar onSave={handleSave} onTest={handleTest} testResult={testResult} testing={testing} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// OverseerrPanel
// ═══════════════════════════════════════════════════════════

export function OverseerrPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, testConnection, toast, loadStatus, status } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [overseerrUrl, setOverseerrUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const overseerr = dig(cfg, "integrations.overseerr", {});
      setEnabled(!!overseerr.enabled);
      setOverseerrUrl(overseerr.url || "");
      if (overseerr.api_key) setApiKey(MASKED);
    });
  }, [loadLiveConfig]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const body: Record<string, string> = { url: overseerrUrl };
      if (apiKey && apiKey !== MASKED) body.api_key = apiKey;
      const result = await testConnection("overseerr", body);
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
      if (apiKey && apiKey !== MASKED) {
        await saveCredential("overseerr_api_key", apiKey, "api_key", "Overseerr API key");
      }
      await mergeConfigSection("integrations", {
        overseerr: {
          enabled,
          url: overseerrUrl || undefined,
        },
      });
      toast("Overseerr settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const overseerrStatus = status?.overseerr?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Overseerr</h2>
        <StatusBadge status={overseerrStatus} />
      </div>

      <Card title="Configuration">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Overseerr URL"
          value={overseerrUrl}
          onChange={setOverseerrUrl}
          placeholder="https://overseerr.example.com"
        />
        <FormInput
          label="API Key"
          value={apiKey}
          onChange={setApiKey}
          type="password"
        />
      </Card>

      <ActionBar onSave={handleSave} onTest={handleTest} testResult={testResult} testing={testing} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// LidarrPanel
// ═══════════════════════════════════════════════════════════
export function LidarrPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, testConnection, toast, loadStatus, status } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [lidarrUrl, setLidarrUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const lidarr = dig(cfg, "integrations.lidarr", {});
      setEnabled(!!lidarr.enabled);
      setLidarrUrl(lidarr.url || "");
      if (lidarr.api_key) setApiKey(MASKED);
    });
  }, [loadLiveConfig]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const body: Record<string, string> = { url: lidarrUrl };
      if (apiKey && apiKey !== MASKED) body.api_key = apiKey;
      const result = await testConnection("lidarr", body);
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
      if (apiKey && apiKey !== MASKED) {
        await saveCredential("lidarr_api_key", apiKey, "api_key", "Lidarr API key");
      }
      await mergeConfigSection("integrations", {
        lidarr: {
          enabled,
          url: lidarrUrl || undefined,
        },
      });
      toast("Lidarr settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const lidarrStatus = status?.lidarr?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Lidarr</h2>
        <StatusBadge status={lidarrStatus} />
      </div>

      <Card title="Configuration">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Lidarr URL"
          value={lidarrUrl}
          onChange={setLidarrUrl}
          placeholder="http://lidarr:8686"
        />
        <FormInput
          label="API Key"
          value={apiKey}
          onChange={setApiKey}
          type="password"
        />
      </Card>

      <ActionBar onSave={handleSave} onTest={handleTest} testResult={testResult} testing={testing} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// HomeAssistantPanel
// ═══════════════════════════════════════════════════════════

export function HomeAssistantPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, testConnection, toast, loadStatus, status } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [haUrl, setHaUrl] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [mcpSseUrl, setMcpSseUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const ha = dig(cfg, "integrations.home_assistant", {});
      setEnabled(!!ha.enabled);
      setHaUrl(ha.url || "");
      setMcpSseUrl(ha.mcp_sse_url || "");
      if (ha.token) setAccessToken(MASKED);
    });
  }, [loadLiveConfig]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const body: Record<string, string> = { url: haUrl };
      if (accessToken && accessToken !== MASKED) body.token = accessToken;
      const result = await testConnection("home-assistant", body);
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
      if (accessToken && accessToken !== MASKED) {
        await saveCredential("ha_token", accessToken, "api_key", "Home Assistant access token");
      }
      await mergeConfigSection("integrations", {
        home_assistant: {
          enabled,
          url: haUrl || undefined,
          mcp_sse_url: mcpSseUrl || undefined,
        },
      });
      toast("Home Assistant settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const haStatus = status?.home_assistant?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Home Assistant</h2>
        <StatusBadge status={haStatus} />
      </div>

      <Card title="Configuration">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="URL"
          value={haUrl}
          onChange={setHaUrl}
          placeholder="http://homeassistant.local:8123"
        />
        <FormInput
          label="Access Token"
          value={accessToken}
          onChange={setAccessToken}
          type="password"
        />
        <FormInput
          label="MCP SSE URL"
          value={mcpSseUrl}
          onChange={setMcpSseUrl}
        />
      </Card>

      <ActionBar onSave={handleSave} onTest={handleTest} testResult={testResult} testing={testing} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// PicnicPanel
// ═══════════════════════════════════════════════════════════

export function PicnicPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, testConnection, toast, loadStatus, status } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [countryCode, setCountryCode] = useState("DE");
  const [defaultProject, setDefaultProject] = useState("Groceries");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const picnic = dig(cfg, "integrations.picnic", {});
      setEnabled(!!picnic.enabled);
      setCountryCode(picnic.country_code || "DE");
      setDefaultProject(picnic.default_list_project || "Groceries");
      if (picnic.username) setUsername(picnic.username);
      if (picnic.password) setPassword(MASKED);
    });
  }, [loadLiveConfig]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const body: Record<string, string> = { country_code: countryCode };
      if (username) body.username = username;
      if (password && password !== MASKED) body.password = password;
      const result = await testConnection("picnic", body);
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
      if (username) {
        await saveCredential("picnic_username", username, "username", "Picnic account username");
      }
      if (password && password !== MASKED) {
        await saveCredential("picnic_password", password, "password", "Picnic account password");
      }
      await mergeConfigSection("integrations", {
        picnic: {
          enabled,
          country_code: countryCode,
          default_list_project: defaultProject,
        },
      });
      toast("Picnic settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const picnicStatus = status?.picnic?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Picnic</h2>
        <StatusBadge status={picnicStatus} />
      </div>

      <Card title="Configuration">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="Username"
          value={username}
          onChange={setUsername}
          placeholder="Picnic account email"
        />
        <FormInput
          label="Password"
          value={password}
          onChange={setPassword}
          type="password"
        />
        <FormDropdown
          label="Country"
          value={countryCode}
          onChange={setCountryCode}
          options={[
            { value: "DE", label: "Germany (DE)" },
            { value: "NL", label: "Netherlands (NL)" },
            { value: "BE", label: "Belgium (BE)" },
          ]}
        />
        <FormInput
          label="Default Shopping List Project"
          value={defaultProject}
          onChange={setDefaultProject}
          placeholder="Groceries"
        />
      </Card>

      <ActionBar onSave={handleSave} onTest={handleTest} testResult={testResult} testing={testing} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// FilesystemPanel
// ═══════════════════════════════════════════════════════════

export function FilesystemPanel() {
  const { loadLiveConfig, mergeConfigSection, toast, loadStatus } = useAdminStore();

  const [rootDir, setRootDir] = useState("");
  const [allowedDirs, setAllowedDirs] = useState("");
  const [allowWrite, setAllowWrite] = useState(false);
  const [allowDelete, setAllowDelete] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const fs = dig(cfg, "integrations.filesystem", {});
      setRootDir(fs.root_dir || fs.root_directory || "");
      setAllowWrite(!!fs.allow_write);
      setAllowDelete(!!fs.allow_delete);
      const dirs = fs.allowed_directories || [];
      setAllowedDirs(Array.isArray(dirs) ? dirs.join("\n") : "");
    });
  }, [loadLiveConfig]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const dirsList = allowedDirs
        .split("\n")
        .map((d: string) => d.trim())
        .filter(Boolean);
      await mergeConfigSection("integrations", {
        filesystem: {
          root_dir: rootDir || undefined,
          allow_write: allowWrite,
          allow_delete: allowDelete,
          allowed_directories: dirsList.length > 0 ? dirsList : undefined,
        },
      });
      toast("Filesystem settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Filesystem</h2>
      </div>

      <Card title="Configuration">
        <FormInput
          label="Root Directory"
          value={rootDir}
          onChange={setRootDir}
          placeholder="/app or /home/user"
        />
        <FormTextarea
          label="Additional Allowed Directories"
          value={allowedDirs}
          onChange={setAllowedDirs}
          placeholder={"One directory per line, e.g.:\n/app/workspaces\n/tmp/radbot"}
        />
        <FormToggle label="Allow Write" checked={allowWrite} onChange={setAllowWrite} />
        <FormToggle label="Allow Delete" checked={allowDelete} onChange={setAllowDelete} />
      </Card>

      <ActionBar onSave={handleSave} saving={saving} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// YouTubePanel
// ═══════════════════════════════════════════════════════════

export function YouTubePanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, toast, loadStatus, status, token } =
    useAdminStore();

  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const yt = dig(cfg, "integrations.youtube", {});
      setEnabled(yt.enabled ?? false);
      if (yt.api_key) setApiKey(MASKED);
    });
    // Also check credential store presence via status
    loadStatus();
  }, [loadLiveConfig, loadStatus]);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (apiKey && apiKey !== MASKED) {
        await saveCredential("youtube_api_key", apiKey, "api_key", "YouTube Data API v3 key");
      }
      // Merge config section to trigger integration client reset (hot-reload)
      await mergeConfigSection("integrations", {
        youtube: { enabled },
      });
      toast("YouTube settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const body: Record<string, string> = {};
      if (apiKey && apiKey !== MASKED) body.api_key = apiKey;
      const resp = await fetch("/admin/api/test/youtube", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (data.status === "ok") {
        toast(data.message, "success");
      } else {
        toast(data.message, "error");
      }
    } catch (e: any) {
      toast("Test failed: " + e.message, "error");
    } finally {
      setTesting(false);
    }
  };

  const integrationStatus = status?.youtube?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">YouTube</h2>
        <StatusBadge status={integrationStatus} />
      </div>

      <Card title="YouTube Data API v3">
        <Note>
          Used by the KidsVid agent to search YouTube for safe, educational videos for children.
          Get an API key from the{" "}
          <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer" className="text-radbot-sunset hover:underline">
            Google Cloud Console
          </a>{" "}
          with the YouTube Data API v3 enabled.
        </Note>
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="API Key"
          value={apiKey}
          onChange={setApiKey}
          type="password"
          placeholder="AIzaSy..."
        />
      </Card>

      <ActionBar onSave={handleSave} saving={saving} onTest={handleTest} testing={testing} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// KideoPanel
// ═══════════════════════════════════════════════════════════

export function KideoPanel() {
  const { loadLiveConfig, mergeConfigSection, saveCredential, toast, loadStatus, status, token } =
    useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const kideo = dig(cfg, "integrations.kideo", {});
      setEnabled(kideo.enabled ?? false);
      setUrl(kideo.url ?? "");
      if (kideo.api_key) setApiKey(MASKED);
    });
    loadStatus();
  }, [loadLiveConfig, loadStatus]);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (apiKey && apiKey !== MASKED) {
        await saveCredential("kideo_api_key", apiKey, "api_key", "Kideo API key");
      }
      await mergeConfigSection("integrations", {
        kideo: { enabled, url: url || undefined },
      });
      toast("Kideo settings saved", "success");
      loadStatus();
    } catch (e: any) {
      toast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const body: Record<string, string> = {};
      if (url) body.url = url;
      const resp = await fetch("/admin/api/test/kideo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (data.status === "ok") {
        toast(data.message, "success");
      } else {
        toast(data.message, "error");
      }
    } catch (e: any) {
      toast("Test failed: " + e.message, "error");
    } finally {
      setTesting(false);
    }
  };

  const integrationStatus = status?.kideo?.status || "unconfigured";

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-4">
        <h2 className="text-lg font-semibold text-txt-primary">Kideo</h2>
        <StatusBadge status={integrationStatus} />
      </div>

      <Card title="Kideo Video Library">
        <Note>
          Kideo is a safe, ad-free video player for children. KidsVid can add approved
          YouTube videos to Kideo for offline viewing — no YouTube interface, no
          recommendations, no comments.
        </Note>
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="URL"
          value={url}
          onChange={setUrl}
          placeholder="https://kideo.demonsafe.com"
        />
        <FormInput
          label="API Key (optional)"
          value={apiKey}
          onChange={setApiKey}
          type="password"
          placeholder="(leave empty if no auth required)"
        />
      </Card>

      <ActionBar onSave={handleSave} saving={saving} onTest={handleTest} testing={testing} />
    </div>
  );
}
