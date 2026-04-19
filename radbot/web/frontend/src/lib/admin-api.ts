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

// ── Telos ────────────────────────────────────────────────
export interface TelosEntry {
  entry_id: string;
  section: string;
  ref_code: string | null;
  content: string;
  metadata: Record<string, any>;
  status: string;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface TelosStatus {
  has_identity: boolean;
}

export interface TelosBulkEntry {
  section: string;
  content: string;
  ref_code?: string | null;
  metadata?: Record<string, any>;
  status?: string;
  sort_order?: number;
}

export async function telosGetStatus(token: string): Promise<TelosStatus> {
  return adminFetch("/api/telos/status", { token });
}

export async function telosGetSection(
  token: string,
  section: string,
  includeInactive = false,
): Promise<{ section: string; entries: TelosEntry[] }> {
  const qs = includeInactive ? "?include_inactive=true" : "";
  return adminFetch(`/api/telos/section/${encodeURIComponent(section)}${qs}`, { token });
}

export async function telosAddEntry(
  token: string,
  section: string,
  body: { content: string; ref_code?: string | null; metadata?: Record<string, any>; status?: string; sort_order?: number },
): Promise<TelosEntry> {
  return adminFetch(`/api/telos/entry/${encodeURIComponent(section)}`, {
    token,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function telosUpdateEntry(
  token: string,
  section: string,
  refCode: string,
  patch: { content?: string; metadata_merge?: Record<string, any>; metadata_replace?: Record<string, any>; status?: string; sort_order?: number },
): Promise<TelosEntry> {
  return adminFetch(`/api/telos/entry/${encodeURIComponent(section)}/${encodeURIComponent(refCode)}`, {
    token,
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export async function telosArchive(
  token: string,
  section: string,
  refCode: string,
  reason?: string,
): Promise<{ status: string }> {
  return adminFetch(`/api/telos/archive/${encodeURIComponent(section)}/${encodeURIComponent(refCode)}`, {
    token,
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export async function telosBulk(
  token: string,
  entries: TelosBulkEntry[],
  replace = false,
): Promise<{ status: string; inserted_or_updated: number; replaced: boolean }> {
  return adminFetch("/api/telos/bulk", {
    token,
    method: "POST",
    body: JSON.stringify({ entries, replace }),
  });
}

export async function telosImportMarkdown(
  token: string,
  markdown: string,
  replace = false,
): Promise<{ status: string; imported: number; replaced: boolean }> {
  return adminFetch("/api/telos/import", {
    token,
    method: "POST",
    body: JSON.stringify({ markdown, replace }),
  });
}

export async function telosExportMarkdown(token: string): Promise<string> {
  const res = await fetch("/api/telos/export", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

export async function telosResolvePrediction(
  token: string,
  refCode: string,
  outcome: boolean,
  actualValue?: string,
): Promise<{ status: string; miscalibrated: boolean; entry: TelosEntry | null }> {
  return adminFetch(`/api/telos/resolve-prediction/${encodeURIComponent(refCode)}`, {
    token,
    method: "POST",
    body: JSON.stringify({ outcome, actual_value: actualValue ?? null }),
  });
}

// ── MCP bridge ───────────────────────────────────────────

export interface McpStatus {
  auth_configured: boolean;
  token_source: "credential_store" | "env" | "";
  token_masked: string;
  wiki_path: string;
  wiki_mounted: boolean;
  sse_url: string;
  setup_url: string;
}

export interface McpProject {
  name: string;
  path_patterns: string[];
  wiki_path: string | null;
}

export async function getMcpStatus(token: string): Promise<McpStatus> {
  return adminFetch("/api/mcp/status", { token });
}

export async function revealMcpToken(token: string): Promise<{ token: string; source: string }> {
  return adminFetch("/api/mcp/token/reveal", { token });
}

export async function rotateMcpToken(token: string): Promise<{ token: string; source: string }> {
  return adminFetch("/api/mcp/token/rotate", { token, method: "POST" });
}

export async function listMcpProjects(token: string): Promise<McpProject[]> {
  return adminFetch("/api/mcp/projects", { token });
}

export async function upsertMcpProject(token: string, project: McpProject): Promise<McpProject> {
  return adminFetch("/api/mcp/projects", {
    token,
    method: "POST",
    body: JSON.stringify(project),
  });
}

export async function deleteMcpProject(token: string, name: string): Promise<{ deleted: string }> {
  return adminFetch(`/api/mcp/projects/${encodeURIComponent(name)}`, {
    token,
    method: "DELETE",
  });
}
