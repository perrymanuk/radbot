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
        <h2 className="text-lg font-semibold text-[#eee]">Gmail</h2>
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
          <div className="text-sm text-[#999]">Loading accounts...</div>
        ) : accounts.length === 0 ? (
          <div className="text-sm text-[#999]">No accounts configured.</div>
        ) : (
          <div className="overflow-x-auto mb-3">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[#999] border-b border-[#2a3a5c]">
                  <th className="py-1.5 pr-3">Account</th>
                  <th className="py-1.5 pr-3">Email</th>
                  <th className="py-1.5 pr-3">Source</th>
                  <th className="py-1.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.account} className="border-b border-[#2a3a5c]/50">
                    <td className="py-1.5 pr-3 text-[#eee]">{a.account}</td>
                    <td className="py-1.5 pr-3 text-[#ccc]">{a.email}</td>
                    <td className="py-1.5 pr-3 text-[#999]">{a.source}</td>
                    <td className="py-1.5 flex gap-1.5">
                      <button
                        onClick={() => handleTestAccount(a.account)}
                        disabled={testing}
                        className="px-2 py-1 text-xs bg-[#0f3460] text-[#eee] border border-[#2a3a5c] rounded hover:border-[#e94560] transition-colors cursor-pointer disabled:opacity-50"
                      >
                        Test
                      </button>
                      <button
                        onClick={() => handleRemoveAccount(a.account)}
                        className="px-2 py-1 text-xs bg-[#3a1b1b] text-[#c0392b] border border-[#2a3a5c] rounded hover:border-[#c0392b] transition-colors cursor-pointer"
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

        <div className="mt-3 pt-3 border-t border-[#2a3a5c]">
          <label className="block text-xs text-[#999] mb-1 font-medium">Add Account</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={newAccountLabel}
              onChange={(e) => setNewAccountLabel(e.target.value)}
              placeholder="Account Label"
              className="flex-1 p-2 border border-[#2a3a5c] rounded-md bg-[#1a1a2e] text-[#eee] text-sm outline-none focus:border-[#e94560] transition-colors"
            />
            <button
              onClick={() => handleAddAccount()}
              className="px-3 py-2 bg-[#0f3460] text-[#eee] border border-[#2a3a5c] rounded-md text-sm font-medium hover:border-[#e94560] transition-colors cursor-pointer"
            >
              Add Account
            </button>
            <button
              onClick={() => handleAddAccount("link")}
              className="px-3 py-2 bg-[#1a1a2e] text-[#999] border border-[#2a3a5c] rounded-md text-sm font-medium hover:border-[#e94560] hover:text-[#eee] transition-colors cursor-pointer"
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
        <h2 className="text-lg font-semibold text-[#eee]">Calendar</h2>
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
              className="px-3 py-2 bg-[#0f3460] text-[#eee] border border-[#2a3a5c] rounded-md text-sm font-medium hover:border-[#e94560] transition-colors cursor-pointer"
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
        <h2 className="text-lg font-semibold text-[#eee]">Jira</h2>
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
        <h2 className="text-lg font-semibold text-[#eee]">Overseerr</h2>
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
        <h2 className="text-lg font-semibold text-[#eee]">Home Assistant</h2>
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
        <h2 className="text-lg font-semibold text-[#eee]">Picnic</h2>
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
  const [allowWrite, setAllowWrite] = useState(false);
  const [allowDelete, setAllowDelete] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const fs = dig(cfg, "integrations.filesystem", {});
      setRootDir(fs.root_directory || "");
      setAllowWrite(!!fs.allow_write);
      setAllowDelete(!!fs.allow_delete);
    });
  }, [loadLiveConfig]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await mergeConfigSection("integrations", {
        filesystem: {
          root_directory: rootDir || undefined,
          allow_write: allowWrite,
          allow_delete: allowDelete,
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
        <h2 className="text-lg font-semibold text-[#eee]">Filesystem</h2>
      </div>

      <Card title="Configuration">
        <FormInput
          label="Root Directory"
          value={rootDir}
          onChange={setRootDir}
        />
        <FormToggle label="Allow Write" checked={allowWrite} onChange={setAllowWrite} />
        <FormToggle label="Allow Delete" checked={allowDelete} onChange={setAllowDelete} />
      </Card>

      <ActionBar onSave={handleSave} saving={saving} />
    </div>
  );
}
