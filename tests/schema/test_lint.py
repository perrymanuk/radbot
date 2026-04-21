"""Tests for the PR-gate lint — build_snapshot + drift detection."""

from __future__ import annotations

import json

from tests.schema import lint as lint_module


def test_committed_snapshot_matches_live_agent_graph():
    """The committed snapshot must match what the live agent graph produces.

    This is the actual PR-gate assertion, runnable as a unit test (so it
    shows up in pytest output alongside everything else). If this fails
    locally, run `uv run python -m tests.schema.lint --update` and review
    the diff before committing.
    """
    current = lint_module._serialize(lint_module.build_snapshot())
    committed = lint_module.SNAPSHOT_PATH.read_text()
    assert current == committed, (
        "Tool schemas drifted from the committed snapshot.\n"
        "Regenerate with: uv run python -m tests.schema.lint --update"
    )


def test_snapshot_captures_full_toolset():
    """Sanity check: snapshot covers every agent in the graph."""
    snap = json.loads(lint_module.SNAPSHOT_PATH.read_text())
    agents = {t["agent"] for t in snap["tools"]}
    # Known agents from CLAUDE.md tool table. Scout has no sub-agents
    # of its own; the root-agent graph exposes these 8 children.
    assert {"beto", "axel", "casa", "comms", "kidsvid", "planner"}.issubset(agents)


def test_check_fails_on_injected_drift(tmp_path, monkeypatch):
    """`check()` must exit non-zero when the live schema differs from the snapshot."""
    # Point the lint at a throwaway path seeded with a deliberately wrong snapshot.
    fake_snapshot = tmp_path / "tool_schemas.snapshot.json"
    fake_snapshot.write_text('{"snapshot_id":"bogus","tools":[],"skipped":[]}\n')
    monkeypatch.setattr(lint_module, "SNAPSHOT_PATH", fake_snapshot)

    rc = lint_module.check()

    assert rc == 1  # drift detected


def test_check_errors_when_snapshot_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(lint_module, "SNAPSHOT_PATH", tmp_path / "missing.json")

    rc = lint_module.check()

    assert rc == 2  # distinct exit code so CI can spot the bootstrap case
