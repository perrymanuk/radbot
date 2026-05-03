"""Item 6 (2026-05-03) — Telos read regression test.

Locks the structural shape of beto's Telos read responses (`telos_get_section`,
`telos_get_entry`, `telos_get_full`) against a checked-in baseline at
`tests/fixtures/item6_regression_baseline.json`. If a future contributor
changes beto's instruction file or the Telos render path in a way that breaks
parseability, this test fails BEFORE the bad behavior reaches production.

The "5 conversations" framing in the spec (routing / Telos read / Telos write /
transfer_to_agent / chitchat) collapses, in CI, to the deterministic Telos
read portion only — the unit+integration job in CI has no LLM client and no
DB bootstrap, so the routing/transfer/chitchat checks are documented as a
PR-checklist manual smoke (see PR description / `docs/plans/EX_DRAFT_*.md`
Item 6 AC #4 (a)+(c)).

Determinism strategy:
- Telos DB calls are patched with a fixed Entry fixture (`_FIXTURE_GROUPED`
  + `_FIXTURE_JOURNAL`) covering every section beto might read.
- Timestamps are stripped from all comparisons.
- Markdown output of `telos_get_full` is round-tripped through the existing
  `parse_telos_markdown` AST helper and compared structurally on
  `(section, ref_code, content)` tuples — rendering-order/whitespace
  variance is ignored.

To regenerate the baseline (e.g. after an intentional render change):

    make regen-item6-baseline

That re-runs this test with `RADBOT_REGEN_ITEM6_BASELINE=1`, which makes the
test WRITE the baseline JSON instead of asserting against it.

PR checklist: any change to beto's instruction file (`main_agent.md`) or to
Telos render code (`radbot/tools/telos/markdown_io.py`,
`radbot/tools/telos/loader.py`) requires regenerating the baseline IN THE
SAME PR — see `specs/agents.md` § Scout / Telos exploration lifecycle.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from radbot.tools.telos import telos_tools
from radbot.tools.telos.markdown_io import parse_telos_markdown
from radbot.tools.telos.models import Entry, Section

BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "item6_regression_baseline.json"
)
REGEN_ENV = "RADBOT_REGEN_ITEM6_BASELINE"


def _fixture_entry(
    section: Section,
    content: str,
    ref_code: str | None = None,
    metadata: dict | None = None,
) -> Entry:
    """Pinned-timestamp Entry — `created_at`/`updated_at` are STRIPPED in
    comparisons but kept here as a stable fixed value for reproducibility.
    """
    fixed = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    return Entry(
        entry_id=f"fixed-{ref_code or section.value}-uuid",
        section=section,
        ref_code=ref_code,
        content=content,
        metadata=metadata or {},
        status="active",
        sort_order=0,
        created_at=fixed,
        updated_at=fixed,
    )


# Fixed fixture covering every section beto's Telos read tools touch.
_FIXTURE_GROUPED: dict[Section, list[Entry]] = {s: [] for s in Section}
_FIXTURE_GROUPED[Section.IDENTITY] = [
    _fixture_entry(Section.IDENTITY, "Perry, Austin, builds agents.", "ME"),
]
_FIXTURE_GROUPED[Section.MISSION] = [
    _fixture_entry(Section.MISSION, "Make radbot self-aware.", "M1"),
]
_FIXTURE_GROUPED[Section.PROBLEMS] = [
    _fixture_entry(Section.PROBLEMS, "agents forget who the user is", "P1"),
    _fixture_entry(Section.PROBLEMS, "context windows are not free", "P2"),
]
_FIXTURE_GROUPED[Section.GOALS] = [
    _fixture_entry(Section.GOALS, "Ship telos", "G1"),
    _fixture_entry(Section.GOALS, "Sleep 8h", "G2"),
]
_FIXTURE_GROUPED[Section.PROJECTS] = [
    _fixture_entry(
        Section.PROJECTS,
        "Personal AI agent stack",
        "PRJ1",
        metadata={"name": "radbot"},
    ),
]
_FIXTURE_GROUPED[Section.WISDOM] = [
    _fixture_entry(Section.WISDOM, "the magic is in the work you're avoiding", "W1"),
]
_FIXTURE_JOURNAL = [
    _fixture_entry(Section.JOURNAL, "Wrote the Telos spec"),
    _fixture_entry(Section.JOURNAL, "Shipped Item 6"),
]


def _flatten_fixture() -> list[Entry]:
    """All fixture entries, in canonical-section order — what
    `telos_db.list_all` would return."""
    flat: list[Entry] = []
    for section in Section:
        flat.extend(_FIXTURE_GROUPED.get(section, []))
    flat.extend(_FIXTURE_JOURNAL)
    return flat


def _strip_timestamps(obj):
    """Recursively drop `created_at`/`updated_at`/`entry_id` from any dict
    or list of dicts so comparisons survive the timestamp-ignore rule."""
    if isinstance(obj, dict):
        return {
            k: _strip_timestamps(v)
            for k, v in obj.items()
            if k not in ("created_at", "updated_at", "entry_id")
        }
    if isinstance(obj, list):
        return [_strip_timestamps(x) for x in obj]
    return obj


def _parse_full_markdown_structurally(md: str) -> list[dict]:
    """AST-style parse of `telos_get_full()`'s markdown output.

    Reuses the existing `parse_telos_markdown` (which is a small AST-style
    helper that splits on the canonical `## SECTION` / bullet delimiters
    `render_telos_markdown` writes) and reduces each Entry to the
    `(section, ref_code, content)` triple the spec calls for.

    Sorted to make rendering-order ignored.
    """
    entries = parse_telos_markdown(md)
    return sorted(
        (
            {
                "section": e.section.value,
                "ref_code": e.ref_code,
                "content": e.content,
            }
            for e in entries
        ),
        key=lambda d: (d["section"], d["ref_code"] or "", d["content"]),
    )


@pytest.fixture
def patched_telos_db():
    """Patch every telos_db call the read tools touch with the fixed fixture."""

    def _list_section(sec, status=None, status_in=None, order_by="sort_order_asc"):
        items = list(_FIXTURE_GROUPED.get(sec, []))
        if sec == Section.JOURNAL:
            items = list(_FIXTURE_JOURNAL)
        if status is None and status_in is None:
            return items
        if status is not None and status != "active":
            return []
        return items

    def _get_entry(sec, ref_code):
        for e in _FIXTURE_GROUPED.get(sec, []):
            if e.ref_code == ref_code:
                return e
        return None

    def _list_all():
        return _flatten_fixture()

    with (
        patch.object(telos_tools.telos_db, "list_section", side_effect=_list_section),
        patch.object(telos_tools.telos_db, "get_entry", side_effect=_get_entry),
        patch.object(telos_tools.telos_db, "list_all", side_effect=_list_all),
    ):
        yield


def _build_actual_payload() -> dict:
    """Run the agent-side read tools the same way beto would and capture
    everything the baseline snapshots."""
    section_responses = {}
    for section in (
        Section.IDENTITY,
        Section.MISSION,
        Section.PROBLEMS,
        Section.GOALS,
        Section.PROJECTS,
        Section.WISDOM,
        Section.JOURNAL,
    ):
        section_responses[section.value] = _strip_timestamps(
            telos_tools.telos_get_section(section.value)
        )

    entry_responses = {}
    for section_name, ref_code in (
        ("identity", "ME"),
        ("mission", "M1"),
        ("goals", "G1"),
        ("projects", "PRJ1"),
    ):
        entry_responses[f"{section_name}:{ref_code}"] = _strip_timestamps(
            telos_tools.telos_get_entry(section_name, ref_code)
        )

    full_response = telos_tools.telos_get_full()
    assert (
        full_response["status"] == "success"
    ), f"telos_get_full failed: {full_response}"
    full_parsed = _parse_full_markdown_structurally(full_response["markdown"])

    return {
        "telos_get_section_responses": section_responses,
        "telos_get_entry_responses": entry_responses,
        "telos_get_full_parsed": full_parsed,
    }


class TestItem6TelosReadRegression:
    """Locks the Telos read shape beto depends on against the baseline.

    AC #4 (b) — automated. AC #4 (a) + (c) — manual PR-checklist smoke.
    """

    def test_telos_read_responses_match_baseline(self, patched_telos_db):
        actual = _build_actual_payload()

        if os.environ.get(REGEN_ENV):
            BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
            BASELINE_PATH.write_text(
                json.dumps(actual, indent=2, sort_keys=True) + "\n"
            )
            pytest.skip(
                f"Wrote baseline to {BASELINE_PATH} — re-run without "
                f"{REGEN_ENV} to assert."
            )

        assert BASELINE_PATH.exists(), (
            f"Baseline missing at {BASELINE_PATH}. Run "
            f"`make regen-item6-baseline` to seed it."
        )
        baseline = json.loads(BASELINE_PATH.read_text())
        assert actual == baseline, (
            "Telos read response shape diverged from baseline. If this is "
            "intentional (e.g. you changed the render format), re-run "
            "`make regen-item6-baseline` to update the fixture and check "
            "in the diff. If unintentional, beto's Telos read parsing is "
            "now broken — investigate before merging."
        )
