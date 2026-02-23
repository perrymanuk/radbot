import { useState, useEffect } from "react";
import { useAdminStore } from "@/stores/admin-store";
import {
  Card,
  FormInput,
  FormToggle,
  FormTextarea,
  ActionBar,
} from "@/components/admin/FormFields";

// ── GitHub App Panel ──────────────────────────────────────
export function GitHubAppPanel() {
  const { loadLiveConfig, mergeConfigSection, toast, token } = useAdminStore();

  const [enabled, setEnabled] = useState(false);
  const [appId, setAppId] = useState("");
  const [installationId, setInstallationId] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const gh = cfg?.integrations?.github ?? {};
      setEnabled(gh.enabled ?? false);
      setAppId(gh.app_id ?? "");
      setInstallationId(gh.installation_id ?? "");
      setPrivateKey(gh.private_key ? "***" : "");
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, any> = {
        enabled,
        app_id: appId,
        installation_id: installationId,
      };
      if (privateKey && privateKey !== "***") {
        payload.private_key = privateKey;
      }
      await mergeConfigSection("integrations", { github: payload });
      toast("GitHub App settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const body: Record<string, any> = {
        app_id: appId,
        installation_id: installationId,
      };
      if (privateKey && privateKey !== "***") {
        body.private_key = privateKey;
      }
      const resp = await fetch("/admin/api/test/github", {
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
      <h2 className="text-lg font-semibold mb-6">GitHub App</h2>

      <Card title="GitHub App Settings">
        <FormToggle label="Enabled" checked={enabled} onChange={setEnabled} />
        <FormInput
          label="App ID"
          value={appId}
          onChange={setAppId}
          placeholder="123456"
          hint="Found at Settings > Developer settings > GitHub Apps > App ID"
        />
        <FormInput
          label="Installation ID"
          value={installationId}
          onChange={setInstallationId}
          placeholder="12345678"
          hint="Found in the URL after installing the app: /settings/installations/XXXXX"
        />
        <FormTextarea
          label="Private Key (PEM)"
          value={privateKey}
          onChange={setPrivateKey}
          placeholder="-----BEGIN RSA PRIVATE KEY-----&#10;...&#10;-----END RSA PRIVATE KEY-----"
          large
        />
        <ActionBar
          onSave={handleSave}
          saving={saving}
          onTest={handleTest}
          testing={testing}
        />
      </Card>

      <div className="mt-4 text-xs text-[#666]">
        <p className="mb-1"><strong>Setup:</strong></p>
        <ol className="list-decimal ml-4 space-y-0.5">
          <li>Create a GitHub App at github.com/settings/apps/new</li>
          <li>Permissions: Contents (R/W), Pull Requests (R/W), Metadata (R)</li>
          <li>Install the app on desired repos</li>
          <li>Generate a private key and paste the PEM contents above</li>
        </ol>
      </div>
    </div>
  );
}

// ── Claude Code Panel ─────────────────────────────────────
export function ClaudeCodePanel() {
  const { loadLiveConfig, mergeConfigSection, toast, token } = useAdminStore();

  const [oauthToken, setOauthToken] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState("/app/workspaces");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    loadLiveConfig().then((cfg) => {
      const cc = cfg?.integrations?.claude_code ?? {};
      setWorkspaceDir(cc.workspace_dir ?? "/app/workspaces");
      // Check if token exists (masked)
      setOauthToken(cc._has_token ? "***" : "");
    });
    // Also check credential store for existing token
    fetch("/admin/api/credentials", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((creds) => {
        if (Array.isArray(creds)) {
          const hasToken = creds.some((c: any) => c.name === "claude_code_oauth_token");
          if (hasToken && !oauthToken) {
            setOauthToken("***");
          }
        }
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save workspace dir to integrations config
      await mergeConfigSection("integrations", {
        claude_code: { workspace_dir: workspaceDir },
      });

      // Save OAuth token to credential store if changed
      if (oauthToken && oauthToken !== "***") {
        await fetch("/admin/api/credentials", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            name: "claude_code_oauth_token",
            value: oauthToken,
            credential_type: "api_key",
            description: "Claude Code CLI OAuth token",
          }),
        });
      }
      toast("Claude Code settings saved");
    } catch (e: any) {
      toast("Failed to save: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const resp = await fetch("/admin/api/test/claude-code", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({}),
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
      <h2 className="text-lg font-semibold mb-6">Claude Code</h2>

      <Card title="Claude Code CLI Settings">
        <FormInput
          label="OAuth Token"
          value={oauthToken}
          onChange={setOauthToken}
          placeholder="Paste token from 'claude setup-token'"
          type="password"
          hint="Generate with: claude setup-token"
        />
        <FormInput
          label="Workspace Directory"
          value={workspaceDir}
          onChange={setWorkspaceDir}
          placeholder="/app/workspaces"
          hint="Base directory where repos are cloned"
        />
        <ActionBar
          onSave={handleSave}
          saving={saving}
          onTest={handleTest}
          testing={testing}
        />
      </Card>

      <div className="mt-4 text-xs text-[#666]">
        <p className="mb-1"><strong>Setup:</strong></p>
        <ol className="list-decimal ml-4 space-y-0.5">
          <li>Ensure <code>claude</code> CLI is installed (included in Docker image)</li>
          <li>Run <code>claude setup-token</code> to generate an OAuth token</li>
          <li>Paste the token above</li>
        </ol>
      </div>
    </div>
  );
}
