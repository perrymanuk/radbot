"""Semantic-memory MCP tool — Qdrant-backed search over agent memory.

Default scope is `beto` (matches radbot's primary orchestrator). Pass
`agent_scope` to narrow to a specific sub-agent (casa, planner, etc.) or
the sentinel `all` to widen.

Returns markdown: one bullet per hit with score, snippet, source agent,
and relative date where available.
"""

from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

_USER_ID = "web_user"  # single-user system; matches CLAUDE.md convention
_APP_NAME = "radbot"
_DEFAULT_SCOPE = "beto"
_WIDEN_SENTINEL = "all"


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="search_memory",
            description=(
                "Semantic search across radbot's Qdrant-backed agent memory. "
                "Default scope is `beto` (the root orchestrator). Pass "
                f"`agent_scope` to target a sub-agent, or `{_WIDEN_SENTINEL}` "
                "to search across every agent."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "agent_scope": {
                        "type": "string",
                        "description": (
                            "Agent namespace to restrict results to. Default 'beto'. "
                            "Use 'all' to search across every agent."
                        ),
                        "default": _DEFAULT_SCOPE,
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 25,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
    ]


async def call(
    name: str, arguments: dict[str, Any]
) -> list[mcp_types.TextContent]:
    if name == "search_memory":
        return [_do_search(
            arguments["query"],
            arguments.get("agent_scope", _DEFAULT_SCOPE),
            int(arguments.get("limit", 5)),
        )]
    raise KeyError(name)


def _do_search(query: str, agent_scope: str, limit: int) -> mcp_types.TextContent:
    from radbot.memory.qdrant_memory import QdrantMemoryService

    try:
        service = QdrantMemoryService()
    except Exception as e:
        return mcp_types.TextContent(
            type="text", text=f"**Error:** memory service unavailable: {e}"
        )

    filter_conditions: dict[str, Any] | None = None
    if agent_scope and agent_scope.lower() != _WIDEN_SENTINEL:
        filter_conditions = {"source_agent": agent_scope}

    try:
        hits = service.search_memory(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            query=query,
            limit=limit,
            filter_conditions=filter_conditions,
        )
    except Exception as e:
        return mcp_types.TextContent(
            type="text", text=f"**Error:** search failed: {e}"
        )

    if not hits:
        scope_label = agent_scope if agent_scope else _DEFAULT_SCOPE
        return mcp_types.TextContent(
            type="text",
            text=f"_No memory hits for `{query}` (scope: {scope_label})._",
        )

    scope_label = agent_scope if agent_scope else _DEFAULT_SCOPE
    lines = [
        f"## Memory search for `{query}` (scope: {scope_label}, {len(hits)} hits)",
        "",
    ]
    for h in hits:
        score = h.get("score")
        score_str = f" · score={score:.3f}" if isinstance(score, (int, float)) else ""
        payload = h.get("payload") or h
        source_agent = payload.get("source_agent") or "—"
        mem_type = payload.get("memory_type") or ""
        ts = payload.get("timestamp") or payload.get("ingested_at") or ""
        snippet = (payload.get("text") or payload.get("content") or "").strip()
        if len(snippet) > 320:
            snippet = snippet[:320] + "…"
        meta_bits = [f"agent={source_agent}"]
        if mem_type:
            meta_bits.append(f"type={mem_type}")
        if ts:
            meta_bits.append(f"ts={ts}")
        lines.append(f"- _({' · '.join(meta_bits)}{score_str})_")
        if snippet:
            # Render snippet as blockquote for visual separation
            for sline in snippet.splitlines():
                lines.append(f"  > {sline}")
        lines.append("")
    return mcp_types.TextContent(type="text", text="\n".join(lines).rstrip())
