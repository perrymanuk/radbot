"""Database operations for the Telos user-context store.

Single table `telos_entries` backs all sections. Section-specific fields
live in JSONB `metadata`. Reuses the shared PostgreSQL pool from
`radbot.db.connection`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from radbot.db.connection import get_db_connection, get_db_cursor

from .models import REF_PREFIX, STATUS_VALUES, Entry, Section

logger = logging.getLogger(__name__)


def init_telos_schema() -> None:
    """Create the telos_entries table (idempotent)."""
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
    one is auto-assigned."""
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
        json.dumps(metadata or {}),
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
    status: Optional[str] = "active",
    limit: Optional[int] = None,
    order_by: str = "sort_order_asc",
) -> List[Entry]:
    """List entries in a section.

    `status=None` returns all statuses. Default "active".
    `order_by` options: sort_order_asc (default), created_at_desc,
    created_at_asc.
    """
    where = ["section = %s"]
    params: List[Any] = [section.value]
    if status is not None:
        where.append("status = %s")
        params.append(status)
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
