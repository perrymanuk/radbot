import type {
  Session,
  SessionAgent,
  AgentEvent,
  AgentInfo,
  Message,
  Notification,
} from "@/types";

const BASE = "";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ── Sessions ──────────────────────────────────────────────
export async function fetchSessions(): Promise<Session[]> {
  const data = await json<{ sessions: Session[] }>("/api/sessions/");
  return data.sessions;
}

export async function createSession(
  name?: string,
  description?: string,
  agentName: SessionAgent = "beto",
): Promise<Session> {
  const sessionId = crypto.randomUUID();
  return json("/api/sessions/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      name: name || `Session ${sessionId.slice(0, 8)}`,
      ...(description && { description }),
      agent_name: agentName,
    }),
  });
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/api/sessions/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

export async function updateSession(
  sessionId: string,
  data: { name?: string; description?: string },
): Promise<void> {
  await fetch(`${BASE}/api/sessions/${sessionId}/rename`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function renameSession(
  sessionId: string,
  name: string,
): Promise<void> {
  await updateSession(sessionId, { name });
}

export async function autoNameSession(
  sessionId: string,
): Promise<
  | { status: "success"; name: string }
  | { status: "error"; detail: string }
> {
  const res = await fetch(`${BASE}/api/sessions/${sessionId}/auto-name`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return res.json();
}

// ── Messages ──────────────────────────────────────────────
export async function fetchMessages(
  sessionId: string,
  limit = 50,
): Promise<Message[]> {
  return json(`/api/sessions/${sessionId}/messages?limit=${limit}`);
}

// ── Events ────────────────────────────────────────────────
export async function fetchEvents(
  sessionId: string,
): Promise<AgentEvent[]> {
  return json(`/api/events?session_id=${sessionId}`);
}

// ── Agent Info ────────────────────────────────────────────
export async function fetchAgentInfo(): Promise<AgentInfo> {
  return json("/api/agent-info");
}

// ── Session stats ─────────────────────────────────────────
export interface SessionStatsResponse {
  inputTokens: number;
  outputTokens: number;
  contextTokens: number;
  contextWindow: number;
  model: string;
  costUsd: number;
  costTodayUsd: number;
  costMonthUsd: number;
}

export async function fetchSessionStats(
  sessionId: string,
): Promise<SessionStatsResponse> {
  return json(`/api/sessions/${sessionId}/stats`);
}

// ── TTS ───────────────────────────────────────────────────
export async function synthesizeSpeech(
  text: string,
): Promise<ArrayBuffer> {
  const res = await fetch(`${BASE}/api/tts/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`TTS error: ${res.status}`);
  return res.arrayBuffer();
}

// ── STT ───────────────────────────────────────────────────
export async function transcribeAudio(
  audioBlob: Blob,
): Promise<{ text: string }> {
  const formData = new FormData();
  formData.append("audio", audioBlob);
  return json("/api/stt/transcribe", {
    method: "POST",
    body: formData,
  });
}

// ── Notifications ────────────────────────────────────────
export async function fetchNotifications(params?: {
  type?: string;
  read?: string;
  limit?: number;
  offset?: number;
}): Promise<{ notifications: Notification[]; total: number }> {
  const q = new URLSearchParams();
  if (params?.type) q.set("type", params.type);
  if (params?.read) q.set("read", params.read);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return json(`/api/notifications/${qs ? `?${qs}` : ""}`);
}

export async function fetchUnreadCount(): Promise<{ count: number }> {
  return json("/api/notifications/unread-count");
}

export async function markNotificationRead(id: string): Promise<void> {
  await fetch(`${BASE}/api/notifications/${id}/read`, { method: "POST" });
}

export async function markAllNotificationsRead(type?: string): Promise<void> {
  await fetch(`${BASE}/api/notifications/read-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(type ? { type } : {}),
  });
}

export async function deleteNotification(id: string): Promise<void> {
  await fetch(`${BASE}/api/notifications/${id}`, { method: "DELETE" });
}

// ── Health ────────────────────────────────────────────────
export async function healthCheck(): Promise<{ status: string }> {
  return json("/health");
}
