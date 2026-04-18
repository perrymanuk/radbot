"""
Core agent creation and configuration for RadBot.

Beto is a pure orchestrator with only memory tools. All domain tools
live on specialized sub-agents.

Sub-agent assembly order: pass every sub-agent to the root Agent
constructor rather than mutating ``sub_agents`` after the fact — ADK
sets ``parent_agent`` on each child at construction, which the tree
relies on for routing lookup.
"""

import logging
import os
from datetime import date
from typing import Any, List, Optional

# Import from our initialization and tools setup modules
from radbot.agent.agent_initializer import (
    Agent,
    config_manager,
    logger,
    types,
)
from radbot.agent.agent_tools_setup import setup_before_agent_call

# Import callbacks
from radbot.callbacks.sanitize_callback import sanitize_before_model_callback
from radbot.callbacks.empty_content_callback import (
    handle_empty_response_after_model,
    scrub_empty_content_before_model,
)
from radbot.callbacks.telemetry_callback import telemetry_after_model_callback
from radbot.callbacks.scope_to_current_turn import (
    scope_sub_agent_context_callback,
)
from radbot.config.config_loader import config_loader

# Import memory tools and services
from radbot.memory.qdrant_memory import QdrantMemoryService
from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools
from radbot.tools.telos import TELOS_TOOLS, inject_telos_context

# Get the instruction from the config manager
instruction = config_manager.get_instruction("main_agent")

# Initialize memory service from vector_db configuration
memory_service = None


def initialize_memory_service():
    """Initialize (or re-initialize) QdrantMemoryService from current config.

    Called at import time with file-based config, and again from
    initialize_app_startup() after DB config overrides are loaded.
    """
    global memory_service
    try:
        # Get Qdrant settings from config_loader (includes DB overrides if loaded)
        vector_db_config = config_loader.get_config().get("vector_db", {})
        url = vector_db_config.get("url")
        api_key = vector_db_config.get("api_key")
        host = vector_db_config.get("host", "localhost")
        port = vector_db_config.get("port", 6333)
        collection = vector_db_config.get("collection", "radbot_memories")

        # Fallback to environment variables for backward compatibility
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

        # Log memory service configuration
        logger.debug(
            f"Initializing QdrantMemoryService with host={host}, port={port}, collection={collection}"
        )
        if url:
            logger.debug(f"Using Qdrant URL: {url}")

        # Create memory service
        memory_service = QdrantMemoryService(
            collection_name=collection,
            host=host,
            port=int(port) if isinstance(port, str) else port,
            url=url,
            api_key=api_key,
        )
        logger.debug(
            f"Successfully initialized QdrantMemoryService with collection '{collection}'"
        )

    except Exception as e:
        logger.error(f"Failed to initialize QdrantMemoryService: {str(e)}")
        logger.warning("Memory service will not be available for this session")
        import traceback

        logger.debug(
            f"Memory service initialization traceback: {traceback.format_exc()}"
        )


# NOTE: Do not call initialize_memory_service() at import time.
# DB config overrides (e.g. Qdrant host) aren't loaded yet.
# Web startup calls it in initialize_app_startup() after load_db_config().
# CLI calls it in its entry point.

# Get the model name from config
model_name = config_manager.get_main_model()
logger.debug(f"Using model: {model_name}")

# Get today's date for the global instruction
today = date.today()

# Beto's tools: agent-scoped memory + Telos (persistent user persona / context store).
# Sub-agents do NOT get Telos tools — they're tool executors, not persona-aware.
beto_tools = create_agent_memory_tools("beto") + list(TELOS_TOOLS)

# ---------------------------------------------------------------------------
# Create ALL sub-agents BEFORE the root Agent constructor so ADK sets
# parent_agent on each child at construction time. Mutating sub_agents
# later leaves that link unset, breaking routing lookups.
# ---------------------------------------------------------------------------

# Builtin sub-agents (search, code execution, scout)
from radbot.agent.research_agent.factory import create_research_agent
from radbot.tools.adk_builtin.code_execution_tool import create_code_execution_agent
from radbot.tools.adk_builtin.search_tool import create_search_agent

search_agent = create_search_agent(name="search_agent")
code_execution_agent = create_code_execution_agent(name="code_execution_agent")
scout_agent = create_research_agent(name="scout", as_subagent=False)

# Domain sub-agents (casa, planner, tracker, comms, axel)
from radbot.agent.specialized_agent_factory import create_specialized_agents

specialized_agents = create_specialized_agents()
logger.debug(f"Created {len(specialized_agents)} specialized agents")

# Assemble the complete sub-agents list
all_sub_agents = [a for a in [search_agent, code_execution_agent, scout_agent] if a is not None]
all_sub_agents.extend(specialized_agents)

# Attach callbacks to all sub-agents before construction.
# scope_sub_agent_context_callback scopes each sub-agent's LLM prompt to the
# current user turn (prevents cross-turn context bleed). Root Beto keeps
# full history — only sub-agents are scoped.
_after_cbs = [handle_empty_response_after_model, telemetry_after_model_callback]
_before_cbs = [scope_sub_agent_context_callback, scrub_empty_content_before_model]
for sa in all_sub_agents:
    if not sa.after_model_callback:
        sa.after_model_callback = _after_cbs
    # Replace any existing before_model_callback (typically just scrub...) with
    # our combined list so the scope-to-turn filter runs first.
    sa.before_model_callback = _before_cbs

# Create the root agent with ALL sub-agents in the constructor
root_agent = Agent(
    model=model_name,
    name="beto",
    instruction=instruction,
    global_instruction=f"""Today's date: {today}""",
    sub_agents=all_sub_agents,
    tools=beto_tools,
    before_agent_callback=setup_before_agent_call,
    before_model_callback=[
        scrub_empty_content_before_model,
        sanitize_before_model_callback,
        # Telos: inject user persona/context into beto's system_instruction.
        # Anchor every turn, full block session-start only (state-gated).
        # Attached to beto ONLY — sub-agents don't need user persona context.
        inject_telos_context,
    ],
    after_model_callback=[handle_empty_response_after_model, telemetry_after_model_callback],
    generate_content_config=types.GenerateContentConfig(temperature=0.2),
)

# Store memory_service as an attribute of the agent after creation
# This attribute will be used by the Runner in web/api/session.py
if memory_service:
    root_agent._memory_service = memory_service
    logger.debug("Added memory_service to root_agent as _memory_service attribute")

# Log agent creation
logger.info(
    f"Created root agent 'beto' with {len(beto_tools)} tools and "
    f"{len(root_agent.sub_agents)} sub-agents"
)


def create_agent(tools: Optional[List[Any]] = None, app_name: str = "beto"):
    """
    Create the agent with all necessary tools.

    This is the entry point used by ADK web to create the agent.

    Args:
        tools: Optional list of additional tools to include
        app_name: Application name to use, defaults to "beto"

    Returns:
        An ADK BaseAgent instance
    """
    # If additional tools are provided, add them to the agent
    if tools:
        all_tools = list(root_agent.tools) + list(tools)
        root_agent.tools = all_tools
        logger.debug(f"Added {len(tools)} additional tools to agent")

    return root_agent
