"""Build the two-tier Telos context injection strings.

`build_telos_tiers()` returns `(anchor, full_block)`:

* Anchor (~300 bytes, capped at 500) — goes into beto's `system_instruction`
  on every turn. Identity + Mission + counts + pointer to tools.
* Full block (~2KB, capped at 2048 bytes) — goes into `system_instruction`
  on the first turn of each session only. Identity + Mission + Problems +
  Goals + active Projects + Challenges + Wisdom + last 5 journal entries.

Both are empty strings on a fresh DB, in which case the callback is a
no-op.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from . import db as telos_db
from .models import IDENTITY_REF, Entry, Section

logger = logging.getLogger(__name__)

ANCHOR_CAP_BYTES = 500
FULL_BLOCK_CAP_BYTES = 2048


def build_telos_tiers() -> Tuple[str, str]:
    """Return (anchor_text, full_block_text)."""
    try:
        grouped = telos_db.list_all_active()
        journal = telos_db.recent_journal(limit=5)
    except Exception as e:
        logger.warning("Telos loader DB read failed (non-fatal): %s", e)
        return "", ""

    # If totally empty, return empty strings — callback will be a no-op.
    if not any(grouped[s] for s in grouped) and not journal:
        return "", ""

    identity = _first(grouped.get(Section.IDENTITY))
    missions = grouped.get(Section.MISSION, [])
    problems = grouped.get(Section.PROBLEMS, [])
    goals = grouped.get(Section.GOALS, [])
    projects = grouped.get(Section.PROJECTS, [])
    challenges = grouped.get(Section.CHALLENGES, [])
    wisdom = grouped.get(Section.WISDOM, [])

    anchor = _render_anchor(
        identity=identity,
        missions=missions,
        counts={
            "goals": len(goals),
            "projects": len(projects),
            "problems": len(problems),
            "challenges": len(challenges),
            "wisdom": len(wisdom),
            "journal": len(journal),
        },
    )
    full_block = _render_full_block(
        identity=identity,
        missions=missions,
        problems=problems,
        goals=goals,
        projects=projects,
        challenges=challenges,
        wisdom=wisdom,
        journal=journal,
    )
    return anchor, full_block


def _first(items):
    return items[0] if items else None


def _single_line(text: str, limit: int = 160) -> str:
    """Collapse a content block to a single line with a soft length cap."""
    collapsed = " ".join(text.split())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "…"
    return collapsed


def _render_anchor(*, identity, missions, counts) -> str:
    lines = ["TELOS ANCHOR"]
    if identity:
        lines.append(f"Identity: {_single_line(identity.content, 180)}")
    if missions:
        lines.append(f"Mission: {_single_line(missions[0].content, 180)}")
    parts = []
    for label, n in (
        ("goals", counts["goals"]),
        ("projects", counts["projects"]),
        ("problems", counts["problems"]),
        ("challenges", counts["challenges"]),
    ):
        if n:
            parts.append(f"{n} {label}")
    if parts:
        lines.append("Active: " + ", ".join(parts) + ".")
    lines.append(
        "Use telos_get_section(name) or telos_get_full() for detail;"
        " telos_get_section('traumas') only when relevant."
    )
    text = "\n".join(lines)
    if len(text.encode("utf-8")) > ANCHOR_CAP_BYTES:
        # Trim the final line first, then mission detail.
        lines = lines[:-1]
        text = "\n".join(lines)
        if len(text.encode("utf-8")) > ANCHOR_CAP_BYTES:
            text = text.encode("utf-8")[: ANCHOR_CAP_BYTES - 1].decode(
                "utf-8", errors="ignore"
            ) + "…"
    return text


def _render_full_block(
    *,
    identity,
    missions: List[Entry],
    problems: List[Entry],
    goals: List[Entry],
    projects: List[Entry],
    challenges: List[Entry],
    wisdom: List[Entry],
    journal: List[Entry],
) -> str:
    sections: List[Tuple[str, List[str]]] = []

    if identity:
        sections.append(("IDENTITY", [identity.content.strip()]))
    if missions:
        sections.append(("MISSION", [_bullet(m) for m in missions]))
    if problems:
        sections.append(("PROBLEMS", [_bullet(p) for p in problems]))
    if goals:
        sections.append(("GOALS", [_bullet(g) for g in goals]))
    if projects:
        sections.append(("ACTIVE PROJECTS", [_bullet(p) for p in projects]))
    if challenges:
        sections.append(("CHALLENGES", [_bullet(c) for c in challenges]))
    if wisdom:
        sections.append(("WISDOM", [_bullet(w) for w in wisdom]))
    if journal:
        sections.append(
            (
                "RECENT JOURNAL",
                [_journal_line(j) for j in journal],
            )
        )

    if not sections:
        return ""

    header = "USER CONTEXT (Telos) — full profile. Use for grounding beto in the user's current mission, goals, and recent state. Do not repeat verbatim to the user."
    body = _assemble(header, sections)

    # If over budget, drop journal entries from the tail first.
    if len(body.encode("utf-8")) > FULL_BLOCK_CAP_BYTES and sections and sections[-1][0] == "RECENT JOURNAL":
        journal_lines = sections[-1][1]
        while journal_lines and len(body.encode("utf-8")) > FULL_BLOCK_CAP_BYTES:
            journal_lines.pop()
            if journal_lines:
                sections[-1] = ("RECENT JOURNAL", journal_lines)
            else:
                sections.pop()
            body = _assemble(header, sections)

    # Final safety: hard-truncate if still over.
    if len(body.encode("utf-8")) > FULL_BLOCK_CAP_BYTES:
        body = body.encode("utf-8")[: FULL_BLOCK_CAP_BYTES - 1].decode(
            "utf-8", errors="ignore"
        ) + "…"

    return body


def _assemble(header: str, sections: List[Tuple[str, List[str]]]) -> str:
    parts = [header, ""]
    for title, items in sections:
        parts.append(f"{title}:")
        parts.extend(items)
        parts.append("")
    return "\n".join(parts).rstrip()


def _bullet(entry: Entry) -> str:
    ref = f"{entry.ref_code}: " if entry.ref_code else ""
    body = _single_line(entry.content, 200)
    # Append metadata hints inline for goals/projects.
    meta = entry.metadata or {}
    hints = []
    if "deadline" in meta and meta["deadline"]:
        hints.append(f"by {meta['deadline']}")
    if "kpi" in meta and meta["kpi"]:
        hints.append(f"kpi={meta['kpi']}")
    if "priority" in meta and meta["priority"]:
        hints.append(f"priority={meta['priority']}")
    suffix = f" ({', '.join(hints)})" if hints else ""
    return f"- {ref}{body}{suffix}"


def _journal_line(entry: Entry) -> str:
    date = entry.created_at.date().isoformat() if entry.created_at else ""
    prefix = f"[{date}] " if date else ""
    return f"- {prefix}{_single_line(entry.content, 180)}"
