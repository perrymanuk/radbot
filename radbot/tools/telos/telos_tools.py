"""Agent tools for reading and updating the Telos user-context store.

All tools return ``{"status": "success", ...}`` or
``{"status": "error", "message": ...}`` per radbot convention.

Silent vs. confirm-required distinctions are enforced by the agent's
instructions (``main_agent.md``), not here. These functions just do what
they're asked.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.tools.shared.errors import truncate_error

from . import db as telos_db
from .markdown_io import parse_telos_markdown, render_telos_markdown
from .models import IDENTITY_REF, STATUS_VALUES, Entry, Section

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section_or_error(section: str):
    try:
        return Section(section), None
    except ValueError:
        valid = ", ".join(s.value for s in Section)
        return None, {
            "status": "error",
            "message": f"Unknown section {section!r}. Valid: {valid}.",
        }


def _serialize_entry(entry: Entry) -> Dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "section": entry.section.value,
        "ref_code": entry.ref_code,
        "content": entry.content,
        "metadata": entry.metadata,
        "status": entry.status,
        "sort_order": entry.sort_order,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def _wrap(label: str, fn, *args, **kwargs) -> Dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        msg = f"Failed to {label}: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": truncate_error(msg)}


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


def telos_get_section(section: str, include_inactive: bool = False) -> Dict[str, Any]:
    """
    Return all entries in a Telos section.

    Valid sections: identity, history, problems, mission, narratives, goals,
    challenges, strategies, projects, wisdom, ideas, predictions,
    wrong_about, best_books, best_movies, best_music, taste, traumas,
    metrics, journal.

    Args:
        section: The Telos section name (lowercase).
        include_inactive: If True, include completed/archived/superseded
            entries. Default False (active only).

    Returns:
        {"status": "success", "section": str, "entries": [...]} on success.
    """
    sec, err = _section_or_error(section)
    if err:
        return err

    def _do():
        status = None if include_inactive else "active"
        order = "created_at_desc" if sec == Section.JOURNAL else "sort_order_asc"
        entries = telos_db.list_section(sec, status=status, order_by=order)
        return {
            "status": "success",
            "section": sec.value,
            "entries": [_serialize_entry(e) for e in entries],
        }

    return _wrap(f"list section {section}", _do)


def telos_get_entry(section: str, ref_code: str) -> Dict[str, Any]:
    """
    Fetch one Telos entry by (section, ref_code). Use to look up the full
    record of a goal, problem, etc. you already know the ref_code for
    (e.g. "G1", "P2", "PRED3"). Identity uses ref_code "ME".
    """
    sec, err = _section_or_error(section)
    if err:
        return err

    def _do():
        entry = telos_db.get_entry(sec, ref_code)
        if not entry:
            return {
                "status": "error",
                "message": f"No entry {ref_code} in {sec.value}.",
            }
        return {"status": "success", "entry": _serialize_entry(entry)}

    return _wrap(f"get entry {section}:{ref_code}", _do)


def telos_get_full() -> Dict[str, Any]:
    """
    Return the full Telos as canonical markdown. Use sparingly — this can be
    large. Prefer telos_get_section when you only need a specific section.
    """

    def _do():
        entries = telos_db.list_all()
        md = render_telos_markdown(entries)
        return {"status": "success", "markdown": md, "entry_count": len(entries)}

    return _wrap("render full telos", _do)


def telos_search_journal(query: str, limit: int = 20) -> Dict[str, Any]:
    """
    ILIKE search over journal content. Returns newest entries first.
    Useful for "have I ever mentioned X?" questions.

    Args:
        query: Substring to match (case-insensitive).
        limit: Max results to return. Default 20.
    """

    def _do():
        rows = telos_db.search_journal(query, limit=limit)
        return {
            "status": "success",
            "entries": [_serialize_entry(e) for e in rows],
        }

    return _wrap("search journal", _do)


# ---------------------------------------------------------------------------
# Silent-update tools (agent may call without user confirmation per main_agent.md)
# ---------------------------------------------------------------------------


def telos_add_journal(
    entry: str,
    event_type: str = "",
    related_refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Append a journal entry. Use for notable events, decisions, states, or
    interactions worth remembering. No confirmation needed.

    Args:
        entry: Free-form text describing what happened.
        event_type: Optional tag (e.g. "decision", "milestone", "mood",
            "interaction"). Stored in metadata.
        related_refs: Optional list of ref_codes this journal entry relates
            to (e.g. ["G1", "PRJ3"]). Stored in metadata.
    """

    def _do():
        metadata: Dict[str, Any] = {}
        if event_type:
            metadata["event_type"] = event_type
        if related_refs:
            metadata["related_refs"] = list(related_refs)
        row = telos_db.add_entry(Section.JOURNAL, entry, metadata=metadata)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add journal", _do)


def telos_add_prediction(
    claim: str,
    probability: float,
    deadline: str = "",
) -> Dict[str, Any]:
    """
    Record a prediction the user made with an attached probability and
    optional deadline. Use whenever the user voices a forecast with a
    confidence ("I'd bet 80% X", "by June there's a 60% chance Y"). No
    confirmation needed.

    Args:
        claim: The predicted outcome as a single sentence.
        probability: 0.0 to 1.0.
        deadline: Optional ISO date ("2026-12-31") for when this resolves.
    """

    def _do():
        if not 0.0 <= probability <= 1.0:
            return {
                "status": "error",
                "message": "probability must be between 0.0 and 1.0.",
            }
        metadata: Dict[str, Any] = {"probability": probability}
        if deadline:
            metadata["deadline"] = deadline
        row = telos_db.add_entry(Section.PREDICTIONS, claim, metadata=metadata)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add prediction", _do)


def telos_resolve_prediction(
    ref_code: str,
    outcome: bool,
    actual_value: str = "",
) -> Dict[str, Any]:
    """
    Mark a prediction as resolved with the outcome. If the user was
    miscalibrated (confident and wrong, OR dismissive and right), also
    appends an entry to wrong_about silently.

    Args:
        ref_code: The PRED<N> ref_code to resolve.
        outcome: True if the prediction came true, False otherwise.
        actual_value: Optional description of what actually happened.
    """

    def _do():
        existing = telos_db.get_entry(Section.PREDICTIONS, ref_code)
        if not existing:
            return {"status": "error", "message": f"No prediction {ref_code}."}
        prob = (existing.metadata or {}).get("probability")
        meta = {
            "resolution": "true" if outcome else "false",
            "resolved_at": _now_iso(),
        }
        if actual_value:
            meta["actual_value"] = actual_value
        updated = telos_db.update_entry(
            Section.PREDICTIONS,
            ref_code,
            status="completed",
            metadata_merge=meta,
        )

        # Miscalibration: confident-and-wrong OR dismissive-and-right.
        miscalibrated = False
        if isinstance(prob, (int, float)):
            if (not outcome and prob >= 0.75) or (outcome and prob <= 0.25):
                miscalibrated = True
        if miscalibrated:
            note = (
                f"Miscalibrated on {ref_code}: predicted "
                f"{prob:.0%} for {existing.content!r}; outcome was "
                f"{'true' if outcome else 'false'}."
            )
            telos_db.add_entry(
                Section.WRONG_ABOUT,
                note,
                metadata={"source_prediction": ref_code},
            )

        return {
            "status": "success",
            "entry": _serialize_entry(updated) if updated else None,
            "miscalibrated": miscalibrated,
        }

    return _wrap("resolve prediction", _do)


def telos_note_wrong(thing: str, why: str = "") -> Dict[str, Any]:
    """
    Record that the user was wrong about something. Use when the user
    concedes "I was wrong about X" or corrects a prior belief. No
    confirmation needed.

    Args:
        thing: What the user was wrong about, one sentence.
        why: Optional explanation of what actually turned out to be true.
    """

    def _do():
        content = thing if not why else f"{thing} — {why}"
        row = telos_db.add_entry(Section.WRONG_ABOUT, content)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("note wrong", _do)


def telos_note_taste(
    category: str,
    item: str,
    sentiment: str,
    note: str = "",
) -> Dict[str, Any]:
    """
    Record a strong taste/preference. Use when the user expresses a clear
    opinion about a book, movie, song, food, tool, game, etc. No
    confirmation needed.

    Args:
        category: "book" | "movie" | "music" | "food" | "tool" | "game" | "other"
        item: The name of the item (title, brand, etc.).
        sentiment: "love" | "like" | "dislike" | "hate" | "neutral"
        note: Optional short comment explaining the sentiment.
    """

    def _do():
        metadata = {"category": category, "sentiment": sentiment}
        if note:
            metadata["note"] = note
        target_section = {
            "book": Section.BEST_BOOKS,
            "movie": Section.BEST_MOVIES,
            "music": Section.BEST_MUSIC,
        }.get(category, Section.TASTE)
        row = telos_db.add_entry(target_section, item, metadata=metadata)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("note taste", _do)


def telos_add_wisdom(principle: str, origin: str = "") -> Dict[str, Any]:
    """
    Record a principle or rule the user lives by. Use when the user
    voices something quotable they'd want remembered (e.g., "always X",
    "never Y", "if in doubt, Z"). No confirmation needed.

    Args:
        principle: The principle as a single quotable sentence.
        origin: Optional source/attribution.
    """

    def _do():
        metadata = {"origin": origin} if origin else {}
        row = telos_db.add_entry(Section.WISDOM, principle, metadata=metadata)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add wisdom", _do)


def telos_add_idea(idea: str) -> Dict[str, Any]:
    """
    Record a strong opinion, hot-take, or idea the user has voiced.
    No confirmation needed.
    """

    def _do():
        row = telos_db.add_entry(Section.IDEAS, idea)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add idea", _do)


# ---------------------------------------------------------------------------
# Confirm-required tools (agent must propose and get user yes per main_agent.md)
# ---------------------------------------------------------------------------


def telos_upsert_identity(
    content: str,
    name: str = "",
    location: str = "",
    role: str = "",
    pronouns: str = "",
) -> Dict[str, Any]:
    """
    Upsert the user's Identity entry (single record). Use when the user
    states or updates who they are. Confirmation REQUIRED — propose the
    change in a plain sentence first.

    Args:
        content: The full identity description (can be multi-line prose).
        name: Optional structured name field.
        location: Optional structured location field.
        role: Optional structured role/occupation field.
        pronouns: Optional structured pronouns field.
    """

    def _do():
        metadata = {
            k: v
            for k, v in {
                "name": name,
                "location": location,
                "role": role,
                "pronouns": pronouns,
            }.items()
            if v
        }
        row = telos_db.upsert_singleton(
            Section.IDENTITY, IDENTITY_REF, content, metadata
        )
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("upsert identity", _do)


def telos_add_entry(
    section: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    ref_code: str = "",
) -> Dict[str, Any]:
    """
    Generic add for structural sections (problems, mission, narratives,
    goals, challenges, strategies, projects, metrics). Confirmation REQUIRED.

    For goals pass metadata like {"deadline": "2026-12-31", "kpi": "100k users"}.
    For projects pass {"priority": "high", "parent_goal": "G1"}.
    For problems/missions/narratives metadata is usually empty.

    Use the specialized tools (telos_add_goal, telos_add_problem, etc.)
    when you want clearer semantics; this is the escape hatch.
    """
    sec, err = _section_or_error(section)
    if err:
        return err

    def _do():
        row = telos_db.add_entry(
            sec,
            content,
            ref_code=ref_code or None,
            metadata=metadata or {},
        )
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap(f"add {section}", _do)


def telos_update_entry(
    section: str,
    ref_code: str,
    content: str = "",
    metadata_merge: Optional[Dict[str, Any]] = None,
    status: str = "",
) -> Dict[str, Any]:
    """
    Update one entry's content/metadata/status. Confirmation REQUIRED for
    structural sections; for journal/predictions/taste etc. you typically
    use the specialized silent tools instead.

    Args:
        section: Target section.
        ref_code: Entry to update.
        content: New content (empty string = leave unchanged).
        metadata_merge: Shallow JSONB merge into existing metadata.
        status: "active" | "completed" | "archived" | "superseded" (empty = leave).
    """
    sec, err = _section_or_error(section)
    if err:
        return err

    def _do():
        kwargs: Dict[str, Any] = {}
        if content:
            kwargs["content"] = content
        if metadata_merge:
            kwargs["metadata_merge"] = metadata_merge
        if status:
            if status not in STATUS_VALUES:
                return {
                    "status": "error",
                    "message": f"invalid status {status!r}. Valid: {sorted(STATUS_VALUES)}.",
                }
            kwargs["status"] = status
        row = telos_db.update_entry(sec, ref_code, **kwargs)
        if not row:
            return {
                "status": "error",
                "message": f"No entry {ref_code} in {sec.value}.",
            }
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap(f"update {section}:{ref_code}", _do)


def telos_add_goal(
    title: str,
    deadline: str = "",
    kpi: str = "",
    parent_problem: str = "",
) -> Dict[str, Any]:
    """
    Add a goal. Confirmation REQUIRED. Auto-assigns G<N> ref_code.
    """

    def _do():
        metadata = {
            k: v
            for k, v in {
                "deadline": deadline,
                "kpi": kpi,
                "parent_problem": parent_problem,
            }.items()
            if v
        }
        row = telos_db.add_entry(Section.GOALS, title, metadata=metadata)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add goal", _do)


def telos_complete_goal(ref_code: str, resolution: str = "") -> Dict[str, Any]:
    """
    Mark a goal completed and write a journal entry noting the completion.
    Confirmation REQUIRED.
    """

    def _do():
        meta = {"completed_at": _now_iso()}
        if resolution:
            meta["resolution"] = resolution
        updated = telos_db.update_entry(
            Section.GOALS,
            ref_code,
            status="completed",
            metadata_merge=meta,
        )
        if not updated:
            return {"status": "error", "message": f"No goal {ref_code}."}
        journal_body = f"Completed {ref_code}: {updated.content}" + (
            f" — {resolution}" if resolution else ""
        )
        telos_db.add_entry(
            Section.JOURNAL,
            journal_body,
            metadata={"event_type": "goal_completed", "related_refs": [ref_code]},
        )
        return {"status": "success", "entry": _serialize_entry(updated)}

    return _wrap(f"complete goal {ref_code}", _do)


def telos_archive(section: str, ref_code: str, reason: str = "") -> Dict[str, Any]:
    """
    Archive an entry (soft delete). Confirmation REQUIRED — never archive
    without explicit user approval.
    """
    sec, err = _section_or_error(section)
    if err:
        return err

    def _do():
        ok = telos_db.archive_entry(sec, ref_code, reason=reason or None)
        if not ok:
            return {
                "status": "error",
                "message": f"No entry {ref_code} in {sec.value}.",
            }
        return {"status": "success", "archived": f"{sec.value}:{ref_code}"}

    return _wrap(f"archive {section}:{ref_code}", _do)


def telos_import_markdown(markdown_text: str, replace: bool = False) -> Dict[str, Any]:
    """
    Bulk-load a Telos markdown file. Parses canonical Telos format (## SECTION
    headers with `- REF: content` bullets) and upserts into the DB.

    Args:
        markdown_text: The full markdown content.
        replace: If True, wipe ALL existing entries first. Default False
            (merge into existing; entries with the same ref_code are
            updated, new ones are added).

    Confirmation REQUIRED when replace=True. Merge mode can go silently if
    the user provided the content.
    """

    def _do():
        entries = parse_telos_markdown(markdown_text)
        if not entries:
            return {
                "status": "error",
                "message": "Parsed zero entries — input may not be canonical Telos markdown.",
            }
        if replace:
            telos_db.reset_all()
        rows = telos_db.bulk_upsert(entries)
        return {
            "status": "success",
            "imported": len(rows),
            "replaced": replace,
        }

    return _wrap("import markdown", _do)


# ---------------------------------------------------------------------------
# Project-task tools (replace the deprecated tools/todo module)
# ---------------------------------------------------------------------------

_VALID_TASK_STATUSES = {"backlog", "inprogress", "done"}


def _require_project(ref_code: str):
    """Return (entry, None) if the project exists; else (None, error_dict)."""
    project = telos_db.get_entry(Section.PROJECTS, ref_code)
    if not project:
        return None, {
            "status": "error",
            "message": f"No project {ref_code}. Use telos_list_projects first.",
        }
    return project, None


def telos_list_projects() -> Dict[str, Any]:
    """List active Telos projects. Returns ref_code, name (first content line),
    and metadata. Use before adding a task/milestone/exploration so you know
    the parent_project ref.
    """

    def _do():
        rows = telos_db.list_section(Section.PROJECTS, status="active")
        out = []
        for p in rows:
            name = (p.content or "").splitlines()[0].strip()
            out.append(
                {
                    "ref_code": p.ref_code,
                    "name": name,
                    "metadata": p.metadata,
                }
            )
        return {"status": "success", "projects": out}

    return _wrap("list projects", _do)


def telos_get_project(ref_or_name: str) -> Dict[str, Any]:
    """Render a project hierarchy as a single payload: the project itself
    plus all its milestones, tasks (grouped by task_status), explorations,
    and linked goals. ref_or_name is the ref_code ("PRJ1") or a substring of
    the project name.
    """

    def _do():
        # Resolve by ref_code first, then by name substring.
        needle = ref_or_name.strip()
        project = telos_db.get_entry(Section.PROJECTS, needle)
        if project is None:
            for p in telos_db.list_section(Section.PROJECTS, status="active"):
                first = (p.content or "").splitlines()[0].lower()
                if needle.lower() in first:
                    project = p
                    break
        if project is None:
            return {"status": "error", "message": f"Unknown project: {ref_or_name!r}."}

        ref = project.ref_code

        def _children(section: Section):
            return [
                _serialize_entry(e)
                for e in telos_db.list_section(section, status="active")
                if (e.metadata or {}).get("parent_project") == ref
            ]

        tasks = _children(Section.PROJECT_TASKS)
        grouped: Dict[str, list] = {"backlog": [], "inprogress": [], "done": []}
        for t in tasks:
            status_key = (t.get("metadata") or {}).get("task_status") or "backlog"
            grouped.setdefault(status_key, []).append(t)

        return {
            "status": "success",
            "project": _serialize_entry(project),
            "milestones": _children(Section.MILESTONES),
            "tasks": grouped,
            "explorations": _children(Section.EXPLORATIONS),
            "goals": [
                _serialize_entry(g)
                for g in telos_db.list_section(Section.GOALS, status="active")
                if (g.metadata or {}).get("parent_project") == ref
            ],
        }

    return _wrap(f"get project {ref_or_name}", _do)


def telos_add_milestone(
    title: str,
    parent_project: str,
    deadline: str = "",
    details: str = "",
) -> Dict[str, Any]:
    """Add a milestone under a project. Confirmation REQUIRED.
    Auto-assigns MS<N>.

    Args:
        title: Milestone title (one line).
        parent_project: ref_code of the parent project (e.g. "PRJ1").
        deadline: Optional ISO date.
        details: Optional multi-line description appended below the title.
    """

    def _do():
        _p, err = _require_project(parent_project)
        if err:
            return err
        content = title if not details else f"{title}\n\n{details}"
        metadata: Dict[str, Any] = {"parent_project": parent_project}
        if deadline:
            metadata["deadline"] = deadline
        row = telos_db.add_entry(Section.MILESTONES, content, metadata=metadata)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add milestone", _do)


def telos_complete_milestone(ref_code: str, resolution: str = "") -> Dict[str, Any]:
    """Mark a milestone completed. No confirmation needed — routine update."""

    def _do():
        meta = {"completed_at": _now_iso()}
        if resolution:
            meta["resolution"] = resolution
        row = telos_db.update_entry(
            Section.MILESTONES,
            ref_code,
            status="completed",
            metadata_merge=meta,
        )
        if not row:
            return {"status": "error", "message": f"No milestone {ref_code}."}
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap(f"complete milestone {ref_code}", _do)


def telos_add_task(
    description: str,
    parent_project: str,
    parent_milestone: str = "",
    title: str = "",
    category: str = "",
    task_status: str = "backlog",
) -> Dict[str, Any]:
    """Create a project task under an existing Telos project (and optionally
    a milestone). Confirmation REQUIRED. Auto-assigns PT<N>.

    Args:
        description: Full task description.
        parent_project: ref_code of the parent project (e.g. "PRJ1").
        parent_milestone: Optional ref_code of a milestone (e.g. "MS2").
        title: Optional short title.
        category: Optional tag ("bug", "feature", "chore", …).
        task_status: "backlog" | "inprogress" | "done". Default "backlog".
    """

    def _do():
        if task_status not in _VALID_TASK_STATUSES:
            return {
                "status": "error",
                "message": (
                    f"invalid task_status {task_status!r}. "
                    f"Valid: {sorted(_VALID_TASK_STATUSES)}."
                ),
            }
        _p, err = _require_project(parent_project)
        if err:
            return err
        if parent_milestone:
            ms = telos_db.get_entry(Section.MILESTONES, parent_milestone)
            if not ms:
                return {
                    "status": "error",
                    "message": f"No milestone {parent_milestone}.",
                }
        metadata: Dict[str, Any] = {
            "parent_project": parent_project,
            "task_status": task_status,
        }
        if parent_milestone:
            metadata["parent_milestone"] = parent_milestone
        if title:
            metadata["title"] = title
        if category:
            metadata["category"] = category
        row = telos_db.add_entry(Section.PROJECT_TASKS, description, metadata=metadata)
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add task", _do)


def telos_list_tasks(
    parent_project: str = "",
    parent_milestone: str = "",
    task_status: str = "",
    include_inactive: bool = False,
) -> Dict[str, Any]:
    """List project tasks, optionally filtered by parent project, milestone,
    and/or kanban status."""

    def _do():
        status = None if include_inactive else "active"
        rows = telos_db.list_section(
            Section.PROJECT_TASKS, status=status, order_by="sort_order_asc"
        )
        out = []
        for r in rows:
            meta = r.metadata or {}
            if parent_project and meta.get("parent_project") != parent_project:
                continue
            if parent_milestone and meta.get("parent_milestone") != parent_milestone:
                continue
            if task_status and meta.get("task_status") != task_status:
                continue
            out.append(_serialize_entry(r))
        return {"status": "success", "entries": out}

    return _wrap("list tasks", _do)


def telos_complete_task(ref_code: str) -> Dict[str, Any]:
    """Mark a project task as done (sets metadata.task_status='done').
    No confirmation needed — completing a task is routine.
    """

    def _do():
        row = telos_db.update_entry(
            Section.PROJECT_TASKS,
            ref_code,
            metadata_merge={"task_status": "done", "completed_at": _now_iso()},
        )
        if not row:
            return {"status": "error", "message": f"No task {ref_code}."}
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap(f"complete task {ref_code}", _do)


def telos_archive_task(ref_code: str, reason: str = "") -> Dict[str, Any]:
    """Archive (soft-delete) a project task. Confirmation REQUIRED."""

    def _do():
        ok = telos_db.archive_entry(
            Section.PROJECT_TASKS, ref_code, reason=reason or None
        )
        if not ok:
            return {"status": "error", "message": f"No task {ref_code}."}
        return {"status": "success", "archived": f"project_tasks:{ref_code}"}

    return _wrap(f"archive task {ref_code}", _do)


def telos_add_exploration(
    topic: str,
    parent_project: str,
    notes: str = "",
) -> Dict[str, Any]:
    """Record an open exploration / research thread under a project.
    Confirmation REQUIRED. Auto-assigns EX<N>.

    Use for things that aren't tasks yet — "I want to look into X" captures
    here, and a follow-up task/milestone can be promoted from it later.
    """

    def _do():
        _p, err = _require_project(parent_project)
        if err:
            return err
        content = topic if not notes else f"{topic}\n\n{notes}"
        row = telos_db.add_entry(
            Section.EXPLORATIONS,
            content,
            metadata={"parent_project": parent_project},
        )
        return {"status": "success", "entry": _serialize_entry(row)}

    return _wrap("add exploration", _do)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Tool wrappers
# ---------------------------------------------------------------------------

# Read tools
telos_get_section_tool = FunctionTool(telos_get_section)
telos_get_entry_tool = FunctionTool(telos_get_entry)
telos_get_full_tool = FunctionTool(telos_get_full)
telos_search_journal_tool = FunctionTool(telos_search_journal)

# Silent-update tools
telos_add_journal_tool = FunctionTool(telos_add_journal)
telos_add_prediction_tool = FunctionTool(telos_add_prediction)
telos_resolve_prediction_tool = FunctionTool(telos_resolve_prediction)
telos_note_wrong_tool = FunctionTool(telos_note_wrong)
telos_note_taste_tool = FunctionTool(telos_note_taste)
telos_add_wisdom_tool = FunctionTool(telos_add_wisdom)
telos_add_idea_tool = FunctionTool(telos_add_idea)

# Confirm-required tools
telos_upsert_identity_tool = FunctionTool(telos_upsert_identity)
telos_add_entry_tool = FunctionTool(telos_add_entry)
telos_update_entry_tool = FunctionTool(telos_update_entry)
telos_add_goal_tool = FunctionTool(telos_add_goal)
telos_complete_goal_tool = FunctionTool(telos_complete_goal)
telos_archive_tool = FunctionTool(telos_archive)
telos_import_markdown_tool = FunctionTool(telos_import_markdown)

# Project hierarchy tools (replace the deprecated tools/todo module)
telos_list_projects_tool = FunctionTool(telos_list_projects)
telos_get_project_tool = FunctionTool(telos_get_project)
telos_add_milestone_tool = FunctionTool(telos_add_milestone)
telos_complete_milestone_tool = FunctionTool(telos_complete_milestone)
telos_add_task_tool = FunctionTool(telos_add_task)
telos_list_tasks_tool = FunctionTool(telos_list_tasks)
telos_complete_task_tool = FunctionTool(telos_complete_task)
telos_archive_task_tool = FunctionTool(telos_archive_task)
telos_add_exploration_tool = FunctionTool(telos_add_exploration)


TELOS_TOOLS = [
    # read
    telos_get_section_tool,
    telos_get_entry_tool,
    telos_get_full_tool,
    telos_search_journal_tool,
    # silent
    telos_add_journal_tool,
    telos_add_prediction_tool,
    telos_resolve_prediction_tool,
    telos_note_wrong_tool,
    telos_note_taste_tool,
    telos_add_wisdom_tool,
    telos_add_idea_tool,
    # confirm-required
    telos_upsert_identity_tool,
    telos_add_entry_tool,
    telos_update_entry_tool,
    telos_add_goal_tool,
    telos_complete_goal_tool,
    telos_archive_tool,
    telos_import_markdown_tool,
    # project hierarchy (replaces the old tools/todo module)
    telos_list_projects_tool,
    telos_get_project_tool,
    telos_add_milestone_tool,
    telos_complete_milestone_tool,
    telos_add_task_tool,
    telos_list_tasks_tool,
    telos_complete_task_tool,
    telos_archive_task_tool,
    telos_add_exploration_tool,
]


# Scoped subset for scout. Covers the "ground a plan in the user's goals,
# explore past journal entries, and write the finished plan as an exploration
# plus actionable project_tasks" workflow. Excludes identity/goal mutation,
# archiving, and project meta-management — those stay on beto.
SCOUT_TELOS_TOOLS = [
    # read: ground plans in the user's persona + project context
    telos_get_section_tool,
    telos_get_entry_tool,
    telos_get_full_tool,
    telos_search_journal_tool,
    telos_list_projects_tool,
    telos_get_project_tool,
    telos_list_tasks_tool,
    # plan writes
    telos_add_exploration_tool,
    telos_add_task_tool,
    telos_add_milestone_tool,
    telos_add_journal_tool,
]
