"""Manifest-driven agent assembly for radbot.

This module replaces the four-file orchestration ceremony
(`agent_initializer` + `agent_tools_setup` + `specialized_agent_factory` +
`agent_core`) with a single `AGENT_DEFS` manifest and a `build_default_assembly`
driver. Sub-agent factories live in their own `<domain>_agent/factory.py`
modules — assembly only walks the manifest, attaches the right callback
stack per role, and constructs the root.

Lifecycle
---------
`build_default_assembly()` MUST be called once after `load_db_config()` and
`initialize_memory_service()` — typically from the FastAPI startup hook in
`web/app.py`. The result is cached on a module-level slot, and the
top-level `agent.py` lazy proxy resolves `root_agent` / `ROOT_AGENTS`
through `_resolve_assembly()`.

Pre-startup access raises `RuntimeError` rather than silently returning a
half-initialized stub. Tests that need an assembled agent should call
`build_default_assembly()` (or `build_assembly()` with a custom manifest)
explicitly.

Failure modes
-------------
- `role="root"` and name == "beto" → raise. Beto missing = nothing works.
- `role="root"` and name != "beto" (e.g. scout-as-root) → log ERROR and
  omit from `ROOT_AGENTS`. `get_root_agent()` falls back to beto.
- `role="subagent"` or `role="builtin"` → raise. Sub-agent missing breaks
  routing.

Tool-layer integration outages (Picnic creds, HA unreachable) are absorbed
inside the per-domain factories via `factory_utils.load_tools()` — they
never bubble up here. The only way a factory itself raises is real
programmer error.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from google.adk.agents import Agent
from google.genai import types

from radbot.callbacks.empty_content_callback import (
    handle_empty_response_after_model,
    scrub_empty_content_before_model,
)
from radbot.callbacks.sanitize_callback import sanitize_before_model_callback
from radbot.callbacks.sanitize_tool_schemas import sanitize_tool_schemas_before_model
from radbot.callbacks.scope_to_current_turn import (
    scope_sub_agent_context_callback,
)
from radbot.callbacks.telemetry_callback import telemetry_after_model_callback
from radbot.callbacks.terse_protocol import (
    terse_protocol_after_model_callback,
    terse_protocol_before_model_callback,
)
from radbot.config import config_manager
from radbot.config.config_loader import config_loader
from radbot.memory.qdrant_memory import QdrantMemoryService
from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools
from radbot.tools.telos import TELOS_TOOLS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Memory service
# ---------------------------------------------------------------------------

# Module-level memory_service kept for backward compatibility with callers
# that imported it directly (admin.py status endpoint, health.py). New code
# should access it via `Assembly.memory_service` or the agent's
# `_memory_service` attribute.
memory_service: Optional[QdrantMemoryService] = None


def initialize_memory_service() -> Optional[QdrantMemoryService]:
    """Build a `QdrantMemoryService` from current config (DB overrides included).

    Returns the service (also stored on the module-level `memory_service`
    slot). Returns None on failure — memory becomes unavailable for the
    session, which is degraded but not fatal.
    """
    global memory_service
    try:
        vector_db_config = config_loader.get_config().get("vector_db", {})
        url = vector_db_config.get("url")
        api_key = vector_db_config.get("api_key")
        host = vector_db_config.get("host", "localhost")
        port = vector_db_config.get("port", 6333)
        collection = vector_db_config.get("collection", "radbot_memories")

        if not url:
            url = os.getenv("QDRANT_URL")
        if not api_key:
            api_key = os.getenv("QDRANT_API_KEY")
        if not host or host == "localhost":
            host = os.getenv("QDRANT_HOST", host)
        if port == 6333:
            port = os.getenv("QDRANT_PORT", port)
        if collection == "radbot_memories":
            collection = os.getenv("QDRANT_COLLECTION", collection)

        memory_service = QdrantMemoryService(
            collection_name=collection,
            host=host,
            port=int(port) if isinstance(port, str) else port,
            url=url,
            api_key=api_key,
        )
        logger.debug(
            "Initialized QdrantMemoryService (collection=%s, host=%s, port=%s)",
            collection,
            host,
            port,
        )
        return memory_service
    except Exception as e:
        logger.error("Failed to initialize QdrantMemoryService: %s", e)
        logger.warning("Memory service will not be available for this session")
        return None


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentDef:
    """One row in the assembly manifest.

    `factory` is a zero-arg callable that returns a constructed `Agent`
    (or None on degenerate failure — see module-level failure-mode rules).
    Per-agent quirks (axel's code execution, scout's sub/root flag) live
    inside the closure, not in this schema, so the manifest stays narrow.
    """

    name: str
    factory: Callable[[], Optional[Agent]]
    role: str  # "root" | "subagent" | "builtin"
    terse_protocol: bool = False
    gemini_only: bool = False


@dataclass
class Assembly:
    """Result of building the agent graph.

    `root_agents` keys are session-agent names (matching `chat_sessions.agent_name`);
    `default_root_name` resolves unknown names back to beto.
    """

    root_agent: Agent
    root_agents: Dict[str, Agent] = field(default_factory=dict)
    default_root_name: str = "beto"
    memory_service: Optional[QdrantMemoryService] = None


# ---------------------------------------------------------------------------
# Sub-agent factory closures
#
# Late imports inside each closure so this module can be imported without
# pulling the full sub-agent stack at import time (matters for tests that
# patch individual factories).
# ---------------------------------------------------------------------------


def _make_search_agent() -> Optional[Agent]:
    from radbot.tools.adk_builtin.search_tool import create_search_agent

    return create_search_agent(name="search_agent")


def _make_code_execution_agent() -> Optional[Agent]:
    from radbot.tools.adk_builtin.code_execution_tool import (
        create_code_execution_agent,
    )

    return create_code_execution_agent(name="code_execution_agent")


def _make_scout_subagent() -> Optional[Agent]:
    from radbot.agent.research_agent.factory import create_research_agent

    return create_research_agent(name="scout", as_subagent=False)


def _make_scout_root() -> Optional[Agent]:
    from radbot.agent.research_agent.factory import create_research_agent

    return create_research_agent(name="scout", as_root=True)


def _make_casa() -> Optional[Agent]:
    from radbot.agent.home_agent.factory import create_home_agent

    return create_home_agent()


def _make_planner() -> Optional[Agent]:
    from radbot.agent.planner_agent.factory import create_planner_agent

    return create_planner_agent()


def _make_comms() -> Optional[Agent]:
    from radbot.agent.comms_agent.factory import create_comms_agent

    return create_comms_agent()


def _make_axel() -> Optional[Agent]:
    from radbot.agent.execution_agent.factory import create_axel_agent

    return create_axel_agent()


def _make_kidsvid() -> Optional[Agent]:
    from radbot.agent.youtube_agent.factory import create_youtube_agent

    return create_youtube_agent()


# Default manifest. Order matters only for log readability; routing graph
# is built by ADK from the resulting `sub_agents` list passed to beto.
#
# Terse JSON Protocol attaches to agents emitting long prose
# (axel + planner). search_agent / code_execution_agent are ADK built-ins
# whose structured outputs the protocol would corrupt; scout emits
# structured plans; casa / comms / kidsvid are tool-heavy domain agents
# whose native output is already compact (EX20 telemetry showed casa
# looping 53× on a single light switch under the protocol).
AGENT_DEFS: List[AgentDef] = [
    AgentDef(
        name="search_agent",
        factory=_make_search_agent,
        role="builtin",
        gemini_only=True,
    ),
    AgentDef(
        name="code_execution_agent",
        factory=_make_code_execution_agent,
        role="builtin",
        gemini_only=True,
    ),
    AgentDef(name="scout", factory=_make_scout_subagent, role="subagent"),
    AgentDef(name="casa", factory=_make_casa, role="subagent"),
    AgentDef(
        name="planner", factory=_make_planner, role="subagent", terse_protocol=True
    ),
    AgentDef(name="comms", factory=_make_comms, role="subagent"),
    AgentDef(name="axel", factory=_make_axel, role="subagent", terse_protocol=True),
    AgentDef(name="kidsvid", factory=_make_kidsvid, role="subagent"),
    AgentDef(name="scout_root", factory=_make_scout_root, role="root"),
]


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


_SUBAGENT_AFTER_CBS = [
    handle_empty_response_after_model,
    telemetry_after_model_callback,
]
_SUBAGENT_BEFORE_CBS = [
    scope_sub_agent_context_callback,
    scrub_empty_content_before_model,
    sanitize_tool_schemas_before_model,
]


def _attach_subagent_callbacks(agent: Agent, terse_protocol: bool) -> None:
    """Wire the standard sub-agent callback stack onto `agent` in place."""
    if not agent.after_model_callback:
        agent.after_model_callback = (
            _SUBAGENT_AFTER_CBS + [terse_protocol_after_model_callback]
            if terse_protocol
            else list(_SUBAGENT_AFTER_CBS)
        )
    # Replace any existing before_model_callback (typically just scrub...) so
    # the scope-to-turn filter runs first.
    agent.before_model_callback = (
        _SUBAGENT_BEFORE_CBS + [terse_protocol_before_model_callback]
        if terse_protocol
        else list(_SUBAGENT_BEFORE_CBS)
    )


def _build_beto(sub_agents: List[Agent]) -> Agent:
    """Construct beto with all sub-agents and the root callback stack."""
    instruction = config_manager.get_instruction("main_agent")
    model_name = config_manager.get_main_model()
    today = date.today()

    # Beto's tools: agent-scoped memory + Telos. Sub-agents do NOT get Telos.
    beto_tools = create_agent_memory_tools("beto") + list(TELOS_TOOLS)

    return Agent(
        model=model_name,
        name="beto",
        instruction=instruction,
        global_instruction=f"""Today's date: {today}""",
        sub_agents=sub_agents,
        tools=beto_tools,
        before_model_callback=[
            scrub_empty_content_before_model,
            sanitize_before_model_callback,
            sanitize_tool_schemas_before_model,
        ],
        after_model_callback=[
            handle_empty_response_after_model,
            telemetry_after_model_callback,
        ],
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
    )


def build_assembly(
    defs: List[AgentDef],
    memory_service: Optional[QdrantMemoryService] = None,
) -> Assembly:
    """Build an `Assembly` from a custom manifest. Does NOT cache.

    Tests use this to assert wiring without spinning up the full agent.
    """
    sub_agents: List[Agent] = []
    extra_roots: Dict[str, Agent] = {}

    for d in defs:
        if d.role in ("subagent", "builtin"):
            try:
                agent = d.factory()
            except Exception as exc:
                logger.error(
                    "Sub-agent %r factory raised: %s", d.name, exc, exc_info=True
                )
                raise
            if agent is None:
                raise RuntimeError(
                    f"Sub-agent {d.name!r} factory returned None — sub-agent missing breaks routing"
                )
            _attach_subagent_callbacks(agent, terse_protocol=d.terse_protocol)
            sub_agents.append(agent)
            logger.debug("Assembled %s (%s)", d.name, d.role)
        elif d.role == "root":
            # Root agents (other than beto) are opt-in alternates. Failure to
            # build one shouldn't kill beto sessions.
            if d.name == "beto":
                raise RuntimeError(
                    "beto must be assembled by _build_beto, not declared as a root in AGENT_DEFS"
                )
            try:
                agent = d.factory()
            except Exception as exc:
                logger.error(
                    "Alternate root %r factory raised: %s — omitting from registry",
                    d.name,
                    exc,
                    exc_info=True,
                )
                continue
            if agent is None:
                logger.error(
                    "Alternate root %r factory returned None — omitting", d.name
                )
                continue
            extra_roots[agent.name] = agent
            if memory_service is not None:
                agent._memory_service = memory_service
            logger.debug("Assembled alternate root %s", d.name)
        else:
            raise ValueError(f"Unknown AgentDef role {d.role!r} for {d.name!r}")

    root_agent = _build_beto(sub_agents)
    if memory_service is not None:
        root_agent._memory_service = memory_service

    root_agents: Dict[str, Agent] = {"beto": root_agent}
    root_agents.update(extra_roots)

    logger.info(
        "Built assembly: beto + %d sub-agents + %d alternate root(s)",
        len(sub_agents),
        len(extra_roots),
    )

    return Assembly(
        root_agent=root_agent,
        root_agents=root_agents,
        default_root_name="beto",
        memory_service=memory_service,
    )


_cached_assembly: Optional[Assembly] = None


def build_default_assembly(
    memory_service: Optional[QdrantMemoryService] = None,
) -> Assembly:
    """Build the default assembly from `AGENT_DEFS` and cache it.

    Idempotent across repeated calls in the same process — the second call
    returns the cached assembly without rebuilding. The web startup hook
    calls this exactly once after `load_db_config()`.
    """
    global _cached_assembly
    if _cached_assembly is not None:
        return _cached_assembly
    _cached_assembly = build_assembly(AGENT_DEFS, memory_service=memory_service)
    return _cached_assembly


def reset_cached_assembly() -> None:
    """Clear the cached assembly. Tests use this to rebuild between cases."""
    global _cached_assembly
    _cached_assembly = None


def _resolve_assembly() -> Assembly:
    """Return the cached assembly or raise if not yet built.

    Used by the top-level `agent.py` lazy proxy. Pre-startup access raises
    a clear lifecycle error rather than silently returning a stub.
    """
    if _cached_assembly is None:
        raise RuntimeError(
            "Agent assembly has not been built yet. "
            "Call radbot.agent.assembly.build_default_assembly() during application startup "
            "(typically web/app.py:initialize_app_startup) before accessing root_agent."
        )
    return _cached_assembly


# ---------------------------------------------------------------------------
# Public access helpers
# ---------------------------------------------------------------------------


def get_root_agent(agent_name: str = "beto") -> Agent:
    """Return the root agent for a given session-agent name.

    Unknown names fall back to beto so a typo or legacy row doesn't strand
    a session.
    """
    assembly = _resolve_assembly()
    agent = assembly.root_agents.get(agent_name)
    if agent is None:
        logger.warning(
            "Unknown session agent_name=%r — falling back to beto", agent_name
        )
        return assembly.root_agent
    return agent


def create_agent(tools: Optional[List[Any]] = None, app_name: str = "beto") -> Agent:
    """Return the root agent (with optional extra tools).

    Kept for backward compatibility with the legacy ADK web entry point
    that resolves `create_agent` from `agent.py`.
    """
    assembly = _resolve_assembly()
    root = assembly.root_agent
    if tools:
        root.tools = list(root.tools) + list(tools)
        logger.debug("Added %d additional tools to root agent", len(tools))
    return root
