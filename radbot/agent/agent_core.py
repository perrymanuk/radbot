"""
Core agent creation and configuration for RadBot.

Beto is a pure orchestrator with only memory tools. All domain tools
live on specialized sub-agents created by specialized_agent_factory.py.
"""

import os
import logging
from typing import Optional, Any, List
from datetime import date

# Import from our initialization and tools setup modules
from radbot.agent.agent_initializer import (
    logger,
    Agent,
    types,
    config_manager,
)

from radbot.agent.agent_tools_setup import (
    setup_before_agent_call,
    search_agent,
    code_execution_agent,
    scout_agent,
)

# Import specialized agents factory
from radbot.agent.specialized_agent_factory import create_specialized_agents

# Import memory tools and services
from radbot.memory.qdrant_memory import QdrantMemoryService
from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools
from radbot.config.config_loader import config_loader

# Import sanitization callback
from radbot.callbacks.sanitize_callback import sanitize_before_model_callback

# Import telemetry callback
from radbot.callbacks.telemetry_callback import telemetry_after_model_callback

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
        logger.info(f"Initializing QdrantMemoryService with host={host}, port={port}, collection={collection}")
        if url:
            logger.info(f"Using Qdrant URL: {url}")

        # Create memory service
        memory_service = QdrantMemoryService(
            collection_name=collection,
            host=host,
            port=int(port) if isinstance(port, str) else port,
            url=url,
            api_key=api_key,
        )
        logger.info(f"Successfully initialized QdrantMemoryService with collection '{collection}'")

    except Exception as e:
        logger.error(f"Failed to initialize QdrantMemoryService: {str(e)}")
        logger.warning("Memory service will not be available for this session")
        import traceback
        logger.debug(f"Memory service initialization traceback: {traceback.format_exc()}")


# NOTE: Do not call initialize_memory_service() at import time.
# DB config overrides (e.g. Qdrant host) aren't loaded yet.
# Web startup calls it in initialize_app_startup() after load_db_config().
# CLI calls it in its entry point.

# Get the model name from config
model_name = config_manager.get_main_model()
logger.info(f"Using model: {model_name}")

# Get today's date for the global instruction
today = date.today()

# Beto's tools: only agent-scoped memory tools (orchestrator pattern)
beto_tools = create_agent_memory_tools("beto")

# Create the root agent — no domain tools, only memory tools
root_agent = Agent(
    model=model_name,
    name="beto",
    instruction=instruction,
    global_instruction=f"""Today's date: {today}""",
    sub_agents=[search_agent, code_execution_agent, scout_agent],
    tools=beto_tools,
    before_agent_callback=setup_before_agent_call,
    before_model_callback=sanitize_before_model_callback,
    after_model_callback=telemetry_after_model_callback,
    generate_content_config=types.GenerateContentConfig(temperature=0.2),
)

# Create specialized agents (casa, planner, tracker, comms, axel)
specialized_agents = create_specialized_agents(root_agent)
logger.info(f"Created {len(specialized_agents)} specialized agents")

# Store memory_service as an attribute of the agent after creation
# This attribute will be used by the Runner in web/api/session.py
if memory_service:
    root_agent._memory_service = memory_service
    logger.info("Added memory_service to root_agent as _memory_service attribute")

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
        logger.info(f"Added {len(tools)} additional tools to agent")

    return root_agent
