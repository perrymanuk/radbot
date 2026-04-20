"""Telos command-line interface.

    uv run python -m radbot.tools.telos.cli {onboard|import|export|show|reset}

* onboard — interactive one-time setup (9-question interview).
* import FILE — load a canonical Telos markdown file (merge into DB).
* export — print current Telos as canonical markdown to stdout.
* show — print a human-readable summary of the current state.
* reset — wipe ALL entries (asks for confirmation).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from . import db as telos_db
from .markdown_io import parse_telos_markdown, render_telos_markdown
from .models import IDENTITY_REF, Section

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def _prompt_line(label: str, allow_skip: bool = True) -> Optional[str]:
    """Single-line prompt. Returns None on empty/skip."""
    hint = " (enter to skip)" if allow_skip else ""
    sys.stdout.write(f"{label}{hint}: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    return line or None


def _prompt_multiline(label: str) -> str:
    """Multi-line prompt. Blank line ends input."""
    print(f"{label} (blank line to finish):")
    lines: List[str] = []
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        stripped = line.rstrip("\n")
        if stripped == "":
            break
        lines.append(stripped)
    return "\n".join(lines).strip()


def _prompt_list(label: str, min_count: int = 0) -> List[str]:
    """Collect multiple items, one per line. Blank line ends input."""
    print(f"{label} (one per line; blank line to finish):")
    items: List[str] = []
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            if len(items) >= min_count:
                break
            print(
                f"  need at least {min_count}; keep going (or empty line to abort step)."
            )
            continue
        items.append(stripped)
    return items


def _confirm(prompt: str, default: bool = False) -> bool:
    default_label = "Y/n" if default else "y/N"
    sys.stdout.write(f"{prompt} [{default_label}]: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        return default
    ans = line.strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


# ---------------------------------------------------------------------------
# Onboard flow
# ---------------------------------------------------------------------------


def onboard() -> int:
    if telos_db.has_identity():
        print("Telos Identity is already set. Nothing to onboard.")
        print("(To redo onboarding, run `telos reset` first.)")
        return 0

    print("=" * 60)
    print("Telos onboarding — one-time setup, ~5 minutes.")
    print("Skip any question with an empty line.")
    print("=" * 60)

    # 1. Identity (committed immediately so the sentinel flips).
    print("\n[1/9] Identity")
    name = _prompt_line("Your name", allow_skip=False)
    location = _prompt_line("Where you're based")
    role = _prompt_line("What you do (role / occupation)")
    pronouns = _prompt_line("Pronouns")
    if name is None:
        print("Name is required. Aborting.")
        return 1
    content_bits = [name]
    if location:
        content_bits.append(f"based in {location}")
    if role:
        content_bits.append(role)
    identity_content = ", ".join(content_bits)
    metadata = {
        k: v
        for k, v in {
            "name": name,
            "location": location or "",
            "role": role or "",
            "pronouns": pronouns or "",
        }.items()
        if v
    }
    telos_db.upsert_singleton(
        Section.IDENTITY, IDENTITY_REF, identity_content, metadata
    )
    print("  ✓ Identity saved.")

    # 2. Problems.
    print("\n[2/9] Problems — big things you're trying to solve.")
    problems = _prompt_list("Problems (1-3)")
    for p in problems:
        telos_db.add_entry(Section.PROBLEMS, p)
    if problems:
        print(f"  ✓ {len(problems)} problem(s) saved.")

    # 3. Mission.
    print("\n[3/9] Mission — what you want to put into the world.")
    mission = _prompt_multiline("Mission")
    if mission:
        telos_db.add_entry(Section.MISSION, mission)
        print("  ✓ Mission saved.")

    # 4. Goals.
    print("\n[4/9] Goals — what you're working toward right now.")
    print("       (You can add deadlines/KPIs later.)")
    goals = _prompt_list("Goals")
    for g in goals:
        telos_db.add_entry(Section.GOALS, g)
    if goals:
        print(f"  ✓ {len(goals)} goal(s) saved.")

    # 5. Projects.
    print("\n[5/9] Projects — concrete things you're actively working on.")
    projects = _prompt_list("Projects")
    for p in projects:
        telos_db.add_entry(Section.PROJECTS, p)
    if projects:
        print(f"  ✓ {len(projects)} project(s) saved.")

    # 6. Challenges.
    print("\n[6/9] Challenges — what's actively blocking you.")
    challenges = _prompt_list("Challenges")
    for c in challenges:
        telos_db.add_entry(Section.CHALLENGES, c)
    if challenges:
        print(f"  ✓ {len(challenges)} challenge(s) saved.")

    # 7. Wisdom.
    print("\n[7/9] Wisdom — principles you live by; things radbot should remember.")
    wisdom = _prompt_list("Wisdom")
    for w in wisdom:
        telos_db.add_entry(Section.WISDOM, w)
    if wisdom:
        print(f"  ✓ {len(wisdom)} wisdom entry/entries saved.")

    # 8. Taste.
    print(
        "\n[8/9] Taste — best book / movie / anything worth knowing about your taste."
    )
    book = _prompt_line("Best book")
    if book:
        telos_db.add_entry(Section.BEST_BOOKS, book, metadata={"sentiment": "love"})
    movie = _prompt_line("Best movie")
    if movie:
        telos_db.add_entry(Section.BEST_MOVIES, movie, metadata={"sentiment": "love"})

    # 9. History (optional).
    print("\n[9/9] History — background that shapes how you think. Optional.")
    if _confirm("Want to add history now?"):
        history = _prompt_multiline("History")
        if history:
            telos_db.add_entry(Section.HISTORY, history)
            print("  ✓ History saved.")

    print("\n" + "=" * 60)
    print("Onboarding complete. Telos is live.")
    print("From here, beto will keep it updated from your conversations.")
    print("Run `python -m radbot.tools.telos.cli show` any time to review.")
    print("=" * 60)
    return 0


# ---------------------------------------------------------------------------
# Import / export / show / reset
# ---------------------------------------------------------------------------


def cmd_import(path: str, replace: bool = False) -> int:
    source = Path(path)
    if not source.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    text = source.read_text(encoding="utf-8")
    entries = parse_telos_markdown(text)
    if not entries:
        print("Parsed zero entries — input may not be canonical Telos markdown.")
        return 1
    if replace:
        if not _confirm(
            f"REPLACE all existing Telos entries and load {len(entries)} from {path}?"
        ):
            print("Aborted.")
            return 1
        telos_db.reset_all()
    rows = telos_db.bulk_upsert(entries)
    print(f"Imported {len(rows)} entries from {path} (replace={replace}).")
    return 0


def cmd_export() -> int:
    entries = telos_db.list_all()
    sys.stdout.write(render_telos_markdown(entries))
    return 0


def cmd_show() -> int:
    if not telos_db.has_identity():
        print("Telos is empty. Run `onboard` to set it up.")
        return 0
    grouped = telos_db.list_all_active()
    journal = telos_db.recent_journal(limit=10)
    for section in Section:
        items = grouped.get(section, [])
        if not items and section != Section.JOURNAL:
            continue
        if section == Section.JOURNAL:
            items = journal
            if not items:
                continue
        print(f"\n=== {section.value.upper()} ({len(items)}) ===")
        for e in items:
            ref = f"[{e.ref_code}] " if e.ref_code else ""
            print(f"  {ref}{e.content}")
            if e.metadata:
                meta_short = ", ".join(f"{k}={v}" for k, v in e.metadata.items() if v)
                if meta_short:
                    print(f"      ({meta_short})")
    return 0


def cmd_reset(section: Optional[str] = None) -> int:
    if section:
        try:
            sec = Section(section)
        except ValueError:
            print(f"Unknown section: {section}", file=sys.stderr)
            return 1
        if not _confirm(f"Delete ALL entries in section '{sec.value}'?"):
            print("Aborted.")
            return 1
        n = telos_db.reset_all(section=sec)
        print(f"Deleted {n} entries in {sec.value}.")
    else:
        if not _confirm("Delete ALL Telos entries across ALL sections?"):
            print("Aborted.")
            return 1
        n = telos_db.reset_all()
        print(f"Deleted {n} entries. Telos is now empty.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        prog="python -m radbot.tools.telos.cli",
        description="Telos CLI — manage the persistent user-context store.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("onboard", help="Interactive one-time setup")

    imp = sub.add_parser("import", help="Import a Telos markdown file")
    imp.add_argument("path", help="Path to the markdown file")
    imp.add_argument(
        "--replace",
        action="store_true",
        help="Wipe all existing entries before import (default: merge)",
    )

    sub.add_parser("export", help="Print current Telos as canonical markdown")
    sub.add_parser("show", help="Print a human-readable summary")

    rst = sub.add_parser("reset", help="Delete all entries (asks confirmation)")
    rst.add_argument(
        "--section",
        help="Delete only one section instead of all",
    )

    args = parser.parse_args(argv)

    # Make sure the schema exists before any command runs.
    telos_db.init_telos_schema()

    if args.command == "onboard":
        return onboard()
    if args.command == "import":
        return cmd_import(args.path, replace=args.replace)
    if args.command == "export":
        return cmd_export()
    if args.command == "show":
        return cmd_show()
    if args.command == "reset":
        return cmd_reset(section=args.section)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
