"""Database operations for the Telos user-context store.

Single table `telos_entries` backs all sections. Section-specific fields
live in JSONB `metadata`. Reuses the shared PostgreSQL pool from
`radbot.db.connection`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from radbot.db.connection import get_db_connection, get_db_cursor

from .models import ACTIVE_EQUIVALENT, REF_PREFIX, STATUS_VALUES, Entry, Section

logger = logging.getLogger(__name__)


# Sentinel for `list_section` to distinguish "argument omitted" from
# "explicitly None" (which preserves the legacy "all statuses" semantics).
_OMITTED: Any = object()

_STATUS_CHECK_NAME = "telos_entries_status_check"


def init_telos_schema() -> None:
    """Create the telos_entries table (idempotent) and apply sibling
    migrations (GIN index on metadata, status CHECK constraint).

    The two sibling steps run unconditionally on every web startup. They are
    idempotent: `CREATE INDEX IF NOT EXISTS` is a no-op when the index
    exists, and `_apply_status_check_constraint` short-circuits when the
    existing CHECK definition's allowed-status set already matches
    `STATUS_VALUES` (semantic comparison — Round 3 council blocker fix
    against `pg_get_constraintdef` byte-string brittleness).
    """
    from radbot.tools.shared.db_schema import init_table_schema

    init_table_schema(
        table_name="telos_entries",
        create_table_sql="""
            CREATE TABLE telos_entries (
                entry_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                section      TEXT NOT NULL,
                ref_code     TEXT,
                content      TEXT NOT NULL,
                metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
                status       TEXT NOT NULL DEFAULT 'active',
                sort_order   INTEGER NOT NULL DEFAULT 0,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (section, ref_code)
            );
        """,
        create_index_sqls=[
            "CREATE INDEX idx_telos_section_status ON telos_entries (section, status);",
            "CREATE INDEX idx_telos_active ON telos_entries (section) WHERE status = 'active';",
            "CREATE INDEX idx_telos_journal_recent ON telos_entries (created_at DESC) WHERE section = 'journal';",
        ],
    )
    _apply_metadata_gin_index()
    _apply_status_check_constraint()


def _apply_metadata_gin_index() -> None:
    """Ensure the GIN index on telos_entries.metadata exists. Idempotent.

    Sibling step inside `init_telos_schema` rather than an entry in
    `init_table_schema`'s `create_index_sqls` list, because the latter only
    fires when the table is freshly created — which would silently skip the
    index on every existing deployment.
    """
    with get_db_connection() as conn:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_telos_metadata "
                "ON telos_entries USING GIN (metadata);"
            )


def _extract_constraint_status_set(constraint_def: str) -> set[str]:
    """Parse `pg_get_constraintdef` output and return the allowed status set.

    Robust against PG normalization variations:
      - "CHECK ((status = ANY (ARRAY['active'::text, 'completed'::text, ...])))"
      - "CHECK (status IN ('active', 'completed', ...))"
      - "CHECK ((status)::text = ANY ((ARRAY['active'::text, ...])::text[]))"
    All forms have the allowed values as single-quoted string literals;
    extract them.
    """
    return set(re.findall(r"'([^']+)'", constraint_def))


def _add_status_check(cursor, status_values: set[str]) -> None:
    """Emit `ALTER TABLE ADD CONSTRAINT` with quoted CSV values.

    `STATUS_VALUES` is a closed set defined in `models.py` (never user
    input), so the f-string interpolation is safe. `ALTER TABLE` does not
    accept parameterized constraint definitions, so we cannot use %s here.
    """
    quoted_csv = ", ".join(f"'{s}'" for s in sorted(status_values))
    cursor.execute(
        f"ALTER TABLE telos_entries ADD CONSTRAINT "
        f"{_STATUS_CHECK_NAME} CHECK (status IN ({quoted_csv}));"
    )


def _apply_status_check_constraint() -> None:
    """Ensure `telos_entries.status` CHECK constraint matches `STATUS_VALUES`.

    Idempotent + SEMANTICALLY definition-aware: replaces stale constraints
    whose allowed-status set doesn't match `STATUS_VALUES`. Compare by
    parsed SET (not by raw string) so PG normalization differences don't
    trigger spurious DROP+ADD cycles on every startup — `ALTER TABLE`
    takes an `ACCESS EXCLUSIVE` lock, so unnecessary cycles are wasteful
    and risky on large tables.

    Preflight: aborts with a clear error if any existing row carries a
    status outside the new set, so a half-finished rollback can't make the
    constraint apply silently fail later.
    """
    with get_db_connection() as conn:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(
                "SELECT COUNT(*), COALESCE(string_agg(DISTINCT status, ', '), '') "
                "FROM telos_entries WHERE status != ALL(%s);",
                (list(STATUS_VALUES),),
            )
            bad_count, bad_values = cursor.fetchone()
            if bad_count > 0:
                raise RuntimeError(
                    f"telos_entries has {bad_count} rows with statuses outside "
                    f"the new set: {bad_values}. Fix data before applying CHECK."
                )

            cursor.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = %s AND conrelid = 'telos_entries'::regclass;",
                (_STATUS_CHECK_NAME,),
            )
            row = cursor.fetchone()
            existing_def = row[0] if row else None

            if existing_def is None:
                _add_status_check(cursor, STATUS_VALUES)
                logger.info("Added telos_entries CHECK constraint")
                return

            existing_set = _extract_constraint_status_set(existing_def)
            if existing_set == set(STATUS_VALUES):
                return

            logger.info(
                "telos_entries CHECK constraint set mismatch; expected %s, got %s — replacing.",
                sorted(STATUS_VALUES),
                sorted(existing_set),
            )
            cursor.execute(
                f"ALTER TABLE telos_entries DROP CONSTRAINT {_STATUS_CHECK_NAME};"
            )
            _add_status_check(cursor, STATUS_VALUES)
            logger.info(
                "Replaced telos_entries CHECK constraint with current STATUS_VALUES"
            )


def _row_to_entry(row: Dict[str, Any]) -> Entry:
    return Entry(
        entry_id=str(row["entry_id"]),
        section=Section(row["section"]),
        ref_code=row["ref_code"],
        content=row["content"],
        metadata=row["metadata"] or {},
        status=row["status"],
        sort_order=row["sort_order"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def next_ref_code(section: Section) -> Optional[str]:
    """Compute the next auto-assigned ref_code for a section, or None if the
    section does not use ref_codes."""
    prefix = REF_PREFIX.get(section)
    if not prefix:
        return None
    sql = """
        SELECT ref_code FROM telos_entries
        WHERE section = %s AND ref_code LIKE %s
    """
    like = f"{prefix}%"
    max_n = 0
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (section.value, like))
            for (code,) in cursor.fetchall():
                if not code or not code.startswith(prefix):
                    continue
                tail = code[len(prefix) :]
                if tail.isdigit():
                    max_n = max(max_n, int(tail))
    return f"{prefix}{max_n + 1}"


def add_entry(
    section: Section,
    content: str,
    *,
    ref_code: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = "active",
    sort_order: int = 0,
) -> Entry:
    """Insert a new entry. If ref_code is None and the section uses ref_codes,
    one is auto-assigned.

    Postmortem invariant (enforced here, the lowest shared write layer, so
    every writer is covered — MCP `journal_add`, agent-side
    `telos_add_journal`, and direct `db.add_entry` calls): journal entries
    flagged as postmortems must include `metadata.processed_at` (initially
    `null`). Postgres JSONB `@>` matches `{"processed_at": null}` only when
    the key is explicitly present and serialized as null — a missing key
    does NOT match, which would silently break the
    `telos_get_section({metadata_filter: {processed_at: null}})` query that
    Scout's postmortem-processing pass depends on.
    """
    metadata = dict(metadata or {})

    if section == Section.JOURNAL and (
        metadata.get("type") == "postmortem"
        or metadata.get("event_type") == "postmortem"
    ):
        if "processed_at" not in metadata:
            raise ValueError(
                "postmortem journal entries must include metadata.processed_at "
                "(initially null) — this enables the unprocessed-postmortem query"
            )

    if status not in STATUS_VALUES:
        raise ValueError(f"invalid status {status!r}")
    if ref_code is None and section in REF_PREFIX:
        ref_code = next_ref_code(section)

    sql = """
        INSERT INTO telos_entries (section, ref_code, content, metadata, status, sort_order)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s)
        RETURNING *;
    """
    params = (
        section.value,
        ref_code,
        content,
        json.dumps(metadata),
        status,
        sort_order,
    )
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                conn.commit()
                return _row_to_entry(cursor.fetchone())
    except psycopg2.Error as e:
        logger.error("Database error adding telos entry: %s", e)
        raise


def update_entry(
    section: Section,
    ref_code: str,
    *,
    content: Optional[str] = None,
    metadata_merge: Optional[Dict[str, Any]] = None,
    metadata_replace: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
    sort_order: Optional[int] = None,
) -> Optional[Entry]:
    """Update one entry by (section, ref_code). Returns the updated Entry or
    None if no row matched. `metadata_merge` does a shallow JSONB merge;
    `metadata_replace` overwrites the whole metadata object. Pass at most
    one of the two."""
    if metadata_merge and metadata_replace is not None:
        raise ValueError("pass at most one of metadata_merge / metadata_replace")
    if status is not None and status not in STATUS_VALUES:
        raise ValueError(f"invalid status {status!r}")

    sets: List[str] = []
    params: List[Any] = []
    if content is not None:
        sets.append("content = %s")
        params.append(content)
    if metadata_replace is not None:
        sets.append("metadata = %s::jsonb")
        params.append(json.dumps(metadata_replace))
    elif metadata_merge:
        sets.append("metadata = metadata || %s::jsonb")
        params.append(json.dumps(metadata_merge))
    if status is not None:
        sets.append("status = %s")
        params.append(status)
    if sort_order is not None:
        sets.append("sort_order = %s")
        params.append(sort_order)

    if not sets:
        return get_entry(section, ref_code)

    sets.append("updated_at = CURRENT_TIMESTAMP")
    sql = f"""
        UPDATE telos_entries SET {", ".join(sets)}
        WHERE section = %s AND ref_code = %s
        RETURNING *;
    """
    params.extend([section.value, ref_code])
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, tuple(params))
                conn.commit()
                row = cursor.fetchone()
                return _row_to_entry(row) if row else None
    except psycopg2.Error as e:
        logger.error("Database error updating telos entry: %s", e)
        raise


def upsert_singleton(
    section: Section,
    ref_code: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Entry:
    """Upsert a single entry by (section, ref_code). Used for Identity."""
    existing = get_entry(section, ref_code)
    if existing:
        updated = update_entry(
            section,
            ref_code,
            content=content,
            metadata_replace=metadata or {},
        )
        assert updated is not None
        return updated
    return add_entry(section, content, ref_code=ref_code, metadata=metadata)


def get_entry(section: Section, ref_code: str) -> Optional[Entry]:
    sql = "SELECT * FROM telos_entries WHERE section = %s AND ref_code = %s;"
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (section.value, ref_code))
                row = cursor.fetchone()
                return _row_to_entry(row) if row else None
    except psycopg2.Error as e:
        logger.error("Database error fetching telos entry: %s", e)
        raise


def list_section(
    section: Section,
    *,
    status: Any = _OMITTED,
    status_in: Any = _OMITTED,
    limit: Optional[int] = None,
    order_by: str = "sort_order_asc",
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Entry]:
    """List entries in a section.

    Status semantics (sentinel pattern — closes the Round 3 council blocker
    on default-arg back-compat collision):
      - Both omitted → `ACTIVE_EQUIVALENT` (active + lifecycle-states).
      - `status="active"` → legacy single-status filter (back-compat).
      - `status=None` → all statuses (back-compat for the old `status=None`).
      - `status_in=None` → all statuses.
      - `status_in=[...]` → explicit set filter via `status = ANY(%s)`.
      - Both supplied with non-sentinel values → `ValueError`.

    `metadata_filter`, when non-empty, adds a JSONB `WHERE metadata @> %s`
    clause — supported by the GIN index on `metadata` (see
    `_apply_metadata_gin_index`).

    `order_by` options: sort_order_asc (default), created_at_desc,
    created_at_asc.
    """
    if status is not _OMITTED and status_in is not _OMITTED:
        raise ValueError("status and status_in are mutually exclusive")
    if status is _OMITTED and status_in is _OMITTED:
        status_in = ACTIVE_EQUIVALENT

    where: List[str] = ["section = %s"]
    params: List[Any] = [section.value]

    if status is not _OMITTED:
        if status is not None:
            where.append("status = %s")
            params.append(status)
    else:
        if status_in is not None:
            where.append("status = ANY(%s)")
            params.append(list(status_in))

    if metadata_filter:
        where.append("metadata @> %s::jsonb")
        params.append(json.dumps(metadata_filter))

    order_clause = {
        "sort_order_asc": "sort_order ASC, created_at ASC",
        "created_at_desc": "created_at DESC",
        "created_at_asc": "created_at ASC",
    }.get(order_by, "sort_order ASC, created_at ASC")

    sql = f"SELECT * FROM telos_entries WHERE {' AND '.join(where)} ORDER BY {order_clause}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    sql += ";"
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, tuple(params))
                return [_row_to_entry(r) for r in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error("Database error listing telos section: %s", e)
        raise


def archive_entry(
    section: Section, ref_code: str, reason: Optional[str] = None
) -> bool:
    """Set status='archived' and stash the reason in metadata.archived_reason."""
    meta = {"archived_reason": reason} if reason else {}
    row = update_entry(
        section,
        ref_code,
        status="archived",
        metadata_merge=meta if meta else None,
    )
    return row is not None


def archive_stale_done_tasks(since_days: int = 30) -> int:
    """Bulk-archive `project_tasks` rows that completed more than
    `since_days` ago. Returns count archived.

    Selection: `status='active'`, `metadata.task_status='done'`, and
    `metadata.completed_at` strictly older than `since_days` ago. Sets
    `status='archived'` and merges `archived_reason='auto_stale_done'` +
    `archived_at` into metadata. Run from the scheduler default-jobs
    pass (EX46 / PT115) so completed work moves out of the default
    `telos_list_tasks` view automatically.
    """
    if since_days < 0:
        raise ValueError("since_days must be >= 0")
    cutoff = f"NOW() - INTERVAL '{int(since_days)} days'"
    sql = f"""
        UPDATE telos_entries
        SET status = 'archived',
            metadata = metadata || jsonb_build_object(
                'archived_reason', 'auto_stale_done',
                'archived_at', to_char(now() at time zone 'utc',
                                       'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE section = 'project_tasks'
          AND status = 'active'
          AND metadata->>'task_status' = 'done'
          AND metadata ? 'completed_at'
          AND (metadata->>'completed_at')::timestamptz < {cutoff};
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                count = cursor.rowcount
                conn.commit()
                return int(count or 0)
    except psycopg2.Error as e:
        logger.error("Database error archiving stale done tasks: %s", e)
        raise


def search_journal(query: str, limit: int = 20) -> List[Entry]:
    """ILIKE search over journal content. Returns newest first."""
    like = f"%{query}%"
    sql = """
        SELECT * FROM telos_entries
        WHERE section = 'journal' AND content ILIKE %s
        ORDER BY created_at DESC
        LIMIT %s;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (like, int(limit)))
                return [_row_to_entry(r) for r in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error("Database error searching telos journal: %s", e)
        raise


def has_identity() -> bool:
    """True iff at least one identity entry exists. Used as the onboarding
    completion sentinel."""
    sql = "SELECT 1 FROM telos_entries WHERE section = 'identity' LIMIT 1;"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchone() is not None
    except psycopg2.Error as e:
        logger.error("Database error checking telos identity: %s", e)
        raise


def count_active(section: Section) -> int:
    sql = "SELECT COUNT(*) FROM telos_entries WHERE section = %s AND status = 'active';"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (section.value,))
                return cursor.fetchone()[0]
    except psycopg2.Error as e:
        logger.error("Database error counting telos section: %s", e)
        raise


def bulk_upsert(entries: Iterable[Entry]) -> List[Entry]:
    """Atomic multi-entry insert/update. Used by the onboarding wizard and
    markdown import. Each Entry: if (section, ref_code) exists, update
    content/metadata/status/sort_order; otherwise insert."""
    out: List[Entry] = []
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                for e in entries:
                    if e.ref_code:
                        sql = """
                            INSERT INTO telos_entries
                                (section, ref_code, content, metadata, status, sort_order)
                            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                            ON CONFLICT (section, ref_code) DO UPDATE SET
                                content = EXCLUDED.content,
                                metadata = EXCLUDED.metadata,
                                status = EXCLUDED.status,
                                sort_order = EXCLUDED.sort_order,
                                updated_at = CURRENT_TIMESTAMP
                            RETURNING *;
                        """
                        cursor.execute(
                            sql,
                            (
                                e.section.value,
                                e.ref_code,
                                e.content,
                                json.dumps(e.metadata or {}),
                                e.status,
                                e.sort_order,
                            ),
                        )
                    else:
                        # No ref_code: always insert as new (journal-style).
                        sql = """
                            INSERT INTO telos_entries
                                (section, content, metadata, status, sort_order)
                            VALUES (%s, %s, %s::jsonb, %s, %s)
                            RETURNING *;
                        """
                        cursor.execute(
                            sql,
                            (
                                e.section.value,
                                e.content,
                                json.dumps(e.metadata or {}),
                                e.status,
                                e.sort_order,
                            ),
                        )
                    out.append(_row_to_entry(cursor.fetchone()))
                conn.commit()
    except psycopg2.Error:
        logger.exception("Database error in telos bulk_upsert")
        raise
    return out


def reset_all(section: Optional[Section] = None) -> int:
    """Delete all entries, or all entries in one section. Returns the number
    of rows deleted. Used by the CLI reset command."""
    if section is not None:
        sql = "DELETE FROM telos_entries WHERE section = %s;"
        params: Tuple[Any, ...] = (section.value,)
    else:
        sql = "DELETE FROM telos_entries;"
        params = ()
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, params)
                return cursor.rowcount
    except psycopg2.Error as e:
        logger.error("Database error resetting telos entries: %s", e)
        raise


def list_all_active() -> Dict[Section, List[Entry]]:
    """Return all active entries grouped by section. Used by the loader."""
    sql = """
        SELECT * FROM telos_entries
        WHERE status = 'active'
        ORDER BY section, sort_order ASC, created_at ASC;
    """
    out: Dict[Section, List[Entry]] = {s: [] for s in Section}
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql)
                for row in cursor.fetchall():
                    e = _row_to_entry(row)
                    out[e.section].append(e)
    except psycopg2.Error as e:
        logger.error("Database error listing all telos entries: %s", e)
        raise
    return out


def list_all() -> List[Entry]:
    """Return every entry (any status, any section), ordered for export."""
    sql = """
        SELECT * FROM telos_entries
        ORDER BY section, sort_order ASC, created_at ASC;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql)
                return [_row_to_entry(r) for r in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error("Database error listing all telos entries: %s", e)
        raise


def recent_journal(limit: int = 5) -> List[Entry]:
    """Most recent active journal entries, newest first."""
    return list_section(
        Section.JOURNAL, status="active", limit=limit, order_by="created_at_desc"
    )
