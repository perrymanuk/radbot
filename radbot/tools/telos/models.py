"""Telos data model — Section enum, Entry dataclass, ref-code prefixes.

Telos is a structured persona/context store for a single user. Each Entry
belongs to a Section and optionally carries a human-readable ref_code
(e.g. "G1", "P3") for stable reference in markdown round-trips.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class Section(str, Enum):
    IDENTITY = "identity"
    HISTORY = "history"
    PROBLEMS = "problems"
    MISSION = "mission"
    NARRATIVES = "narratives"
    GOALS = "goals"
    CHALLENGES = "challenges"
    STRATEGIES = "strategies"
    PROJECTS = "projects"
    MILESTONES = "milestones"
    PROJECT_TASKS = "project_tasks"
    EXPLORATIONS = "explorations"
    WISDOM = "wisdom"
    IDEAS = "ideas"
    PREDICTIONS = "predictions"
    WRONG_ABOUT = "wrong_about"
    BEST_BOOKS = "best_books"
    BEST_MOVIES = "best_movies"
    BEST_MUSIC = "best_music"
    TASTE = "taste"
    TRAUMAS = "traumas"
    METRICS = "metrics"
    JOURNAL = "journal"


# Canonical markdown header labels (used for parse/render).
SECTION_HEADERS: Dict[Section, str] = {
    Section.IDENTITY: "IDENTITY",
    Section.HISTORY: "HISTORY",
    Section.PROBLEMS: "PROBLEMS",
    Section.MISSION: "MISSION",
    Section.NARRATIVES: "NARRATIVES",
    Section.GOALS: "GOALS",
    Section.CHALLENGES: "CHALLENGES",
    Section.STRATEGIES: "STRATEGIES",
    Section.PROJECTS: "PROJECTS",
    Section.MILESTONES: "MILESTONES",
    Section.PROJECT_TASKS: "PROJECT TASKS",
    Section.EXPLORATIONS: "EXPLORATIONS",
    Section.WISDOM: "WISDOM",
    Section.IDEAS: "IDEAS",
    Section.PREDICTIONS: "PREDICTIONS",
    Section.WRONG_ABOUT: "THINGS I'VE BEEN WRONG ABOUT",
    Section.BEST_BOOKS: "BEST BOOKS",
    Section.BEST_MOVIES: "BEST MOVIES",
    Section.BEST_MUSIC: "BEST MUSIC",
    Section.TASTE: "TASTE",
    Section.TRAUMAS: "TRAUMAS",
    Section.METRICS: "METRICS",
    Section.JOURNAL: "LOG",
}

# Reverse map for markdown parsing (header text → Section). Case-insensitive.
_HEADER_TO_SECTION: Dict[str, Section] = {
    v.upper(): k for k, v in SECTION_HEADERS.items()
}
# Accept a few alternate headers from the canonical Telos template.
_HEADER_TO_SECTION["LOG (JOURNAL)"] = Section.JOURNAL
_HEADER_TO_SECTION["JOURNAL"] = Section.JOURNAL


def header_to_section(header: str) -> Optional[Section]:
    return _HEADER_TO_SECTION.get(header.strip().upper())


# Prefix used when auto-assigning ref_codes. Sections not listed here do not
# use ref_codes by default (identity uses "ME"; history, wisdom, ideas,
# journal, taste, traumas, best_* rely on natural ordering).
REF_PREFIX: Dict[Section, str] = {
    Section.PROBLEMS: "P",
    Section.MISSION: "M",
    Section.NARRATIVES: "N",
    Section.GOALS: "G",
    Section.CHALLENGES: "C",
    Section.STRATEGIES: "S",
    Section.PROJECTS: "PRJ",
    Section.MILESTONES: "MS",
    Section.PROJECT_TASKS: "PT",
    Section.EXPLORATIONS: "EX",
    Section.PREDICTIONS: "PRED",
    Section.METRICS: "K",
}


# Sections whose tools should fire without user confirmation. The tool layer
# does not enforce this — main_agent.md does. This set exists as
# documentation and for admin-panel UX hints.
SILENT_SECTIONS: set[Section] = {
    Section.JOURNAL,
    Section.PREDICTIONS,
    Section.WRONG_ABOUT,
    Section.BEST_BOOKS,
    Section.BEST_MOVIES,
    Section.BEST_MUSIC,
    Section.TASTE,
    Section.WISDOM,
    Section.IDEAS,
}

# Sections never always-loaded into beto's prompt (privacy / noise).
NEVER_ALWAYS_LOADED: set[Section] = {
    Section.TRAUMAS,
}

# Valid status values.
STATUS_VALUES: set[str] = {"active", "completed", "archived", "superseded"}

# Single identity ref_code (there's only one user).
IDENTITY_REF = "ME"


@dataclass
class Entry:
    entry_id: Optional[str] = None  # UUID string, None until DB-assigned
    section: Section = Section.JOURNAL
    ref_code: Optional[str] = None
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_markdown_bullet(self) -> str:
        """Render one entry as a markdown bullet line."""
        prefix = f"- {self.ref_code}: " if self.ref_code else "- "
        return f"{prefix}{self.content}"
