import { useEffect, useState } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { cn } from "@/lib/utils";

// Panel imports
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

// ── Navigation definition ──────────────────────────────────
interface NavItem {
  id: string;
  label: string;
  group: string;
  statusKey?: string; // key into IntegrationStatus for sidebar dot
}

const NAV_ITEMS: NavItem[] = [
  // Core
  { id: "google", label: "Google AI", group: "Core", statusKey: "google" },
  { id: "agent_models", label: "Agent & Models", group: "Core" },
  { id: "web_server", label: "Web Server", group: "Core" },
  { id: "logging", label: "Logging", group: "Core" },
  { id: "cost_tracking", label: "Cost Tracking", group: "Core" },
  // Personal
  { id: "telos", label: "Telos", group: "Personal" },
  // Connections
  { id: "gmail", label: "Gmail", group: "Connections", statusKey: "gmail" },
  { id: "calendar", label: "Calendar", group: "Connections", statusKey: "calendar" },
  { id: "jira", label: "Jira", group: "Connections", statusKey: "jira" },
  { id: "overseerr", label: "Overseerr", group: "Connections", statusKey: "overseerr" },
  { id: "lidarr", label: "Lidarr", group: "Connections", statusKey: "lidarr" },
  { id: "home_assistant", label: "Home Assistant", group: "Connections", statusKey: "home_assistant" },
  { id: "picnic", label: "Picnic", group: "Connections", statusKey: "picnic" },
  { id: "youtube", label: "YouTube", group: "Connections", statusKey: "youtube" },
  { id: "kideo", label: "Kideo", group: "Connections", statusKey: "kideo" },
  { id: "filesystem", label: "Filesystem", group: "Connections" },
  // Infrastructure
  { id: "postgresql", label: "PostgreSQL", group: "Infrastructure", statusKey: "postgresql" },
  { id: "qdrant", label: "Qdrant", group: "Infrastructure", statusKey: "qdrant" },
  { id: "nomad", label: "Nomad", group: "Infrastructure", statusKey: "nomad" },
  // Media & Voice
  { id: "tts", label: "Text-to-Speech", group: "Media & Voice", statusKey: "tts" },
  { id: "stt", label: "Speech-to-Text", group: "Media & Voice", statusKey: "stt" },
  // Notifications
  { id: "ntfy", label: "Push Notifications", group: "Notifications", statusKey: "ntfy" },
  // Automation
  { id: "scheduler", label: "Scheduler", group: "Automation" },
  { id: "webhooks", label: "Webhooks", group: "Automation" },
  { id: "alertmanager", label: "Alertmanager", group: "Automation", statusKey: "alertmanager" },
  // Developer
  { id: "github_app", label: "GitHub App", group: "Developer", statusKey: "github" },
  { id: "claude_code", label: "Claude Code", group: "Developer", statusKey: "claude_code" },
  // Security
  { id: "sanitization", label: "Sanitization", group: "Security" },
  // Advanced
  { id: "mcp_bridge", label: "MCP Bridge", group: "Advanced" },
  { id: "mcp_servers", label: "MCP Servers", group: "Advanced" },
  { id: "credentials", label: "Credentials", group: "Advanced" },
  { id: "raw_config", label: "Raw Config", group: "Advanced" },
];

// Panel component mapping
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

// ── Main Admin Page ────────────────────────────────────────
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
    return () => { unsub(); clearTimeout(t); };
  }, [checking]);

  if (checking) {
    return (
      <div className="fixed inset-0 bg-bg-primary z-[1000] flex items-center justify-center">
        <div className="text-txt-secondary text-sm">Authenticating…</div>
      </div>
    );
  }

  if (!authenticated) return <AuthOverlay />;

  return (
    <div className="h-screen flex flex-col bg-bg-primary text-txt-primary font-sans">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <Content />
      </div>
      <ToastContainer />
    </div>
  );
}

// ── Auth Overlay ───────────────────────────────────────────
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
    <div className="fixed inset-0 bg-bg-primary z-[1000] flex items-center justify-center">
      <form onSubmit={handleSubmit} className="bg-bg-secondary border border-border rounded-xl p-8 w-[380px]">
        <h2 className="text-xl font-semibold mb-1">Admin Access</h2>
        <p className="text-txt-secondary text-sm mb-6">Enter your admin token</p>
        {error && <div className="text-terminal-red text-sm mb-3">{error}</div>}
        <input
          type="text"
          name="username"
          autoComplete="username"
          value="admin"
          readOnly
          hidden
        />
        <input
          type="password"
          name="password"
          id="admin-token"
          autoComplete="current-password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Token"
          className="w-full p-2.5 border border-border rounded-md bg-bg-primary text-txt-primary text-sm mb-4 outline-none focus:border-radbot-sunset"
          autoFocus
        />
        <button
          type="submit"
          className="w-full py-2.5 bg-radbot-sunset text-bg-primary rounded-md font-medium text-sm hover:bg-radbot-sunset/80 transition-colors cursor-pointer"
        >
          Authenticate
        </button>
      </form>
    </div>
  );
}

// ── Header ─────────────────────────────────────────────────
function Header() {
  const logout = useAdminStore((s) => s.logout);

  return (
    <div className="scanlines h-[50px] bg-bg-secondary border-b border-border flex items-center justify-between px-4 flex-shrink-0 relative z-10">
      <div className="flex items-center gap-3 min-w-0">
        <div
          aria-hidden
          className="mascot-sticker hidden sm:block w-[34px] h-[34px] flex-none rounded-md border-2 border-[#ff9966] bg-cover"
          style={{
            backgroundImage: "url(/static/dist/radbot.png)",
            backgroundSize: "260%",
            backgroundPosition: "60% 30%",
          }}
        />
        <div className="flex items-baseline gap-2">
          <h1 className="pixel-font text-[18px] text-txt-primary m-0 leading-none">RADBOT</h1>
          <span className="inline-flex text-[9px] font-mono font-semibold tracking-[0.15em] text-radbot-sunset px-1.5 py-0.5 rounded-sm border border-radbot-sunset/40 bg-radbot-sunset/10">
            ADMIN
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <a
          href="/"
          className="font-mono text-[0.7rem] uppercase tracking-wider text-txt-secondary border border-border px-2.5 py-1 rounded-sm hover:border-radbot-sunset hover:text-txt-primary no-underline transition-colors"
        >
          Chat UI
        </a>
        <button
          onClick={logout}
          className="font-mono text-[0.7rem] uppercase tracking-wider text-txt-secondary border border-border px-2.5 py-1 rounded-sm hover:border-radbot-sunset hover:text-txt-primary cursor-pointer transition-colors bg-transparent"
        >
          Logout
        </button>
      </div>
    </div>
  );
}

// ── Sidebar ────────────────────────────────────────────────
function Sidebar() {
  const activePanel = useAdminStore((s) => s.activePanel);
  const setActivePanel = useAdminStore((s) => s.setActivePanel);
  const status = useAdminStore((s) => s.status);
  const loadStatus = useAdminStore((s) => s.loadStatus);
  const loadLiveConfig = useAdminStore((s) => s.loadLiveConfig);

  // Load status and config on mount
  useEffect(() => {
    loadStatus();
    loadLiveConfig();
  }, [loadStatus, loadLiveConfig]);

  // Group nav items
  const groups = new Map<string, NavItem[]>();
  NAV_ITEMS.forEach((item) => {
    const arr = groups.get(item.group) ?? [];
    arr.push(item);
    groups.set(item.group, arr);
  });

  return (
    <div className="w-[220px] min-w-[220px] bg-bg-secondary border-r border-border overflow-y-auto py-2 flex-shrink-0">
      {Array.from(groups.entries()).map(([group, items]) => (
        <div key={group}>
          <div className="text-[0.65rem] font-bold tracking-wider uppercase text-txt-secondary/60 px-4 pt-3 pb-1">
            {group}
          </div>
          {items.map((item) => {
            const s = item.statusKey ? status[item.statusKey] : undefined;
            return (
              <div
                key={item.id}
                onClick={() => setActivePanel(item.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-1.5 cursor-pointer text-sm text-txt-secondary transition-all border-l-[3px] border-transparent",
                  "hover:bg-bg-tertiary hover:text-txt-primary",
                  activePanel === item.id && "bg-bg-tertiary text-txt-primary border-l-radbot-sunset",
                )}
              >
                {/* Status dot */}
                {item.statusKey && (
                  <span
                    className={cn(
                      "w-2 h-2 rounded-full flex-shrink-0",
                      s?.status === "ok" ? "bg-terminal-green" :
                      s?.status === "error" ? "bg-terminal-red" :
                      "bg-txt-secondary/40",
                    )}
                    title={s?.message || s?.status || "unknown"}
                  />
                )}
                <span className="truncate">{item.label}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

// ── Content ────────────────────────────────────────────────
function Content() {
  const activePanel = useAdminStore((s) => s.activePanel);
  const PanelComponent = PANEL_MAP[activePanel];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-[800px]">
        {PanelComponent ? (
          <PanelComponent />
        ) : (
          <div>
            <h2 className="text-lg font-semibold mb-4">
              {NAV_ITEMS.find((i) => i.id === activePanel)?.label ?? activePanel}
            </h2>
            <p className="text-txt-secondary text-sm">Panel not found.</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Toast Container ────────────────────────────────────────
function ToastContainer() {
  const toasts = useAdminStore((s) => s.toasts);
  const dismissToast = useAdminStore((s) => s.dismissToast);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 flex flex-col gap-2 z-[9999]">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismissToast(t.id)}
          className={cn(
            "px-4 py-3 rounded-lg shadow-lg text-sm font-medium cursor-pointer transition-all animate-[slideIn_0.3s_ease-out]",
            "max-w-[400px] break-words",
            t.type === "success"
              ? "bg-terminal-green/15 border border-terminal-green/30 text-terminal-green"
              : "bg-terminal-red/15 border border-terminal-red/30 text-terminal-red",
          )}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
