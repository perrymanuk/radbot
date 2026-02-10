import type {
  Session,
  Task,
  Project,
  AgentEvent,
  AgentInfo,
  Message,
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

export async function createSession(name?: string): Promise<Session> {
  const sessionId = crypto.randomUUID();
  return json("/api/sessions/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, name: name || `Session ${sessionId.slice(0, 8)}` }),
  });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${BASE}/api/sessions/${sessionId}`, { method: "DELETE" });
}

export async function renameSession(
  sessionId: string,
  name: string,
): Promise<void> {
  await fetch(`${BASE}/api/sessions/${sessionId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

// ── Messages ──────────────────────────────────────────────
export async function fetchMessages(
  sessionId: string,
  limit = 50,
): Promise<Message[]> {
  return json(`/api/sessions/${sessionId}/messages?limit=${limit}`);
}

// ── Tasks ─────────────────────────────────────────────────
export async function fetchTasks(): Promise<Task[]> {
  return json("/api/tasks");
}

export async function createTask(data: {
  title: string;
  description?: string;
  project_id: string;
  status?: string;
  category?: string;
}): Promise<{ task_id: string }> {
  return json("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateTask(
  taskId: string,
  data: Partial<Pick<Task, "title" | "description" | "status" | "project_id">>,
): Promise<void> {
  await fetch(`${BASE}/api/tasks/${taskId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  await fetch(`${BASE}/api/tasks/${taskId}`, { method: "DELETE" });
}

// ── Projects ──────────────────────────────────────────────
export async function fetchProjects(): Promise<Project[]> {
  return json("/api/projects");
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

// ── Health ────────────────────────────────────────────────
export async function healthCheck(): Promise<{ status: string }> {
  return json("/health");
}
