/** Telos public read API client — no auth, matches the rest of /api/*.
 * For admin-authed telos writes, use `admin-api.ts`. */

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

export interface ProjectSummary {
  ref_code: string;
  title: string;
  status: string;
  milestone_count: number;
  active_task_count: number;
  done_task_count: number;
  sort_order: number;
  updated_at: string | null;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function listProjectsSummary(): Promise<ProjectSummary[]> {
  const data = await getJson<{ projects: ProjectSummary[] }>(
    "/api/telos/projects/summary",
  );
  return data.projects;
}

export const PROJECT_SECTIONS = [
  "projects",
  "milestones",
  "project_tasks",
  "explorations",
  "goals",
] as const;

export type ProjectSection = (typeof PROJECT_SECTIONS)[number];

export async function listProjectEntries(
  sections: readonly ProjectSection[] = PROJECT_SECTIONS,
  includeInactive = false,
): Promise<Record<string, TelosEntry[]>> {
  const qs = new URLSearchParams({
    sections: sections.join(","),
  });
  if (includeInactive) qs.set("include_inactive", "true");
  const data = await getJson<{ sections: Record<string, TelosEntry[]> }>(
    `/api/telos/projects/entries?${qs}`,
  );
  return data.sections;
}

export function entryKey(section: string, refCode: string): string {
  return `${section}:${refCode}`;
}
