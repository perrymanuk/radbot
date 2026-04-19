import { useEffect, useState } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { cn } from "@/lib/utils";

import {
  AdminSidebar,
  PanelHeader,
  findPanel,
  mapStatus,
  PANEL_CATEGORIES,
} from "@/components/admin/shell";

// Panel imports — unchanged from legacy AdminPage; the visual refresh comes
// from the shared primitives in FormFields.tsx which every panel uses.
import { GooglePanel, AgentModelsPanel, WebServerPanel, LoggingPanel } from "@/components/admin/panels/CorePanels";
import { GmailPanel, CalendarPanel, JiraPanel, OverseerrPanel, LidarrPanel, HomeAssistantPanel, FilesystemPanel, PicnicPanel, YouTubePanel, KideoPanel } from "@/components/admin/panels/ConnectionPanels";
import { PostgresqlPanel, QdrantPanel } from "@/components/admin/panels/InfrastructurePanels";
import { NomadPanel, AlertmanagerPanel } from "@/components/admin/panels/AlertmanagerPanels";
import { TTSPanel, STTPanel } from "@/components/admin/panels/MediaPanels";
import { NtfyPanel } from "@/components/admin/panels/NotificationPanels";
import { SchedulerPanel, WebhooksPanel } from "@/components/admin/panels/AutomationPanels";
import { SanitizationPanel } from "@/components/admin/panels/SecurityPanels";
import { GitHubAppPanel, ClaudeCodePanel } from "@/components/admin/panels/DeveloperPanels";
import { MCPServersPanel } from "@/components/admin/panels/MCPPanel";
import { CredentialsPanel } from "@/components/admin/panels/CredentialsPanel";
import { RawConfigPanel } from "@/components/admin/panels/RawConfigPanel";
import { CostTrackingPanel } from "@/components/admin/panels/TelemetryPanels";
import { TelosPanel } from "@/components/admin/panels/TelosPanel";
import { McpBridgePanel } from "@/components/admin/panels/McpBridgePanel";

const PANEL_MAP: Record<string, React.ComponentType> = {
  google: GooglePanel,
  agent_models: AgentModelsPanel,
  web_server: WebServerPanel,
  logging: LoggingPanel,
  cost_tracking: CostTrackingPanel,
  telos: TelosPanel,
  gmail: GmailPanel,
  calendar: CalendarPanel,
  jira: JiraPanel,
  overseerr: OverseerrPanel,
  lidarr: LidarrPanel,
  home_assistant: HomeAssistantPanel,
  picnic: PicnicPanel,
  youtube: YouTubePanel,
  kideo: KideoPanel,
  filesystem: FilesystemPanel,
  postgresql: PostgresqlPanel,
  qdrant: QdrantPanel,
  nomad: NomadPanel,
  tts: TTSPanel,
  stt: STTPanel,
  ntfy: NtfyPanel,
  scheduler: SchedulerPanel,
  webhooks: WebhooksPanel,
  alertmanager: AlertmanagerPanel,
  github_app: GitHubAppPanel,
  claude_code: ClaudeCodePanel,
  sanitization: SanitizationPanel,
  mcp_bridge: McpBridgePanel,
  mcp_servers: MCPServersPanel,
  credentials: CredentialsPanel,
  raw_config: RawConfigPanel,
};

export default function AdminPage() {
  const authenticated = useAdminStore((s) => s.authenticated);
  const token = useAdminStore((s) => s.token);
  const [checking, setChecking] = useState(() => !!token && !authenticated);

  useEffect(() => {
    if (!checking) return;
    const unsub = useAdminStore.subscribe((s) => {
      if (s.authenticated || !s.token) setChecking(false);
    });
    const t = setTimeout(() => setChecking(false), 3000);
    return () => {
      unsub();
      clearTimeout(t);
    };
  }, [checking]);

  if (checking) {
    return (
      <div className="admin-scope fixed inset-0 z-[1000] flex items-center justify-center">
        <div style={{ color: "var(--text-mute)", fontSize: 13 }}>Authenticating…</div>
      </div>
    );
  }

  if (!authenticated) return <AuthOverlay />;

  return (
    <div
      className="admin-scope h-screen flex flex-col"
      data-test="admin-dashboard"
    >
      <TopChrome />
      <div className="flex flex-1 overflow-hidden">
        <div className="admin-sidebar-wrap" style={{ display: "flex", flex: "none" }}>
          <SidebarContainer />
        </div>
        <Content />
      </div>
      <ToastContainer />
    </div>
  );
}

function SidebarContainer() {
  const activePanel = useAdminStore((s) => s.activePanel);
  const setActivePanel = useAdminStore((s) => s.setActivePanel);
  const status = useAdminStore((s) => s.status);
  const loadStatus = useAdminStore((s) => s.loadStatus);
  const loadLiveConfig = useAdminStore((s) => s.loadLiveConfig);

  useEffect(() => {
    loadStatus();
    loadLiveConfig();
  }, [loadStatus, loadLiveConfig]);

  return (
    <AdminSidebar
      active={activePanel}
      setActive={(id) => {
        setActivePanel(id);
        const url = new URL(window.location.href);
        url.searchParams.set("panel", id);
        window.history.replaceState({}, "", url.toString());
      }}
      status={status}
    />
  );
}

function AuthOverlay() {
  const [input, setInput] = useState("");
  const setToken = useAdminStore((s) => s.setToken);
  const authenticate = useAdminStore((s) => s.authenticate);
  const error = useAdminStore((s) => s.error);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setToken(input);
    await authenticate();
  };

  return (
    <div
      className="admin-scope fixed inset-0 z-[1000] flex items-center justify-center"
      data-test="admin-login-prompt"
    >
      <form
        onSubmit={handleSubmit}
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          padding: 28,
          width: 380,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 10,
            marginBottom: 4,
          }}
        >
          <h2
            style={{
              fontFamily: "var(--pixel)",
              fontSize: 26,
              color: "var(--text)",
              letterSpacing: "0.04em",
              textShadow: "0 0 10px color-mix(in oklch, var(--sunset) 40%, transparent)",
            }}
          >
            RADBOT
          </h2>
          <span
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.14em",
              color: "var(--sunset)",
              padding: "1px 6px",
              borderRadius: 3,
              background: "color-mix(in oklch, var(--sunset) 14%, transparent)",
              border: "1px solid color-mix(in oklch, var(--sunset) 30%, transparent)",
            }}
          >
            ADMIN
          </span>
        </div>
        <p style={{ color: "var(--text-mute)", fontSize: 13, marginBottom: 22 }}>
          Enter your admin token
        </p>
        {error && (
          <div
            style={{ color: "var(--magenta)", fontSize: 12, marginBottom: 12 }}
            data-test="admin-login-error"
          >
            {error}
          </div>
        )}
        <input type="text" name="username" autoComplete="username" value="admin" readOnly hidden />
        <input
          type="password"
          name="password"
          id="admin-token"
          autoComplete="current-password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Token"
          autoFocus
          data-test="admin-token-input"
          style={{
            width: "100%",
            padding: "10px 12px",
            border: "1px solid var(--border)",
            borderRadius: 6,
            background: "var(--bg-sunk)",
            color: "var(--text)",
            fontSize: 13,
            marginBottom: 16,
            outline: "none",
          }}
        />
        <button
          type="submit"
          data-test="admin-token-submit"
          style={{
            width: "100%",
            padding: "10px",
            background: "var(--sunset)",
            color: "var(--bg)",
            borderRadius: 6,
            fontFamily: "var(--mono)",
            fontWeight: 700,
            fontSize: 12,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            boxShadow: "0 0 18px -4px color-mix(in oklch, var(--sunset) 50%, transparent)",
            cursor: "pointer",
          }}
        >
          Authenticate
        </button>
      </form>
    </div>
  );
}

function TopChrome() {
  const logout = useAdminStore((s) => s.logout);

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "8px 16px",
        background: "var(--bg-sunk)",
        borderBottom: "1px solid var(--border)",
        flex: "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          aria-hidden
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background:
              "linear-gradient(135deg, var(--sunset), var(--magenta))",
            boxShadow:
              "0 0 14px -3px color-mix(in oklch, var(--sunset) 60%, transparent)",
            display: "grid",
            placeItems: "center",
            flex: "none",
          }}
        >
          <span
            style={{
              fontFamily: "var(--pixel)",
              fontSize: 16,
              color: "var(--bg)",
              fontWeight: 700,
            }}
          >
            R
          </span>
        </div>
        <span
          style={{
            fontFamily: "var(--pixel)",
            fontSize: 18,
            letterSpacing: "0.04em",
            color: "var(--text)",
            textShadow: "0 0 6px color-mix(in oklch, var(--sunset) 35%, transparent)",
          }}
        >
          RADBOT
        </span>
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.14em",
            color: "var(--sunset)",
            padding: "1px 6px",
            borderRadius: 3,
            background: "color-mix(in oklch, var(--sunset) 14%, transparent)",
            border: "1px solid color-mix(in oklch, var(--sunset) 30%, transparent)",
          }}
        >
          ADMIN
        </span>
      </div>
      <span style={{ flex: 1 }} />
      <a
        href="/"
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: "var(--text-mute)",
          border: "1px solid var(--border)",
          padding: "5px 10px",
          borderRadius: 4,
        }}
      >
        Chat UI
      </a>
      <button
        type="button"
        onClick={logout}
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: "var(--text-mute)",
          border: "1px solid var(--border)",
          padding: "5px 10px",
          borderRadius: 4,
          cursor: "pointer",
          background: "transparent",
        }}
      >
        Logout
      </button>
    </header>
  );
}

function Content() {
  const activePanel = useAdminStore((s) => s.activePanel);
  const status = useAdminStore((s) => s.status);
  const found = findPanel(activePanel);
  const PanelComponent = PANEL_MAP[activePanel];

  const statusKey = found?.panel.statusKey;
  const panelStatus = mapStatus(statusKey ? status[statusKey] : undefined);

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
      }}
    >
      {found && (
        <PanelHeader panel={found.panel} category={found.category} status={panelStatus} />
      )}
      <div style={{ padding: "22px 26px", maxWidth: 1100, width: "100%" }}>
        {PanelComponent ? (
          <PanelComponent />
        ) : (
          <div style={{ color: "var(--text-mute)", fontSize: 13 }}>
            Panel not found. Available:{" "}
            {PANEL_CATEGORIES.flatMap((c) => c.panels)
              .map((p) => p.id)
              .join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}

function ToastContainer() {
  const toasts = useAdminStore((s) => s.toasts);
  const dismissToast = useAdminStore((s) => s.dismissToast);

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: 20,
        right: 20,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        zIndex: 9999,
      }}
    >
      {toasts.map((t) => {
        const color = t.type === "success" ? "var(--crt)" : "var(--magenta)";
        return (
          <div
            key={t.id}
            onClick={() => dismissToast(t.id)}
            className={cn("animate-[slideIn_0.3s_ease-out]")}
            style={{
              padding: "12px 16px",
              borderRadius: 8,
              background: `color-mix(in oklch, ${color} 14%, var(--surface))`,
              border: `1px solid color-mix(in oklch, ${color} 40%, transparent)`,
              color,
              fontSize: 13,
              fontWeight: 500,
              maxWidth: 400,
              wordBreak: "break-word",
              cursor: "pointer",
              boxShadow: "0 8px 30px -10px rgba(0,0,0,0.5)",
            }}
          >
            {t.message}
          </div>
        );
      })}
    </div>
  );
}

// URL ↔ store sync: read ?panel= on mount.
if (typeof window !== "undefined") {
  const p = new URLSearchParams(window.location.search).get("panel");
  if (p && PANEL_MAP[p]) {
    // Defer to next tick so Zustand has initialized.
    queueMicrotask(() => useAdminStore.setState({ activePanel: p }));
  }
}
