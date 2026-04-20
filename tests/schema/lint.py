"""PR-gate static lint — snapshot + diff of every tool's pydantic schema.

Walks the full RadBot agent graph (beto + all sub-agents), extracts a
pydantic-derived JSON schema for every tool via `extract_pydantic_adapter`,
and serializes the result through the `ToolSchemaSet` model (same committed-
pydantic pattern ADK uses for `EvalSet`). Compares against the committed
snapshot. On mismatch: fails CI with instructions to regenerate.

Usage:
    uv run python -m tests.schema.lint            # check mode (CI default)
    uv run python -m tests.schema.lint --update   # regenerate snapshot locally

The lint fails on *any* change. Classification of breaking vs non-breaking
drift is deliberately out of scope — the rule is "someone must look at this."
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tests.schema.extract import SkippedTool, iter_tool_adapters

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "tool_schemas.snapshot.json"


class ToolSchema(BaseModel):
    """One tool's input-schema record. Mirrors ADK's EvalCase ergonomics."""

    name: str
    agent: str
    json_schema: dict[str, Any]


class SkippedRecord(BaseModel):
    name: str
    agent: str
    reason: str


class ToolSchemaSet(BaseModel):
    """Committed snapshot of every tool schema in the agent graph.

    Follows the google/adk-python `EvalSet` convention: pydantic BaseModel,
    single JSON file, `model_dump_json(indent=2)` serialization for
    human-reviewable diffs in PRs.
    """

    snapshot_id: str = "radbot-tool-schemas-v1"
    description: str = (
        "Import-time schema of every agent tool. Regenerate with "
        "`uv run python -m tests.schema.lint --update` and review the diff."
    )
    tools: list[ToolSchema] = Field(default_factory=list)
    skipped: list[SkippedRecord] = Field(default_factory=list)


def _walk_agents(root: Any) -> list[tuple[str, Any]]:
    """Yield `(agent_name, tool)` for root + every reachable sub-agent, deduped."""
    seen_agents: set[int] = set()
    seen_tools: set[tuple[str, str]] = set()
    out: list[tuple[str, Any]] = []

    def visit(agent: Any) -> None:
        if id(agent) in seen_agents:
            return
        seen_agents.add(id(agent))
        for tool in getattr(agent, "tools", None) or []:
            tool_name = getattr(tool, "name", None) or type(tool).__name__
            key = (agent.name, tool_name)
            if key in seen_tools:
                continue
            seen_tools.add(key)
            out.append((agent.name, tool))
        for sub in getattr(agent, "sub_agents", None) or []:
            visit(sub)

    visit(root)
    return out


def _load_root_agent() -> Any:
    from radbot.agent.agent_core import root_agent

    return root_agent


def build_snapshot() -> ToolSchemaSet:
    """Regenerate the snapshot in-memory from the live agent graph."""
    root = _load_root_agent()
    pairs = _walk_agents(root)

    tools: list[ToolSchema] = []
    skipped: list[SkippedRecord] = []

    for agent_name, tool in pairs:
        name = getattr(tool, "name", None) or type(tool).__name__
        # `iter_tool_adapters` handles MCP + unsupported shapes gracefully.
        results = list(iter_tool_adapters([tool]))
        _, result = results[0]
        if isinstance(result, SkippedTool):
            skipped.append(
                SkippedRecord(name=name, agent=agent_name, reason=result.reason)
            )
            continue
        try:
            schema = result.json_schema()
        except Exception as exc:  # pragma: no cover — defensive
            skipped.append(
                SkippedRecord(
                    name=name, agent=agent_name, reason=f"schema render failed: {exc}"
                )
            )
            continue
        tools.append(ToolSchema(name=name, agent=agent_name, json_schema=schema))

    tools.sort(key=lambda t: (t.agent, t.name))
    skipped.sort(key=lambda s: (s.agent, s.name))
    return ToolSchemaSet(tools=tools, skipped=skipped)


def _serialize(snap: ToolSchemaSet) -> str:
    # `indent=2` + trailing newline → clean git diffs.
    return snap.model_dump_json(indent=2) + "\n"


def _load_committed() -> str | None:
    if not SNAPSHOT_PATH.exists():
        return None
    return SNAPSHOT_PATH.read_text()


def check() -> int:
    current = _serialize(build_snapshot())
    committed = _load_committed()

    if committed is None:
        sys.stderr.write(
            f"error: no committed snapshot at {SNAPSHOT_PATH}.\n"
            "Run `uv run python -m tests.schema.lint --update` and commit the result.\n"
        )
        return 2

    if current == committed:
        print(f"ok: tool schemas match {SNAPSHOT_PATH.name}")
        return 0

    diff = difflib.unified_diff(
        committed.splitlines(keepends=True),
        current.splitlines(keepends=True),
        fromfile=f"a/{SNAPSHOT_PATH.name}",
        tofile=f"b/{SNAPSHOT_PATH.name}",
    )
    sys.stderr.write(
        "error: tool schemas drifted from committed snapshot.\n"
        "This is the pydantic-constraint drift guard (EX17 / PT46).\n"
        "If the change is intentional, regenerate and commit:\n"
        "    uv run python -m tests.schema.lint --update\n"
        "Diff:\n"
    )
    sys.stderr.writelines(diff)
    return 1


def update() -> int:
    snap = build_snapshot()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(_serialize(snap))
    print(
        f"wrote {SNAPSHOT_PATH}: {len(snap.tools)} tools, {len(snap.skipped)} skipped"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Regenerate and write the committed snapshot (developer action; NOT for CI).",
    )
    args = parser.parse_args(argv)
    return update() if args.update else check()


if __name__ == "__main__":
    raise SystemExit(main())
