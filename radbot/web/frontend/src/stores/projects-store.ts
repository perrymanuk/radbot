import { create } from "zustand";
import {
  entryKey,
  listProjectEntries,
  listProjectsSummary,
  patchProjectTask,
  PROJECT_SECTIONS,
  type ProjectSection,
  type ProjectSummary,
  type ProjectTaskPatch,
  type TelosEntry,
} from "@/lib/telos-api";

interface ProjectsState {
  entries: Record<string, TelosEntry>; // key: "section:ref_code"
  childrenByParent: Record<string, string[]>; // parent ref_code -> entry keys
  summary: ProjectSummary[];
  loading: boolean;
  error: string | null;
  loaded: boolean;

  editingTaskRef: string | null;

  loadAll: () => Promise<void>;
  updateTask: (refCode: string, patch: ProjectTaskPatch) => Promise<TelosEntry>;
  openTaskEditor: (refCode: string) => void;
  closeTaskEditor: () => void;
}

function indexEntries(sections: Record<string, TelosEntry[]>) {
  const entries: Record<string, TelosEntry> = {};
  const childrenByParent: Record<string, string[]> = {};

  for (const [section, list] of Object.entries(sections)) {
    for (const e of list) {
      if (!e.ref_code) continue;
      const key = entryKey(section, e.ref_code);
      entries[key] = e;

      const meta = e.metadata || {};
      const parentMs = meta.parent_milestone as string | undefined;
      const parentPrj = meta.parent_project as string | undefined;
      const parent = parentMs || parentPrj;
      if (parent) {
        (childrenByParent[parent] ??= []).push(key);
      }
    }
  }

  return { entries, childrenByParent };
}

export const useProjectsStore = create<ProjectsState>((set, get) => ({
  entries: {},
  childrenByParent: {},
  summary: [],
  loading: false,
  error: null,
  loaded: false,
  editingTaskRef: null,

  openTaskEditor: (refCode) => set({ editingTaskRef: refCode }),
  closeTaskEditor: () => set({ editingTaskRef: null }),

  loadAll: async () => {
    set({ loading: true, error: null });
    try {
      const [sections, summary] = await Promise.all([
        listProjectEntries(PROJECT_SECTIONS),
        listProjectsSummary(),
      ]);
      const { entries, childrenByParent } = indexEntries(sections);
      set({ entries, childrenByParent, summary, loaded: true });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set({ loading: false });
    }
  },

  updateTask: async (refCode, patch) => {
    const key = entryKey("project_tasks", refCode);
    const prev = get().entries[key];
    // Optimistic: merge patch into local entry immediately
    if (prev) {
      const nextMeta =
        patch.metadata_merge !== undefined
          ? { ...(prev.metadata || {}), ...patch.metadata_merge }
          : prev.metadata;
      const optimistic: TelosEntry = {
        ...prev,
        content: patch.content !== undefined ? patch.content : prev.content,
        status: patch.status !== undefined ? patch.status : prev.status,
        metadata: nextMeta,
      };
      set({ entries: { ...get().entries, [key]: optimistic } });
    }
    try {
      const updated = await patchProjectTask(refCode, patch);
      set({ entries: { ...get().entries, [key]: updated } });
      return updated;
    } catch (e) {
      // Revert on error
      if (prev) {
        set({ entries: { ...get().entries, [key]: prev } });
      }
      throw e;
    }
  },
}));

// ── Selectors ──────────────────────────────────────────

export function selectProject(
  state: ProjectsState,
  refCode: string,
): TelosEntry | undefined {
  return state.entries[entryKey("projects", refCode)];
}

function filterByParent<T extends keyof any>(
  state: ProjectsState,
  section: ProjectSection,
  parentField: "parent_project" | "parent_milestone",
  parentRef: string,
): TelosEntry[] {
  const out: TelosEntry[] = [];
  for (const e of Object.values(state.entries)) {
    if (e.section !== section) continue;
    if ((e.metadata || {})[parentField] === parentRef) out.push(e);
  }
  out.sort((a, b) =>
    a.sort_order !== b.sort_order
      ? a.sort_order - b.sort_order
      : (a.ref_code || "").localeCompare(b.ref_code || ""),
  );
  return out;
}

export const selectMilestonesForProject = (s: ProjectsState, ref: string) =>
  filterByParent(s, "milestones", "parent_project", ref);

export const selectTasksForProject = (s: ProjectsState, ref: string) =>
  filterByParent(s, "project_tasks", "parent_project", ref);

export const selectTasksForMilestone = (s: ProjectsState, ref: string) =>
  filterByParent(s, "project_tasks", "parent_milestone", ref);

export const selectExplorationsForProject = (s: ProjectsState, ref: string) =>
  filterByParent(s, "explorations", "parent_project", ref);

export const selectGoalsForProject = (s: ProjectsState, ref: string) =>
  filterByParent(s, "goals", "parent_project", ref);

/** Tasks belonging to a project but not attached to any milestone. */
export function selectUnmilestonedTasks(s: ProjectsState, ref: string): TelosEntry[] {
  return selectTasksForProject(s, ref).filter(
    (t) => !(t.metadata || {}).parent_milestone,
  );
}

export type TaskStatusBucket = "inprogress" | "backlog" | "done" | "other";

export function bucketTasks(tasks: TelosEntry[]): Record<TaskStatusBucket, TelosEntry[]> {
  const out: Record<TaskStatusBucket, TelosEntry[]> = {
    inprogress: [],
    backlog: [],
    done: [],
    other: [],
  };
  for (const t of tasks) {
    const raw = ((t.metadata || {}).task_status || "").toString().toLowerCase();
    if (raw === "inprogress" || raw === "in_progress" || raw === "in progress") {
      out.inprogress.push(t);
    } else if (raw === "done" || raw === "complete" || raw === "completed") {
      out.done.push(t);
    } else if (raw === "backlog" || raw === "todo" || raw === "pending" || raw === "") {
      out.backlog.push(t);
    } else {
      out.other.push(t);
    }
  }
  return out;
}

/** Entries whose parent ref_code points at a project/milestone that isn't in
 * the store — data integrity red flag. */
export function selectOrphans(s: ProjectsState): TelosEntry[] {
  const knownProjects = new Set<string>();
  const knownMilestones = new Set<string>();
  for (const e of Object.values(s.entries)) {
    if (!e.ref_code) continue;
    if (e.section === "projects") knownProjects.add(e.ref_code);
    else if (e.section === "milestones") knownMilestones.add(e.ref_code);
  }
  const out: TelosEntry[] = [];
  for (const e of Object.values(s.entries)) {
    const meta = e.metadata || {};
    const parentPrj = meta.parent_project as string | undefined;
    const parentMs = meta.parent_milestone as string | undefined;
    if (parentPrj && !knownProjects.has(parentPrj)) {
      out.push(e);
      continue;
    }
    if (parentMs && !knownMilestones.has(parentMs)) {
      out.push(e);
    }
  }
  return out;
}
