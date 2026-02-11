"""
Google Search tool integration for ADK.

This module provides factory functions to create and register agents
that use the ADK built-in google_search tool.
"""

import logging
from typing import Any, Optional

from google.adk.agents import Agent, LlmAgent
from google.adk.tools import google_search

from radbot.config import config_manager
from radbot.config.settings import ConfigManager

# Set up logging
logger = logging.getLogger(__name__)


def create_search_agent(
    name: str = "search_agent",
    model: Optional[str] = None,
    config: Optional[ConfigManager] = None,
    instruction_name: str = "search_agent",
) -> Agent:
    """
    Create an agent with Google Search capabilities.

    Args:
        name: Name for the agent (should be "search_agent" for consistent transfers)
        model: Optional model override (defaults to config's main_model)
        config: Optional config manager (uses global if not provided)
        instruction_name: Name of instruction to load from config

    Returns:
        Agent with Google Search tool
    """
    # Ensure agent name is always "search_agent" for consistent transfers
    if name != "search_agent":
        logger.warning(
            f"Agent name '{name}' changed to 'search_agent' for consistent transfers"
        )
        name = "search_agent"

    # Use provided config or default
    cfg = config or config_manager

    # Get the model name (must be a Gemini 2 model)
    # First try to get agent-specific model, then fall back to provided model or defaults
    model_name = model or cfg.get_agent_model("search_agent")
    if not any(
        name in model_name.lower() for name in ["gemini-2", "gemini-2.0", "gemini-2.5"]
    ):
        logger.warning(
            f"Model {model_name} may not be compatible with google_search tool. "
            "Google Search tool requires Gemini 2 models."
        )

    # Get the instruction
    try:
        instruction = cfg.get_instruction(instruction_name)
    except FileNotFoundError:
        # Use a minimal instruction if the named one isn't found
        logger.warning(
            f"Instruction '{instruction_name}' not found for search agent, "
            "using minimal instruction"
        )
        instruction = (
            "You are a web search agent. When asked about recent events, news, "
            "or facts that may have changed since your training, use the Google Search "
            "tool to find current information. Always cite your sources clearly. "
            "When you don't need to search, answer from your knowledge."
        )

    tools = [google_search]

    # Disallow transfer_to_agent injection because google_search (a grounding
    # tool) cannot be mixed with function declarations on gemini-2.5-flash.
    # Control returns to the caller automatically when the agent finishes.
    search_agent = Agent(
        name=name,
        model=model_name,
        instruction=instruction,
        description="A specialized agent that can search the web using Google Search.",
        tools=tools,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    # Enable search explicitly if using Vertex AI
    if cfg.is_using_vertex_ai():
        try:
            from google.genai import types

            # Handle different import paths for ToolGoogleSearch
            try:
                # Try to import from types directly (newer versions)
                ToolGoogleSearch = types.ToolGoogleSearch
            except AttributeError:
                try:
                    # Try to import from separate types classes (older versions)
                    from google.genai.types.tool_types import ToolGoogleSearch
                except ImportError:
                    # Define a minimal wrapper if not available
                    class ToolGoogleSearch:
                        def __init__(self):
                            pass

            # In ADK 0.4.0+, we should always use set_config method
            # The "config" attribute no longer exists directly on Agent class

            # Initialize a Google Search tool config with Vertex AI
            google_search_config = types.GenerateContentConfig()
            google_search_config.tools = [types.Tool(google_search=ToolGoogleSearch())]

            # Use set_config if available (ADK 0.4.0+)
            if hasattr(search_agent, "set_config"):
                search_agent.set_config(google_search_config)
                logger.info(
                    "Set Google Search config via set_config method for Vertex AI"
                )
            else:
                # Fall back to direct attribute setting as a last resort
                try:
                    search_agent.config = google_search_config
                    logger.info(
                        "Added config attribute directly for Google Search with Vertex AI"
                    )
                except Exception as e:
                    logger.warning(f"Unable to set Google Search config: {str(e)}")
        except Exception as e:
            logger.warning(f"Failed to configure Google Search for Vertex AI: {str(e)}")

    logger.info(f"Created search agent '{name}' with google_search tool")
    return search_agent
