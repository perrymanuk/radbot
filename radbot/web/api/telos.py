"""REST API for the Telos user-context store.

Protected by the admin bearer token (same mechanism as `admin.py` and
`alerts.py`). Drives both the onboarding wizard and the normal editor in
the admin panel, and supports markdown import/export for power users.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from radbot.tools.telos import db as telos_db
from radbot.tools.telos.markdown_io import (
    parse_telos_markdown,
    render_telos_markdown,
)
from radbot.tools.telos.models import (
    IDENTITY_REF,
    REF_PREFIX,
    SECTION_HEADERS,
    STATUS_VALUES,
    Entry,
    Section,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telos", tags=["telos"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> None:
    expected = os.environ.get("RADBOT_ADMIN_TOKEN", "")
    if not expected:
        try:
            from radbot.config.config_loader import config_loader

            expected = config_loader.get_config().get("admin_token") or ""
        except Exception:
            pass
    if not expected:
        raise HTTPException(503, "Admin API disabled — RADBOT_ADMIN_TOKEN not set")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == expected:
        return
    raise HTTPException(401, "Invalid or missing admin bearer token")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(entry: Entry) -> Dict[str, Any]:
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


def _parse_section(name: str) -> Section:
    try:
        return Section(name)
    except ValueError:
        valid = ", ".join(s.value for s in Section)
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section {name!r}. Valid: {valid}.",
        )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class EntryInput(BaseModel):
    content: str
    ref_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    sort_order: int = 0


class EntryPatch(BaseModel):
    content: Optional[str] = None
    metadata_merge: Optional[Dict[str, Any]] = None
    metadata_replace: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class ArchiveInput(BaseModel):
    reason: Optional[str] = None


class BulkEntryInput(BaseModel):
    section: str
    content: str
    ref_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    sort_order: int = 0


class BulkInput(BaseModel):
    entries: List[BulkEntryInput]
    replace: bool = False


class ImportInput(BaseModel):
    markdown: str
    replace: bool = False


class ResolvePredictionInput(BaseModel):
    outcome: bool
    actual_value: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Public read endpoints (single-user radbot — unauth'd, matching the rest of
# /api/* for the logged-in web UI). Writes + sensitive sections stay gated
# by _require_admin below.
# ---------------------------------------------------------------------------


@router.get("/projects/summary")
async def projects_summary() -> Dict[str, Any]:
    """Flat list of projects with derived milestone/task counts. Feeds the
    `/projects` page left rail. Unauth'd read."""
    projects = telos_db.list_section(Section.PROJECTS, status=None)
    milestones = telos_db.list_section(Section.MILESTONES, status="active")
    tasks = telos_db.list_section(Section.PROJECT_TASKS, status="active")

    items = []
    for p in projects:
        if not p.ref_code:
            continue
        p_milestones = [
            m for m in milestones
            if (m.metadata or {}).get("parent_project") == p.ref_code
        ]
        p_tasks = [
            t for t in tasks
            if (t.metadata or {}).get("parent_project") == p.ref_code
        ]
        done = [
            t for t in p_tasks
            if (t.metadata or {}).get("task_status") == "done"
        ]
        active = [
            t for t in p_tasks
            if (t.metadata or {}).get("task_status") != "done"
        ]
        items.append({
            "ref_code": p.ref_code,
            "title": (p.content or "").splitlines()[0][:160] if p.content else p.ref_code,
            "status": p.status,
            "milestone_count": len(p_milestones),
            "active_task_count": len(active),
            "done_task_count": len(done),
            "sort_order": p.sort_order,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })
    items.sort(key=lambda x: (x["status"] != "active", x["sort_order"], x["ref_code"]))
    return {"projects": items}


_BULK_SECTIONS_DEFAULT = "projects,milestones,project_tasks,explorations,goals"


@router.get("/projects/entries")
async def projects_entries(
    sections: str = _BULK_SECTIONS_DEFAULT,
    include_inactive: bool = False,
) -> Dict[str, Any]:
    """Bulk-fetch multiple telos sections in one call. Feeds the `/projects`
    page detail panes. Unauth'd read. Unknown section names are skipped."""
    out: Dict[str, Any] = {}
    status = None if include_inactive else "active"
    for name in sections.split(","):
        name = name.strip()
        if not name:
            continue
        try:
            sec = Section(name)
        except ValueError:
            continue
        entries = telos_db.list_section(sec, status=status)
        out[sec.value] = [_serialize(e) for e in entries]
    return {"sections": out}


# ---------------------------------------------------------------------------
# Admin-authed endpoints (writes + sensitive sections)
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status(_auth: None = Depends(_require_admin)) -> Dict[str, Any]:
    """One-shot onboarding status. Drives the wizard-vs-editor branch."""
    return {
        "has_identity": telos_db.has_identity(),
    }


@router.get("/sections")
async def list_sections_meta(_auth: None = Depends(_require_admin)) -> Dict[str, Any]:
    """Per-section active entry counts and headers, for UI summaries."""
    grouped = telos_db.list_all_active()
    out = []
    for section in Section:
        out.append(
            {
                "section": section.value,
                "header": SECTION_HEADERS[section],
                "has_ref_codes": section in REF_PREFIX,
                "active_count": len(grouped.get(section, [])),
            }
        )
    return {"sections": out}


@router.get("/section/{section}")
async def get_section(
    section: str,
    include_inactive: bool = False,
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    sec = _parse_section(section)
    order = "created_at_desc" if sec == Section.JOURNAL else "sort_order_asc"
    status = None if include_inactive else "active"
    entries = telos_db.list_section(sec, status=status, order_by=order)
    return {
        "section": sec.value,
        "entries": [_serialize(e) for e in entries],
    }


@router.get("/entry/{section}/{ref_code}")
async def get_entry(
    section: str,
    ref_code: str,
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    sec = _parse_section(section)
    entry = telos_db.get_entry(sec, ref_code)
    if not entry:
        raise HTTPException(404, f"No entry {ref_code} in {sec.value}.")
    return _serialize(entry)


@router.post("/entry/{section}", status_code=201)
async def add_entry(
    section: str,
    body: EntryInput,
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    sec = _parse_section(section)
    if body.status not in STATUS_VALUES:
        raise HTTPException(400, f"Invalid status {body.status!r}.")
    entry = telos_db.add_entry(
        sec,
        body.content,
        ref_code=body.ref_code or None,
        metadata=body.metadata,
        status=body.status,
        sort_order=body.sort_order,
    )
    return _serialize(entry)


@router.put("/entry/{section}/{ref_code}")
async def update_entry(
    section: str,
    ref_code: str,
    body: EntryPatch,
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    sec = _parse_section(section)
    if body.metadata_merge is not None and body.metadata_replace is not None:
        raise HTTPException(
            400, "Pass at most one of metadata_merge / metadata_replace."
        )
    if body.status is not None and body.status not in STATUS_VALUES:
        raise HTTPException(400, f"Invalid status {body.status!r}.")
    entry = telos_db.update_entry(
        sec,
        ref_code,
        content=body.content,
        metadata_merge=body.metadata_merge,
        metadata_replace=body.metadata_replace,
        status=body.status,
        sort_order=body.sort_order,
    )
    if not entry:
        raise HTTPException(404, f"No entry {ref_code} in {sec.value}.")
    return _serialize(entry)


@router.post("/archive/{section}/{ref_code}")
async def archive_entry(
    section: str,
    ref_code: str,
    body: ArchiveInput = Body(default_factory=ArchiveInput),
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    sec = _parse_section(section)
    ok = telos_db.archive_entry(sec, ref_code, reason=body.reason)
    if not ok:
        raise HTTPException(404, f"No entry {ref_code} in {sec.value}.")
    return {"status": "archived", "section": sec.value, "ref_code": ref_code}


@router.post("/bulk")
async def bulk_upsert(
    body: BulkInput,
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    """Atomic multi-section upsert. Used by the onboarding wizard to save
    everything in one go. If `replace=True`, wipes all entries first."""
    entries: List[Entry] = []
    for item in body.entries:
        try:
            sec = Section(item.section)
        except ValueError:
            raise HTTPException(400, f"Unknown section {item.section!r}.")
        if item.status not in STATUS_VALUES:
            raise HTTPException(400, f"Invalid status {item.status!r}.")
        entries.append(
            Entry(
                section=sec,
                ref_code=item.ref_code,
                content=item.content,
                metadata=item.metadata or {},
                status=item.status,
                sort_order=item.sort_order,
            )
        )
    if body.replace:
        telos_db.reset_all()
    rows = telos_db.bulk_upsert(entries)
    return {
        "status": "success",
        "inserted_or_updated": len(rows),
        "replaced": body.replace,
    }


@router.post("/import")
async def import_markdown(
    body: ImportInput,
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    """Merge (or replace) Telos contents from canonical markdown."""
    entries = parse_telos_markdown(body.markdown)
    if not entries:
        raise HTTPException(
            400,
            "Parsed zero entries — input may not be canonical Telos markdown.",
        )
    if body.replace:
        telos_db.reset_all()
    rows = telos_db.bulk_upsert(entries)
    return {
        "status": "success",
        "imported": len(rows),
        "replaced": body.replace,
    }


@router.get("/export", response_class=PlainTextResponse)
async def export_markdown(_auth: None = Depends(_require_admin)) -> str:
    entries = telos_db.list_all()
    return render_telos_markdown(entries)


@router.post("/resolve-prediction/{ref_code}")
async def resolve_prediction(
    ref_code: str,
    body: ResolvePredictionInput,
    _auth: None = Depends(_require_admin),
) -> Dict[str, Any]:
    """Resolve a prediction and auto-record a wrong_about entry on strong
    miscalibration (confident and wrong, or dismissive and right)."""
    existing = telos_db.get_entry(Section.PREDICTIONS, ref_code)
    if not existing:
        raise HTTPException(404, f"No prediction {ref_code}.")
    prob = (existing.metadata or {}).get("probability")
    meta = {
        "resolution": "true" if body.outcome else "false",
    }
    if body.actual_value:
        meta["actual_value"] = body.actual_value
    updated = telos_db.update_entry(
        Section.PREDICTIONS,
        ref_code,
        status="completed",
        metadata_merge=meta,
    )

    miscalibrated = False
    if isinstance(prob, (int, float)):
        if (not body.outcome and prob >= 0.75) or (body.outcome and prob <= 0.25):
            miscalibrated = True

    if miscalibrated:
        telos_db.add_entry(
            Section.WRONG_ABOUT,
            f"Miscalibrated on {ref_code}: predicted {prob:.0%} for "
            f"{existing.content!r}; outcome was "
            f"{'true' if body.outcome else 'false'}.",
            metadata={"source_prediction": ref_code},
        )

    return {
        "status": "success",
        "entry": _serialize(updated) if updated else None,
        "miscalibrated": miscalibrated,
    }
