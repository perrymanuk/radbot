"""Telos — persistent user-context store for beto.

Single table (``telos_entries``) holds structured sections: identity,
mission, problems, goals, projects, challenges, wisdom, predictions,
journal, etc. Beto reads it on every turn (anchor) and at session start
(full block), and writes to it during interactions via FunctionTools.

See ``docs/implementation/telos.md`` for the full design.
"""

from .callback import inject_telos_context
from .db import init_telos_schema
from .loader import build_telos_tiers
from .telos_tools import TELOS_TOOLS

__all__ = [
    "TELOS_TOOLS",
    "build_telos_tiers",
    "init_telos_schema",
    "inject_telos_context",
]
