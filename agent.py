"""Top-level agent module — lazy proxy for the cached Assembly.

`root_agent` and `ROOT_AGENTS` resolve via `__getattr__` after startup
runs `build_default_assembly()`. Pre-startup access raises a clear
lifecycle error instead of silently returning a half-initialized stub.

The ADK web interface and any caller that previously imported
`from agent import root_agent` continues to work — but module-level
imports of `root_agent` (which would evaluate `__getattr__` immediately,
before the web startup hook has run) MUST be moved inside function
bodies. See `specs/agents.md` § Assembly lifecycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from radbot.agent.assembly import create_agent

__all__ = ["root_agent", "ROOT_AGENTS", "create_agent"]


if TYPE_CHECKING:
    from google.adk.agents import Agent

    root_agent: Agent
    ROOT_AGENTS: Dict[str, Agent]


def __getattr__(name: str) -> Any:
    if name == "root_agent":
        from radbot.agent.assembly import _resolve_assembly

        return _resolve_assembly().root_agent
    if name == "ROOT_AGENTS":
        from radbot.agent.assembly import _resolve_assembly

        return _resolve_assembly().root_agents
    raise AttributeError(f"module 'agent' has no attribute {name!r}")
