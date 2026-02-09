"""
Core agent creation and configuration for RadBot.

This module provides the main agent creation and configuration functionality 
for the RadBot agent system, creating the root agent with all needed tools.
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
    config_manager
)

from radbot.agent.agent_tools_setup import (
    tools,
    setup_before_agent_call,
    search_agent,
    code_execution_agent,
    scout_agent
)

# Import specialized agents factory
from radbot.agent.specialized_agent_factory import create_specialized_agents

# Import memory tools and services
from radbot.memory.qdrant_memory import QdrantMemoryService
from radbot.tools.memory import search_past_conversations, store_important_information
from radbot.config.config_loader import config_loader

# Get the instruction from the config manager
instruction = config_manager.get_instruction("main_agent")

# The specialized agent tools are now included directly in the main_agent.md file
# to reduce duplication and token usage, so we don't need to add them here
# instruction += """
# ## Specialized Agent Tools
# 
# You have access to specialized agents through these tools:
# 
# 1. `call_search_agent(query, max_results=5)` - Perform web searches using Google Search.
#    Example: call_search_agent(query="latest news on quantum computing")
# 
# 2. `call_code_execution_agent(code, description="")` - Execute Python code.
#    Example: call_code_execution_agent(code="print('Hello world')", description="Simple test")
# 
# 3. `call_scout_agent(research_topic)` - Research a topic using a specialized agent.
#    Example: call_scout_agent(research_topic="environmental impact of electric vehicles")
# 
# Use these tools when you need specialized capabilities.
# """

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
            api_key=api_key
        )
        logger.info(f"Successfully initialized QdrantMemoryService with collection '{collection}'")

        # Add memory tools to the tools list if they're not already included
        memory_tools = [search_past_conversations, store_important_information]
        tool_names = [tool.__name__ if hasattr(tool, '__name__') else tool.name if hasattr(tool, 'name') else None for tool in tools]

        for memory_tool in memory_tools:
            tool_name = memory_tool.__name__ if hasattr(memory_tool, '__name__') else None
            if tool_name and tool_name not in tool_names:
                tools.append(memory_tool)
                logger.info(f"Added memory tool: {tool_name}")

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

# Create the root agent
root_agent = Agent(
    model=model_name,
    name="beto",
    instruction=instruction,
    global_instruction=f"""Today's date: {today}""",
    sub_agents=[search_agent, code_execution_agent, scout_agent],
    tools=tools,
    before_agent_callback=setup_before_agent_call,
    generate_content_config=types.GenerateContentConfig(temperature=0.2),
)

# Create specialized agents (including Axel)
specialized_agents = create_specialized_agents(root_agent)
logger.info(f"Created {len(specialized_agents)} specialized agents (including Axel)")

# Store memory_service as an attribute of the agent after creation
# This attribute will be used by the Runner in web/api/session.py
if memory_service:
    root_agent._memory_service = memory_service
    logger.info("Added memory_service to root_agent as _memory_service attribute")

# Log agent creation
logger.info(f"Created root agent 'beto' with {len(tools)} tools and {len(root_agent.sub_agents)} sub-agents")

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