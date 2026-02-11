"""
Factory functions for creating agents with memory capabilities.
"""

import logging
from typing import Any, List, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

# SessionService is now just InMemorySessionService in recent ADK versions
SessionService = InMemorySessionService  # Type alias for backward compatibility

from radbot.agent.agent import RadBotAgent
from radbot.config import config_manager
from radbot.config.config_loader import config_loader
from radbot.memory.qdrant_memory import QdrantMemoryService
from radbot.tools.memory import search_past_conversations, store_important_information


def create_memory_enabled_agent(
    session_service: Optional[SessionService] = None,
    tools: Optional[List[Any]] = None,
    memory_service: Optional[QdrantMemoryService] = None,
    instruction_name: str = "main_agent",
    name: str = "memory_enabled_agent",
) -> RadBotAgent:
    """
    Create an agent with memory capabilities.

    Args:
        session_service: Optional session service for conversation state
        tools: Optional list of tools for the agent
        memory_service: Optional custom memory service (creates one if not provided)
        instruction_name: Name of instruction to load from config
        name: Name for the agent

    Returns:
        A configured RadBotAgent instance with memory capabilities
    """
    # Create or use provided session service
    session_service = session_service or InMemorySessionService()

    # Create or use provided memory service
    if not memory_service:
        # Get Qdrant settings from config_loader
        vector_db_config = config_loader.get_config().get("vector_db", {})
        url = vector_db_config.get("url")
        api_key = vector_db_config.get("api_key")
        host = vector_db_config.get("host", "localhost")
        port = vector_db_config.get("port", 6333)
        collection = vector_db_config.get("collection", "radbot_memories")

        # Log Qdrant connection details (without sensitive info)
        logging.info(
            f"Connecting to Qdrant with: host={host}, port={port}, collection={collection}"
        )
        if url:
            logging.info(f"Using Qdrant URL: {url}")

        # Create memory service
        try:
            memory_service = QdrantMemoryService(
                collection_name=collection,
                host=host,
                port=int(port) if isinstance(port, str) else port,
                url=url,
                api_key=api_key,
            )
            logging.info(
                f"Successfully initialized QdrantMemoryService with collection '{collection}'"
            )

            # Additional debug info
            if hasattr(memory_service, "client") and memory_service.client:
                client_info = str(memory_service.client)
                collection_name = getattr(memory_service, "collection_name", None)
                logging.debug(
                    f"Memory service client: {client_info}, collection: {collection_name}"
                )
        except Exception as e:
            logging.error(f"Failed to initialize QdrantMemoryService: {str(e)}")
            import traceback

            logging.error(f"Traceback: {traceback.format_exc()}")
            raise

    # Ensure memory tools are included
    memory_tools = [search_past_conversations, store_important_information]
    all_tools = list(tools or []) + memory_tools

    # Create the agent with tools and memory service
    model = config_manager.get_main_model()

    # Log all tool names for debugging
    tool_names = []
    for tool in all_tools:
        if hasattr(tool, "__name__"):
            tool_names.append(tool.__name__)
        elif hasattr(tool, "name"):
            tool_names.append(tool.name)
        else:
            tool_names.append(str(type(tool)))
    logging.info(
        f"Creating memory-enabled agent with tools: {', '.join(tool_names[:10])}"
    )

    # Use the updated constructor that accepts memory_service directly
    agent = RadBotAgent(
        name=name,
        session_service=session_service,
        tools=all_tools,
        model=model,
        instruction_name=instruction_name,
        memory_service=memory_service,  # Pass memory_service directly
    )

    # Double check that the memory service is properly set
    if not hasattr(agent, "_memory_service") or agent._memory_service is None:
        logging.warning(
            "Memory service not properly set on agent, setting it explicitly"
        )
        agent._memory_service = memory_service

        # Also recreate the runner to ensure it has the memory service
        agent.runner = Runner(
            agent=agent.root_agent,
            app_name="beto",  # Changed from "radbot" to match agent name
            session_service=session_service,
            memory_service=memory_service,
        )

    # Verify memory tools are properly registered
    if agent.root_agent and agent.root_agent.tools:
        memory_tools_found = []
        for t in agent.root_agent.tools:
            if (
                hasattr(t, "__name__")
                and t.__name__
                in ["search_past_conversations", "store_important_information"]
            ) or (
                hasattr(t, "name")
                and t.name
                in ["search_past_conversations", "store_important_information"]
            ):
                name = getattr(t, "__name__", getattr(t, "name", str(t)))
                memory_tools_found.append(name)

        if memory_tools_found:
            logging.info(
                f"Memory tools successfully registered: {', '.join(memory_tools_found)}"
            )
        else:
            logging.warning("No memory tools found in the created agent!")

    return agent
