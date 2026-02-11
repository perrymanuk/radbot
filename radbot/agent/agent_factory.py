"""
Factory class for creating and configuring agents.

This module provides the AgentFactory class with methods for creating
root agents, sub-agents, and web agents.
"""

import logging
from typing import Any, Dict, List, Optional, Union

# Import necessary components
from google.adk.agents import Agent
from google.adk.tools.transfer_to_agent_tool import transfer_to_agent

# Configure logging
logger = logging.getLogger(__name__)

from radbot.agent.agent_base import FALLBACK_INSTRUCTION

# Import our configuration modules
from radbot.config import config_manager
from radbot.config.settings import ConfigManager


class AgentFactory:
    """Factory class for creating and configuring agents."""

    @staticmethod
    def create_root_agent(
        name: str = "beto",
        model: Optional[str] = None,
        tools: Optional[List] = None,
        instruction_name: str = "main_agent",
        config: Optional[ConfigManager] = None,
    ) -> Agent:
        """Create the main root agent.

        Args:
            name: Name of the agent
            model: Model to use (if None, uses config's main_model)
            tools: List of tools to add to the agent
            instruction_name: Name of the instruction to load from config
            config: Optional ConfigManager instance (uses global if not provided)

        Returns:
            Configured root agent
        """
        # Use provided config or default
        cfg = config or config_manager

        # Get the model name
        model_name = model or cfg.get_main_model()

        # Get the instruction
        try:
            instruction = cfg.get_instruction(instruction_name)
        except FileNotFoundError:
            # Fall back to default instruction
            instruction = FALLBACK_INSTRUCTION

        # Create the root agent
        root_agent = Agent(
            name=name,
            model=model_name,
            instruction=instruction,
            description="The main coordinating agent that handles user requests and orchestrates tasks.",
            tools=tools or [],  # Initialize with provided tools or empty list
        )

        return root_agent

    @staticmethod
    def create_sub_agent(
        name: str,
        description: str,
        instruction_name: str,
        tools: Optional[List] = None,
        model: Optional[str] = None,
        config: Optional[ConfigManager] = None,
    ) -> Agent:
        """Create a sub-agent with appropriate model and configuration.

        Args:
            name: Name of the sub-agent
            description: Description of the sub-agent's capabilities
            instruction_name: Name of the instruction to load from config
            tools: List of tools to add to the agent
            model: Optional model override (if None, uses config's sub_agent_model)
            config: Optional ConfigManager instance (uses global if not provided)

        Returns:
            Configured sub-agent
        """
        # Use provided config or default
        cfg = config or config_manager

        # Get the model name (use sub-agent model by default)
        model_name = model or cfg.get_sub_agent_model()

        # Get the instruction
        try:
            instruction = cfg.get_instruction(instruction_name)
        except FileNotFoundError:
            # Use a minimal instruction if the named one isn't found
            logger.warning(
                f"Instruction '{instruction_name}' not found for sub-agent, using minimal instruction"
            )
            instruction = f"You are a specialized {name} agent. {description}"

        # Create the sub-agent
        sub_agent = Agent(
            name=name,
            model=model_name,
            instruction=instruction,
            description=description,
            tools=tools or [],
        )

        return sub_agent

    @staticmethod
    def create_web_agent(
        name: str = "beto",
        model: Optional[str] = None,
        tools: Optional[List] = None,
        instruction_name: str = "main_agent",
        config: Optional[ConfigManager] = None,
        register_tools: bool = True,
    ) -> Agent:
        """Create an agent specifically for the ADK web interface.

        Args:
            name: Name of the agent
            model: Model to use (if None, uses config's main_model)
            tools: List of tools to add to the agent
            instruction_name: Name of the instruction to load from config
            config: Optional ConfigManager instance (uses global if not provided)
            register_tools: Whether to register common tool handlers

        Returns:
            Configured ADK Agent for web interface
        """
        # Create the base agent
        agent = AgentFactory.create_root_agent(
            name=name,
            model=model,
            tools=tools,
            instruction_name=instruction_name,
            config=config,
        )

        # Initialize memory service for the web UI and store API keys
        try:
            import os

            from radbot.memory.qdrant_memory import QdrantMemoryService

            memory_service = QdrantMemoryService()
            logger.info("Successfully initialized QdrantMemoryService for web agent")

            # Store memory service in ADK's global tool context
            from google.adk.tools.tool_context import ToolContext

            # Directly use setattr to add memory service to tool context
            # This makes it accessible in tool implementations
            setattr(ToolContext, "memory_service", memory_service)
            logger.info("Added memory service to tool context")

        except Exception as e:
            logger.warning(f"Failed to initialize memory service: {str(e)}")

        # Register common tool handlers if requested
        if register_tools:
            try:
                # Use the equivalent of RadBotAgent.register_tool_handlers but for a plain Agent
                from radbot.tools.mcp.mcp_fileserver_client import (
                    handle_fileserver_tool_call,
                )
                from radbot.tools.memory.memory_tools import (
                    search_past_conversations,
                    store_important_information,
                )

                # Register filesystem tool handlers
                agent.register_tool_handler(
                    "list_files",
                    lambda params: handle_fileserver_tool_call("list_files", params),
                )
                agent.register_tool_handler(
                    "read_file",
                    lambda params: handle_fileserver_tool_call("read_file", params),
                )
                agent.register_tool_handler(
                    "write_file",
                    lambda params: handle_fileserver_tool_call("write_file", params),
                )
                agent.register_tool_handler(
                    "delete_file",
                    lambda params: handle_fileserver_tool_call("delete_file", params),
                )
                agent.register_tool_handler(
                    "get_file_info",
                    lambda params: handle_fileserver_tool_call("get_file_info", params),
                )
                agent.register_tool_handler(
                    "search_files",
                    lambda params: handle_fileserver_tool_call("search_files", params),
                )
                agent.register_tool_handler(
                    "create_directory",
                    lambda params: handle_fileserver_tool_call(
                        "create_directory", params
                    ),
                )

                # Register memory tools
                agent.register_tool_handler(
                    "search_past_conversations",
                    lambda params: MessageToDict(search_past_conversations(params)),
                )
                agent.register_tool_handler(
                    "store_important_information",
                    lambda params: MessageToDict(store_important_information(params)),
                )

                # In ADK 0.4.0, agent transfers are handled natively
                # No need to register custom transfer_to_agent handler

                logger.info("Registered common tool handlers for web agent")
            except Exception as e:
                logger.warning(
                    f"Error registering tool handlers for web agent: {str(e)}"
                )

        return agent
