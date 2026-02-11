"""
Base RadBotAgent class implementation.

This module provides the core RadBotAgent class that encapsulates the ADK agent,
runner, and session management.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# Configure logging
logger = logging.getLogger(__name__)

# Type alias for backward compatibility
SessionService = InMemorySessionService

# Load environment variables
load_dotenv()

# Import our configuration modules
from radbot.config import config_manager

# Import our ADK configuration setup to handle Vertex AI settings
from radbot.config.adk_config import setup_vertex_environment
from radbot.config.settings import ConfigManager

# Fallback instruction if configuration loading fails
FALLBACK_INSTRUCTION = """
You are a helpful and versatile AI assistant. Your goal is to understand the user's request
and fulfill it by using available tools, delegating to specialized sub-agents, or accessing 
memory when necessary. Be clear and concise in your responses.
"""


class RadBotAgent:
    """
    Main agent class for the RadBot framework.

    This class encapsulates the ADK agent, runner, and session management.
    It provides a unified interface for interacting with the agent system.
    """

    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        tools: Optional[List[Any]] = None,
        model: Optional[str] = None,
        name: str = "beto",
        instruction: Optional[str] = None,
        instruction_name: Optional[str] = "main_agent",
        config: Optional[ConfigManager] = None,
        memory_service: Optional[Any] = None,
        app_name: str = "beto",
    ):
        """
        Initialize the RadBot agent.

        Args:
            session_service: Optional custom session service for conversation state
            tools: Optional list of tools to provide to the agent
            model: Optional model name (defaults to config's main_model if not provided)
            name: Name for the agent (default: beto)
            instruction: Optional explicit instruction string (overrides instruction_name)
            instruction_name: Optional name of instruction to load from config
            config: Optional ConfigManager instance (uses global if not provided)
            memory_service: Optional custom memory service (tries to create one if None)
            app_name: Application name for session management (default: beto)
        """
        # Use provided config or default
        self.config = config or config_manager

        # Use provided session service or create an in-memory one
        self.session_service = session_service or InMemorySessionService()

        # Store app_name for use with session service
        self.app_name = app_name

        # Determine the model to use
        self.model = model or self.config.get_main_model()

        # Determine instruction to use
        self.instruction_name = instruction_name
        if instruction:
            # Use explicitly provided instruction
            agent_instruction = instruction
        elif instruction_name:
            # Try to load from config, fall back to default if not found
            try:
                agent_instruction = self.config.get_instruction(instruction_name)
            except FileNotFoundError:
                # Log a warning and use fallback instruction
                logger.warning(
                    f"Instruction '{instruction_name}' not found, using fallback"
                )
                agent_instruction = FALLBACK_INSTRUCTION
        else:
            # No instruction or name provided, use fallback
            agent_instruction = FALLBACK_INSTRUCTION

        # Create the main agent
        self.root_agent = Agent(
            name=name,
            model=self.model,
            instruction=agent_instruction,
            description="The main coordinating agent that handles user requests and orchestrates tasks.",
            tools=tools or [],  # Start with empty tools list if none provided
        )

        # Set up memory service if needed
        self._memory_service = memory_service
        if self._memory_service is None and any(
            tool.__name__
            in ["search_past_conversations", "store_important_information"]
            for tool in (tools or [])
            if hasattr(tool, "__name__")
        ):
            # Try to create memory service if memory tools are included but no service provided
            try:
                logger.info("Memory tools detected, trying to create memory service")

                from radbot.memory.qdrant_memory import QdrantMemoryService

                self._memory_service = QdrantMemoryService()
                logger.info("Successfully created QdrantMemoryService")
            except Exception as e:
                logger.warning(f"Failed to create memory service: {str(e)}")
                logger.warning(
                    "Memory tools will not function properly without a memory service"
                )

        # Initialize the runner with the agent and memory service if available
        if self._memory_service:
            self.runner = Runner(
                agent=self.root_agent,
                session_service=self.session_service,
                memory_service=self._memory_service,
            )
            logger.info("Runner initialized with memory service")
        else:
            self.runner = Runner(
                agent=self.root_agent,
                app_name=self.app_name,
                session_service=self.session_service,
            )

        # Enable ADK context caching to reduce API costs
        try:
            from google.adk.agents.context_cache_config import ContextCacheConfig

            self.runner.context_cache_config = ContextCacheConfig(
                cache_intervals=10,
                ttl_seconds=1800,
                min_tokens=4096,
            )
            logger.info("Enabled context caching on CLI Runner")
        except Exception as e:
            logger.warning(f"Could not enable context caching: {e}")
