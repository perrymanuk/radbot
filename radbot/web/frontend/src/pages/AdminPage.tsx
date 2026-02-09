import { useEffect, useState } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { cn } from "@/lib/utils";

// Panel imports
import { GooglePanel, AgentModelsPanel, WebServerPanel, LoggingPanel } from "@/components/admin/panels/CorePanels";
import { GmailPanel, CalendarPanel, JiraPanel, OverseerrPanel, HomeAssistantPanel, TavilyPanel, Crawl4aiPanel, FilesystemPanel } from "@/components/admin/panels/ConnectionPanels";
import { PostgresqlPanel, QdrantPanel, RedisPanel } from "@/components/admin/panels/InfrastructurePanels";
import { TTSPanel, STTPanel } from "@/components/admin/panels/MediaPanels";
import { SchedulerPanel, WebhooksPanel } from "@/components/admin/panels/AutomationPanels";
import { MCPServersPanel } from "@/components/admin/panels/MCPPanel";
import { CredentialsPanel } from "@/components/admin/panels/CredentialsPanel";
import { RawConfigPanel } from "@/components/admin/panels/RawConfigPanel";

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
  // Connections
  { id: "gmail", label: "Gmail", group: "Connections", statusKey: "gmail" },
  { id: "calendar", label: "Calendar", group: "Connections", statusKey: "calendar" },
  { id: "jira", label: "Jira", group: "Connections", statusKey: "jira" },
  { id: "overseerr", label: "Overseerr", group: "Connections", statusKey: "overseerr" },
  { id: "home_assistant", label: "Home Assistant", group: "Connections", statusKey: "home_assistant" },
  { id: "tavily", label: "Tavily Search", group: "Connections", statusKey: "tavily" },
  { id: "crawl4ai", label: "Crawl4AI", group: "Connections", statusKey: "crawl4ai" },
  { id: "filesystem", label: "Filesystem", group: "Connections" },
  // Infrastructure
  { id: "postgresql", label: "PostgreSQL", group: "Infrastructure", statusKey: "postgresql" },
  { id: "qdrant", label: "Qdrant", group: "Infrastructure", statusKey: "qdrant" },
  { id: "redis", label: "Redis", group: "Infrastructure", statusKey: "redis" },
  // Media & Voice
  { id: "tts", label: "Text-to-Speech", group: "Media & Voice", statusKey: "tts" },
  { id: "stt", label: "Speech-to-Text", group: "Media & Voice", statusKey: "stt" },
  // Automation
  { id: "scheduler", label: "Scheduler", group: "Automation" },
  { id: "webhooks", label: "Webhooks", group: "Automation" },
  // Advanced
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
  gmail: GmailPanel,
  calendar: CalendarPanel,
  jira: JiraPanel,
  overseerr: OverseerrPanel,
  home_assistant: HomeAssistantPanel,
  tavily: TavilyPanel,
  crawl4ai: Crawl4aiPanel,
  filesystem: FilesystemPanel,
  postgresql: PostgresqlPanel,
  qdrant: QdrantPanel,
  redis: RedisPanel,
  tts: TTSPanel,
  stt: STTPanel,
  scheduler: SchedulerPanel,
  webhooks: WebhooksPanel,
  mcp_servers: MCPServersPanel,
  credentials: CredentialsPanel,
  raw_config: RawConfigPanel,
};

// ── Main Admin Page ────────────────────────────────────────
export default function AdminPage() {
  const authenticated = useAdminStore((s) => s.authenticated);

  if (!authenticated) return <AuthOverlay />;

  return (
    <div className="h-screen flex flex-col bg-[#1a1a2e] text-[#eee]" style={{ fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
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
    <div className="fixed inset-0 bg-[#1a1a2e] z-[1000] flex items-center justify-center">
      <form onSubmit={handleSubmit} className="bg-[#16213e] border border-[#2a3a5c] rounded-xl p-8 w-[380px]">
        <h2 className="text-xl font-semibold mb-1">Admin Access</h2>
        <p className="text-[#999] text-sm mb-6">Enter your admin token</p>
        {error && <div className="text-[#c0392b] text-sm mb-3">{error}</div>}
        <input
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Token"
          className="w-full p-2.5 border border-[#2a3a5c] rounded-md bg-[#1a1a2e] text-[#eee] text-sm mb-4 outline-none focus:border-[#e94560]"
          autoFocus
        />
        <button
          type="submit"
          className="w-full py-2.5 bg-[#e94560] text-white rounded-md font-medium text-sm hover:bg-[#b83350] transition-colors cursor-pointer"
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
    <div className="h-[50px] bg-[#16213e] border-b border-[#2a3a5c] flex items-center justify-between px-5 flex-shrink-0">
      <h1 className="text-base font-semibold">
        RadBot <span className="text-[#e94560]">Admin</span>
      </h1>
      <div className="flex items-center gap-3">
        <a
          href="/"
          className="text-[#999] text-xs border border-[#2a3a5c] px-3 py-1 rounded hover:border-[#e94560] hover:text-[#eee] no-underline transition-colors"
        >
          Chat UI
        </a>
        <button
          onClick={logout}
          className="text-[#999] text-xs border border-[#2a3a5c] px-3 py-1 rounded hover:border-[#e94560] hover:text-[#eee] cursor-pointer transition-colors bg-transparent"
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
    <div className="w-[220px] min-w-[220px] bg-[#16213e] border-r border-[#2a3a5c] overflow-y-auto py-2 flex-shrink-0">
      {Array.from(groups.entries()).map(([group, items]) => (
        <div key={group}>
          <div className="text-[0.65rem] font-bold tracking-wider uppercase text-[#666] px-4 pt-3 pb-1">
            {group}
          </div>
          {items.map((item) => {
            const s = item.statusKey ? status[item.statusKey] : undefined;
            return (
              <div
                key={item.id}
                onClick={() => setActivePanel(item.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-1.5 cursor-pointer text-sm text-[#999] transition-all border-l-[3px] border-transparent",
                  "hover:bg-[#0f3460] hover:text-[#eee]",
                  activePanel === item.id && "bg-[#0f3460] text-[#eee] border-l-[#e94560]",
                )}
              >
                {/* Status dot */}
                {item.statusKey && (
                  <span
                    className={cn(
                      "w-2 h-2 rounded-full flex-shrink-0",
                      s?.status === "ok" ? "bg-[#4caf50]" :
                      s?.status === "error" ? "bg-[#c0392b]" :
                      "bg-[#555]",
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
            <p className="text-[#999] text-sm">Panel not found.</p>
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
              ? "bg-[#1b3a1b] border border-[#4caf50]/30 text-[#4caf50]"
              : "bg-[#3a1b1b] border border-[#c0392b]/30 text-[#c0392b]",
          )}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
