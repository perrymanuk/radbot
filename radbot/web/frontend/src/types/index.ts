// ── Messages ──────────────────────────────────────────────
export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  agent?: string | null;
}

// ── Sessions ──────────────────────────────────────────────
export interface Session {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
  last_message_at?: string | null;
  preview?: string | null;
}

// ── Agent Events ──────────────────────────────────────────
export type EventCategory =
  | "tool_call"
  | "model_response"
  | "agent_transfer"
  | "planner"
  | "system"
  | "other";

export interface AgentEvent {
  id?: string;
  type: string;
  category: EventCategory;
  summary?: string;
  text?: string;
  timestamp: string;
  agent_name?: string;
  is_final?: boolean;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_response?: string;
  from_agent?: string;
  to_agent?: string;
  steps?: string[];
  raw?: Record<string, unknown>;
}

// ── WebSocket ─────────────────────────────────────────────
export type ConnectionStatus =
  | "connecting"
  | "active"
  | "thinking"
  | "reconnecting"
  | "disconnected"
  | "error";

export interface WSMessage {
  type: "message" | "status" | "events" | "heartbeat" | "history" | "sync_response" | "notification";
  content?: string | Message[] | AgentEvent[];
  messages?: Message[];
}

// ── Notifications ────────────────────────────────────────
export type NotificationType = "scheduled_task" | "reminder" | "alert" | "ntfy_outbound";

export interface Notification {
  notification_id: string;
  type: NotificationType;
  title: string;
  message: string;
  source_id?: string;
  session_id?: string;
  priority: string;
  read: boolean;
  metadata?: Record<string, unknown>;
  created_at: string;
}

// ── Panels ────────────────────────────────────────────────
export type PanelType = "sessions" | "events" | null;

// ── Agent Info ────────────────────────────────────────────
export interface SubAgentDetail {
  name: string;         // runtime agent name (e.g. "casa", "scout")
  config_key: string;   // canonical key in agent_models (e.g. "casa_agent")
  resolved_model: string;
  gemini_only: boolean; // true for search_agent / code_execution_agent
}

export interface AgentInfo {
  name: string;
  model: string;
  sub_agents: string[];
  sub_agents_detail?: SubAgentDetail[];
  agent_models?: Record<string, string>;
  tools?: string[];
}
