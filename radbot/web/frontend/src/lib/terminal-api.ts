import type { Workspace, TerminalSession, TerminalStatus } from "@/types/terminal";

const BASE = "";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchWorkspaces(): Promise<Workspace[]> {
  const data = await json<{ workspaces: Workspace[] }>("/terminal/workspaces/");
  return data.workspaces;
}

export async function createTerminalSession(
  workspaceId: string,
  resumeSessionId?: string,
): Promise<TerminalSession> {
  return json("/terminal/sessions/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: workspaceId,
      resume_session_id: resumeSessionId,
    }),
  });
}

export async function listTerminalSessions(): Promise<TerminalSession[]> {
  const data = await json<{ sessions: TerminalSession[] }>("/terminal/sessions/");
  return data.sessions;
}

export async function killTerminalSession(terminalId: string): Promise<void> {
  await fetch(`${BASE}/terminal/sessions/${terminalId}`, { method: "DELETE" });
}

export async function cloneRepository(
  owner: string,
  repo: string,
  branch: string = "main",
): Promise<{ status: string; message?: string }> {
  return json("/terminal/clone/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner, repo, branch }),
  });
}

export async function getTerminalStatus(): Promise<TerminalStatus> {
  return json("/terminal/status/");
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  const res = await fetch(`${BASE}/terminal/workspaces/${workspaceId}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
}

export async function updateWorkspace(
  workspaceId: string,
  data: { name?: string; description?: string },
): Promise<void> {
  const res = await fetch(`${BASE}/terminal/workspaces/${workspaceId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
}

export async function createScratchWorkspace(
  name?: string,
  description?: string,
): Promise<Workspace> {
  const data = await json<{ workspace: Workspace }>("/terminal/workspaces/scratch/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
  return data.workspace;
}
