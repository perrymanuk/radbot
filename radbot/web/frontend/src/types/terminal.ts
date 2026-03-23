export interface Workspace {
  workspace_id: string;
  owner: string;
  repo: string;
  branch: string;
  local_path: string;
  status: string;
  last_session_id: string | null;
  created_at: string;
  last_used_at: string;
  name: string | null;
  description: string | null;
  worker_status?: "running" | "starting" | "stopped" | "unhealthy" | null;
  worker_uptime_seconds?: number | null;
  worker_idle_seconds?: number | null;
  worker_sessions?: number | null;
}

export interface TerminalSession {
  terminal_id: string;
  workspace_id: string;
  owner: string;
  repo: string;
  branch: string;
  pid: number;
  closed?: boolean;
}

export interface TerminalStatus {
  status: string;
  message: string;
  cli_available: boolean;
  token_configured: boolean;
}
