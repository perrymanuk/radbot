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
  created_at: string;
  last_message_at?: string | null;
  preview?: string | null;
}

// ── Tasks ─────────────────────────────────────────────────
export type TaskStatus = "backlog" | "in_progress" | "done";

export interface Task {
  task_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  project_id: string;
  project_name?: string;
  category?: string;
  priority?: number;
  created_at: string;
  updated_at: string;
}

export interface Project {
  project_id: string;
  name: string;
  description?: string;
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
  type: "message" | "status" | "events" | "heartbeat" | "history" | "sync_response";
  content?: string | Message[] | AgentEvent[];
  messages?: Message[];
}

// ── Panels ────────────────────────────────────────────────
export type PanelType = "sessions" | "tasks" | "events" | null;

// ── Agent Info ────────────────────────────────────────────
export interface AgentInfo {
  name: string;
  model: string;
  sub_agents: string[];
  tools: string[];
}
