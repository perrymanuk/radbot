"""
Research agent factory.

This module provides factory functions for creating research agents.
"""

import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Import ADK components
from google.adk.tools import FunctionTool

# Import project components
from radbot.agent.research_agent.agent import ResearchAgent
from radbot.config import config_manager

TRANSFER_INSTRUCTIONS = (
    "\n\nCRITICAL RULE — Returning control:\n"
    "1. First, complete your task using your tools and compose your full text response with the results.\n"
    "2. Then, call transfer_to_agent(agent_name='beto') to return control to the main agent.\n"
    "You MUST always do BOTH steps — never return without text content, and never skip the transfer back."
)


def create_research_agent(
    name: str = "scout",
    model: Optional[str] = None,
    custom_instruction: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    as_subagent: bool = True,
    enable_google_search: bool = False,
    enable_code_execution: bool = False,
    app_name: str = "beto",
) -> Union[ResearchAgent, Any]:
    """
    Create a research agent with the specified configuration.

    Args:
        name: Name of the agent (should be "scout" for consistent transfers)
        model: LLM model to use (defaults to config setting)
        custom_instruction: Optional custom instruction to override the default
        tools: List of tools to provide to the agent
        as_subagent: Whether to return the ResearchAgent or the underlying ADK agent
        enable_google_search: Whether to enable Google Search capability
        enable_code_execution: Whether to enable Code Execution capability
        app_name: Application name (should match the parent agent name for ADK 0.4.0+)

    Returns:
        Union[ResearchAgent, Any]: The created agent instance
    """
    # Ensure agent name is always "scout" for consistent transfers
    if name != "scout":
        logger.warning(
            f"Agent name '{name}' changed to 'scout' for consistent transfers"
        )
        name = "scout"

    # Use agent-specific model or fall back to default
    if model is None:
        model = config_manager.get_agent_model("scout_agent")
        logger.info(f"Using model from config for scout_agent: {model}")

    # Create the research agent with explicit name and app_name
    research_agent = ResearchAgent(
        name=name,
        model=model,
        instruction=custom_instruction,  # Will use default if None
        tools=tools,
        enable_sequential_thinking=True,
        enable_google_search=enable_google_search,
        enable_code_execution=enable_code_execution,
        app_name=app_name,  # Should match parent agent name
    )

    # Get the ADK agent
    adk_agent = research_agent.get_adk_agent()

    # Add agent-scoped memory tools to scout
    try:
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("scout")
        current_tools = list(adk_agent.tools) if adk_agent.tools else []
        current_tools.extend(memory_tools)
        adk_agent.tools = current_tools
        logger.info("Added agent-scoped memory tools to Scout")
    except Exception as e:
        logger.warning(f"Failed to add memory tools to Scout: {e}")

    # Note: transfer_to_agent is NOT added here explicitly — ADK auto-injects it
    # for any agent that is part of a sub_agents tree. Adding it explicitly causes
    # a "Duplicate function declaration" error from the Gemini API.

    # Scout relies on transfer_to_agent to navigate the agent tree.
    # No sub-agents needed here — search_agent, code_execution_agent, and axel
    # are siblings under beto, and ADK's transfer_to_agent can find them by name.

    # Append mandatory transfer-back instructions
    if hasattr(adk_agent, "instruction") and adk_agent.instruction:
        adk_agent.instruction += TRANSFER_INSTRUCTIONS

    # Return either the ResearchAgent wrapper or the underlying ADK agent
    if as_subagent:
        return research_agent
    else:
        # Double-check agent name before returning
        if hasattr(adk_agent, "name") and adk_agent.name != name:
            logger.warning(
                f"ADK Agent name mismatch: '{adk_agent.name}' not '{name}' - fixing"
            )
            adk_agent.name = name

        return adk_agent
