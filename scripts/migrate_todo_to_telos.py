"""One-shot migration from the deprecated todo tables (`tasks`, `projects`)
into Telos sections (`projects`, `project_tasks`).

Safe to run on any database — reads raw SQL (no Python dependency on the
deleted todo module) and is idempotent via the `legacy_task_id` /
`legacy_project_id` metadata keys on the Telos rows.

    uv run python -m scripts.migrate_todo_to_telos

Behavior:
- For each row in the old `projects` table: find (or create) the matching
  Telos project by name (first content line == project.name, case-sensitive).
  If a Telos project is freshly created, its `metadata.legacy_project_id`
  records the old UUID so re-runs are no-ops.
- For each row in the old `tasks` table with `status ∈ {backlog, inprogress,
  done}`: insert into `project_tasks` with
  `metadata.legacy_task_id = task_id`. Skip if a row with that legacy_task_id
  already exists.
- Old rows are *not* deleted; the old todo tables remain inert.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from radbot.db.connection import get_db_connection, get_db_cursor
from radbot.tools.telos import db as telos_db
from radbot.tools.telos.models import Section

log = logging.getLogger("migrate_todo_to_telos")


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
        (name,),
    )
    return bool(cur.fetchone()[0])


def _existing_legacy_project_refs() -> dict[str, str]:
    """Return {legacy_project_id_uuid: telos_ref_code} from existing Telos projects."""
    out: dict[str, str] = {}
    for p in telos_db.list_section(Section.PROJECTS, status=None):
        legacy = (p.metadata or {}).get("legacy_project_id")
        if legacy and p.ref_code:
            out[str(legacy)] = p.ref_code
    return out


def _existing_legacy_task_ids() -> set[str]:
    ids: set[str] = set()
    for t in telos_db.list_section(Section.PROJECT_TASKS, status=None):
        legacy = (t.metadata or {}).get("legacy_task_id")
        if legacy:
            ids.add(str(legacy))
    return ids


def _telos_project_by_name() -> dict[str, str]:
    """First-line content -> ref_code, lowercased for matching."""
    out: dict[str, str] = {}
    for p in telos_db.list_section(Section.PROJECTS, status="active"):
        first = (p.content or "").splitlines()[0].strip().lower()
        if first and p.ref_code:
            out[first] = p.ref_code
    return out


def main() -> int:
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cur:
            if not _table_exists(cur, "tasks") or not _table_exists(cur, "projects"):
                log.info("Old todo tables not present — nothing to migrate.")
                return 0
            cur.execute("SELECT project_id, name FROM projects")
            old_projects: list[tuple[Any, str]] = list(cur.fetchall())
            cur.execute(
                "SELECT task_id, project_id, description, title, status, category, "
                "origin, related_info, created_at FROM tasks"
            )
            old_tasks: list[tuple] = list(cur.fetchall())

    log.info("old projects=%d  old tasks=%d", len(old_projects), len(old_tasks))

    legacy_to_ref = _existing_legacy_project_refs()
    name_to_ref = _telos_project_by_name()
    inserted_projects = 0

    for project_id, name in old_projects:
        key = str(project_id)
        if key in legacy_to_ref:
            continue
        existing_ref = name_to_ref.get((name or "").strip().lower())
        if existing_ref:
            telos_db.update_entry(
                Section.PROJECTS,
                existing_ref,
                metadata_merge={"legacy_project_id": key},
            )
            legacy_to_ref[key] = existing_ref
            log.info("linked legacy project %s → %s (%s)", key, existing_ref, name)
        else:
            row = telos_db.add_entry(
                Section.PROJECTS,
                name,
                metadata={"legacy_project_id": key},
            )
            legacy_to_ref[key] = row.ref_code or ""
            inserted_projects += 1
            log.info("created Telos project %s from legacy %s (%s)", row.ref_code, key, name)

    already = _existing_legacy_task_ids()
    inserted_tasks = 0
    skipped_status = 0

    for task_id, project_id, description, title, status, category, origin, related_info, created_at in old_tasks:
        tid = str(task_id)
        if tid in already:
            continue
        if status not in ("backlog", "inprogress", "done"):
            skipped_status += 1
            continue
        parent_ref = legacy_to_ref.get(str(project_id))
        if not parent_ref:
            log.warning("task %s has no parent project mapping; skipping", tid)
            continue
        meta: dict[str, Any] = {
            "parent_project": parent_ref,
            "task_status": status,
            "legacy_task_id": tid,
        }
        if title:
            meta["title"] = title
        if category:
            meta["category"] = category
        if origin:
            meta["origin"] = origin
        if related_info:
            # psycopg2 may deliver this as dict already; ensure JSON-safe.
            try:
                meta["related_info"] = (
                    related_info if isinstance(related_info, (dict, list))
                    else json.loads(related_info)
                )
            except Exception:
                meta["related_info"] = str(related_info)
        telos_db.add_entry(
            Section.PROJECT_TASKS,
            description or (title or "(no description)"),
            metadata=meta,
        )
        inserted_tasks += 1

    log.info(
        "done: inserted_projects=%d inserted_tasks=%d skipped_status=%d",
        inserted_projects, inserted_tasks, skipped_status,
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    sys.exit(main())
