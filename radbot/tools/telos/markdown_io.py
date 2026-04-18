"""Canonical Telos markdown parse + render.

The format mirrors Daniel Miessler's Telos template:

    # TELOS

    ## SECTION HEADER

    - REF: content line
    - REF: content line

Sections without ref_codes just use plain bullets. The IDENTITY section is
rendered as free-form text (name, location, role). Unknown headers are
preserved via `metadata.raw_section_name` so a round-trip is idempotent
for unknown sections.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .models import (
    IDENTITY_REF,
    REF_PREFIX,
    SECTION_HEADERS,
    Entry,
    Section,
    header_to_section,
)

_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+(?:([A-Z][A-Z0-9]*\d+|ME):\s+)?(.*)$")


def parse_telos_markdown(text: str) -> List[Entry]:
    """Parse canonical Telos markdown into a list of Entry objects.

    Unknown sections are dropped with a warning comment in
    metadata.raw_section_name so a round-trip preserves the source.
    Identity entries collapse to a single entry with ref_code='ME'.
    """
    entries: List[Entry] = []
    current_section: Optional[Section] = None
    current_unknown: Optional[str] = None
    sort_index = 0
    identity_lines: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            # Flush pending identity block if we were in IDENTITY.
            if current_section == Section.IDENTITY and identity_lines:
                entries.append(
                    Entry(
                        section=Section.IDENTITY,
                        ref_code=IDENTITY_REF,
                        content="\n".join(identity_lines).strip(),
                    )
                )
                identity_lines = []

            header_match = _HEADER_RE.match(line.lstrip())
            if not header_match:
                continue
            header_text = header_match.group(1)
            sec = header_to_section(header_text)
            if sec is not None:
                current_section = sec
                current_unknown = None
                sort_index = 0
            else:
                current_section = None
                current_unknown = header_text
                sort_index = 0
            continue

        if current_section is None and current_unknown is None:
            continue

        # Inside IDENTITY, accumulate lines (bulleted or not) into one entry.
        if current_section == Section.IDENTITY:
            bullet = _BULLET_RE.match(line.strip())
            if bullet:
                _, content = bullet.group(1), bullet.group(2)
                identity_lines.append(content)
            else:
                identity_lines.append(line.strip())
            continue

        bullet = _BULLET_RE.match(line.strip())
        if not bullet:
            continue
        ref_code, content = bullet.group(1), bullet.group(2)
        content = content.strip()
        if not content:
            continue

        if current_unknown is not None:
            entries.append(
                Entry(
                    section=Section.JOURNAL,  # lossy fallback
                    ref_code=ref_code,
                    content=content,
                    metadata={"raw_section_name": current_unknown},
                    sort_order=sort_index,
                )
            )
        else:
            assert current_section is not None
            entries.append(
                Entry(
                    section=current_section,
                    ref_code=ref_code,
                    content=content,
                    sort_order=sort_index,
                )
            )
        sort_index += 1

    # Flush trailing identity block.
    if current_section == Section.IDENTITY and identity_lines:
        entries.append(
            Entry(
                section=Section.IDENTITY,
                ref_code=IDENTITY_REF,
                content="\n".join(identity_lines).strip(),
            )
        )

    return entries


def render_telos_markdown(entries: List[Entry]) -> str:
    """Render a list of Entry objects as canonical Telos markdown.

    Sections appear in canonical order; empty sections are omitted.
    Identity renders as a free-form paragraph, not a bullet list.
    """
    grouped: Dict[Section, List[Entry]] = {s: [] for s in Section}
    unknown: Dict[str, List[Entry]] = {}
    for e in entries:
        raw_name = e.metadata.get("raw_section_name") if e.metadata else None
        if raw_name:
            unknown.setdefault(raw_name, []).append(e)
        else:
            grouped[e.section].append(e)

    out: List[str] = ["# TELOS", ""]

    for section in Section:
        items = grouped.get(section) or []
        if not items:
            continue
        items.sort(key=lambda e: (e.sort_order, e.created_at or 0))
        header = SECTION_HEADERS[section]
        out.append(f"## {header}")
        out.append("")
        if section == Section.IDENTITY:
            # Emit content as prose (may be multi-line).
            out.append(items[0].content)
            out.append("")
            continue
        for e in items:
            out.append(e.to_markdown_bullet())
        out.append("")

    for raw_name, items in unknown.items():
        out.append(f"## {raw_name}")
        out.append("")
        for e in items:
            out.append(e.to_markdown_bullet())
        out.append("")

    return "\n".join(out).rstrip() + "\n"
