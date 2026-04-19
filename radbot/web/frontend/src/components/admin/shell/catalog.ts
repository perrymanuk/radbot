import type { AIconName } from "./icons";
import type { PanelStatus } from "./primitives";

export interface CatalogPanel {
  id: string;
  label: string;
  icon: AIconName;
  statusKey?: string;
}

export interface CatalogCategory {
  key: string;
  label: string;
  panels: CatalogPanel[];
}

// Panel ids match the existing PANEL_MAP keys in AdminPage so the admin-store
// activePanel value survives the redesign. Icons + categories come from the
// handoff design.
export const PANEL_CATEGORIES: CatalogCategory[] = [
  {
    key: "core",
    label: "CORE",
    panels: [
      { id: "google", label: "Google AI", icon: "sparkle", statusKey: "google" },
      { id: "agent_models", label: "Agent & Models", icon: "cpu" },
      { id: "web_server", label: "Web Server", icon: "server" },
      { id: "logging", label: "Logging", icon: "list" },
      { id: "cost_tracking", label: "Cost Tracking", icon: "chart" },
    ],
  },
  {
    key: "personal",
    label: "PERSONAL",
    panels: [{ id: "telos", label: "Telos", icon: "compass" }],
  },
  {
    key: "connections",
    label: "CONNECTIONS",
    panels: [
      { id: "gmail", label: "Gmail", icon: "mail", statusKey: "gmail" },
      { id: "calendar", label: "Calendar", icon: "calendar", statusKey: "calendar" },
      { id: "jira", label: "Jira", icon: "jira", statusKey: "jira" },
      { id: "overseerr", label: "Overseerr", icon: "play", statusKey: "overseerr" },
      { id: "lidarr", label: "Lidarr", icon: "music", statusKey: "lidarr" },
      { id: "home_assistant", label: "Home Assistant", icon: "home", statusKey: "home_assistant" },
      { id: "picnic", label: "Picnic", icon: "cart", statusKey: "picnic" },
      { id: "youtube", label: "YouTube", icon: "video", statusKey: "youtube" },
      { id: "kideo", label: "Kideo", icon: "clap", statusKey: "kideo" },
      { id: "filesystem", label: "Filesystem", icon: "folder" },
    ],
  },
  {
    key: "infra",
    label: "INFRASTRUCTURE",
    panels: [
      { id: "postgresql", label: "PostgreSQL", icon: "db", statusKey: "postgresql" },
      { id: "qdrant", label: "Qdrant", icon: "vec", statusKey: "qdrant" },
      { id: "nomad", label: "Nomad", icon: "nomad", statusKey: "nomad" },
    ],
  },
  {
    key: "media",
    label: "MEDIA & VOICE",
    panels: [
      { id: "tts", label: "Text-to-Speech", icon: "speaker", statusKey: "tts" },
      { id: "stt", label: "Speech-to-Text", icon: "mic", statusKey: "stt" },
    ],
  },
  {
    key: "notifs",
    label: "NOTIFICATIONS",
    panels: [{ id: "ntfy", label: "Push Notifications", icon: "bell", statusKey: "ntfy" }],
  },
  {
    key: "automation",
    label: "AUTOMATION",
    panels: [
      { id: "scheduler", label: "Scheduler", icon: "clock" },
      { id: "webhooks", label: "Webhooks", icon: "link" },
      { id: "alertmanager", label: "Alertmanager", icon: "alert", statusKey: "alertmanager" },
    ],
  },
  {
    key: "developer",
    label: "DEVELOPER",
    panels: [
      { id: "github_app", label: "GitHub App", icon: "git", statusKey: "github" },
      { id: "claude_code", label: "Claude Code", icon: "anchor", statusKey: "claude_code" },
    ],
  },
  {
    key: "security",
    label: "SECURITY",
    panels: [{ id: "sanitization", label: "Sanitization", icon: "shield" }],
  },
  {
    key: "advanced",
    label: "ADVANCED",
    panels: [
      { id: "mcp_bridge", label: "MCP Bridge", icon: "bridge" },
      { id: "mcp_servers", label: "MCP Servers", icon: "stack" },
      { id: "credentials", label: "Credentials", icon: "key" },
      { id: "raw_config", label: "Raw Config", icon: "code" },
    ],
  },
];

export function findPanel(id: string): { panel: CatalogPanel; category: CatalogCategory } | null {
  for (const cat of PANEL_CATEGORIES) {
    const panel = cat.panels.find((p) => p.id === id);
    if (panel) return { panel, category: cat };
  }
  return null;
}

export function totalPanelCount(): number {
  return PANEL_CATEGORIES.reduce((n, c) => n + c.panels.length, 0);
}

// Map raw admin-store IntegrationStatus (ok / error / unconfigured) to the
// design system's PanelStatus enum. Panels without a statusKey fall back to
// "neutral".
export function mapStatus(raw?: { status?: string } | undefined): PanelStatus {
  const s = raw?.status;
  if (s === "ok") return "connected";
  if (s === "error") return "error";
  if (s === "unconfigured") return "disconnected";
  return "neutral";
}
