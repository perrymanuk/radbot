/** Admin API client — all endpoints require bearer token auth. */

type FetchOpts = RequestInit & { token: string };

async function adminFetch<T>(path: string, opts: FetchOpts): Promise<T> {
  const { token, ...init } = opts;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(init.headers as Record<string, string> ?? {}),
  };
  if (init.body && typeof init.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

// ── Config ───────────────────────────────────────────────
export async function getLiveConfig(token: string): Promise<Record<string, any>> {
  return adminFetch("/admin/api/config-live", { token });
}

export async function getConfigSection(token: string, section: string): Promise<Record<string, any>> {
  return adminFetch(`/admin/api/config/${encodeURIComponent(section)}`, { token });
}

export async function saveConfigSection(token: string, section: string, data: Record<string, any>): Promise<void> {
  await adminFetch(`/admin/api/config/${encodeURIComponent(section)}`, {
    token,
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteConfigSection(token: string, section: string): Promise<void> {
  await adminFetch(`/admin/api/config/${encodeURIComponent(section)}`, {
    token,
    method: "DELETE",
  });
}

export async function getAllConfig(token: string): Promise<Record<string, any>> {
  return adminFetch("/admin/api/config", { token });
}

// ── Credentials ──────────────────────────────────────────
export interface CredentialEntry {
  name: string;
  credential_type: string;
  description?: string;
  encrypted: boolean;
  updated_at?: string;
}

export async function listCredentials(token: string): Promise<CredentialEntry[]> {
  return adminFetch("/admin/api/credentials", { token });
}

export async function storeCredential(
  token: string,
  name: string,
  value: string,
  credentialType = "api_key",
  description?: string,
): Promise<void> {
  await adminFetch("/admin/api/credentials", {
    token,
    method: "POST",
    body: JSON.stringify({ name, value, credential_type: credentialType, description }),
  });
}

export async function deleteCredential(token: string, name: string): Promise<void> {
  await adminFetch(`/admin/api/credentials/${encodeURIComponent(name)}`, {
    token,
    method: "DELETE",
  });
}

// ── Test Connections ─────────────────────────────────────
export interface TestResult {
  status: "ok" | "error";
  message: string;
}

export async function testConnection(
  token: string,
  endpoint: string,
  body: Record<string, any> = {},
): Promise<TestResult> {
  return adminFetch(`/admin/api/test/${endpoint}`, {
    token,
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Status ───────────────────────────────────────────────
export type IntegrationStatus = Record<string, { status: string; message?: string }>;

export async function getStatus(token: string): Promise<IntegrationStatus> {
  return adminFetch("/admin/api/status", { token });
}

// ── Models ──────────────────────────────────────────────
export async function listModels(token: string): Promise<string[]> {
  const data = await adminFetch<{ models: string[] }>("/admin/api/models", { token });
  return data.models;
}

// ── Telemetry / Cost Tracking ───────────────────────────
export interface CostSummary {
  total_requests: number;
  total_prompt_tokens: number;
  total_cached_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  total_cost_without_cache_usd: number;
}

export interface CostDashboard {
  year: number;
  month: number;
  summary: CostSummary;
  previous_month_cost_usd: number;
  daily: Array<{ day: string; requests: number; cost_usd: number; prompt_tokens: number; output_tokens: number }>;
  by_agent: Array<{ agent_name: string; requests: number; cost_usd: number; prompt_tokens: number; cached_tokens: number; output_tokens: number }>;
  by_model: Array<{ model: string; requests: number; cost_usd: number; prompt_tokens: number; cached_tokens: number; output_tokens: number }>;
  available_months: Array<{ month: string; requests: number; cost_usd: number }>;
}

export interface SessionUsageStats {
  uptime_seconds: number;
  total_requests: number;
  total_prompt_tokens: number;
  total_cached_tokens: number;
  total_output_tokens: number;
  cache_hit_rate_pct: number;
  estimated_cost_usd: number;
  estimated_cost_without_cache_usd: number;
  estimated_savings_usd: number;
  per_agent: Record<string, { prompt_tokens: number; cached_tokens: number; output_tokens: number; requests: number; cost_usd: number }>;
}

export async function getCostDashboard(token: string, year?: number, month?: number, label?: string): Promise<CostDashboard> {
  const params = new URLSearchParams();
  if (year) params.set("year", String(year));
  if (month) params.set("month", String(month));
  if (label) params.set("label", label);
  const qs = params.toString();
  return adminFetch(`/admin/api/telemetry/costs${qs ? `?${qs}` : ""}`, { token });
}

export async function getSessionUsage(token: string): Promise<SessionUsageStats> {
  return adminFetch("/admin/api/telemetry/usage", { token });
}

// ── Gmail ────────────────────────────────────────────────
export async function getGmailAccounts(token: string): Promise<{ accounts: any[]; error?: string }> {
  return adminFetch("/admin/api/gmail/accounts", { token });
}
