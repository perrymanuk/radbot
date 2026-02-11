"""
Factory functions for creating agents with enhanced memory capabilities.

This module provides factory functions to create agents with the enhanced
multi-layered memory system as described in the memory system upgrade design.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext

from radbot.agent.agent import RadBotAgent
from radbot.config import config_manager
from radbot.config.config_loader import config_loader
from radbot.memory.enhanced_memory import (
    EnhancedMemoryManager,
    create_enhanced_memory_manager,
)
from radbot.memory.qdrant_memory import QdrantMemoryService
from radbot.tools.memory import search_past_conversations, store_important_information

# Set up logging
logger = logging.getLogger(__name__)


class EnhancedMemoryAgent(RadBotAgent):
    """
    Extended RadBotAgent with enhanced memory capabilities.

    This class extends the base RadBotAgent to include the multi-layered
    memory system as described in the memory system upgrade design.
    """

    def __init__(
        self, memory_manager: Optional[EnhancedMemoryManager] = None, **kwargs
    ):
        """
        Initialize an agent with enhanced memory capabilities.

        Args:
            memory_manager: Optional EnhancedMemoryManager instance
            **kwargs: Arguments to pass to the RadBotAgent constructor
        """
        # Initialize the base RadBotAgent
        super().__init__(**kwargs)

        # Set up the enhanced memory manager
        self.memory_manager = memory_manager or create_enhanced_memory_manager(
            memory_service=self._memory_service
        )

        logger.info("Enhanced memory agent initialized with memory manager")

    def process_message(self, user_id: str, message: str) -> str:
        """
        Process a user message with enhanced memory capabilities.

        This method extends the base process_message method to include
        memory trigger detection and storage using the enhanced memory system.

        Args:
            user_id: Unique identifier for the user
            message: The user's message

        Returns:
            The agent's response as a string
        """
        # Create a tool context for memory operations
        tool_context = ToolContext()
        tool_context.user_id = user_id
        tool_context.memory_service = self._memory_service

        # Check for memory triggers in the message
        memory_result = self.memory_manager.process_message(
            message=message, user_id=user_id, tool_context=tool_context
        )

        # If memory was stored, log the result
        if memory_result["status"] == "success":
            memory_type = memory_result.get("memory_type", "unknown")
            tags = memory_result.get("custom_tags", [])

            # Prepare log message
            log_msg = f"Stored {memory_type} from user message"
            if tags:
                log_msg += f" with tags: {', '.join(tags)}"

            logger.info(log_msg)

        # Process the message using the base RadBotAgent
        response = super().process_message(user_id, message)

        # Record the agent's response in conversation history
        self.memory_manager.record_agent_response(response)

        return response

    def reset_session(self, user_id: str) -> None:
        """
        Reset a user's session and clear conversation history.

        Args:
            user_id: The user ID to reset
        """
        # Reset the base session
        super().reset_session(user_id)

        # Clear the conversation history in the memory manager
        self.memory_manager.clear_conversation_history()


def create_enhanced_memory_agent(
    session_service: Optional[InMemorySessionService] = None,
    tools: Optional[List[Any]] = None,
    memory_service: Optional[QdrantMemoryService] = None,
    instruction_name: str = "main_agent",
    name: str = "enhanced_memory_agent",
    memory_manager_config: Optional[Dict[str, Any]] = None,
) -> EnhancedMemoryAgent:
    """
    Create an agent with enhanced memory capabilities.

    Args:
        session_service: Optional session service for conversation state
        tools: Optional list of tools for the agent
        memory_service: Optional custom memory service (creates one if not provided)
        instruction_name: Name of instruction to load from config
        name: Name for the agent
        memory_manager_config: Optional configuration for the memory manager

    Returns:
        A configured EnhancedMemoryAgent instance
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
        logger.info(
            f"Connecting to Qdrant with: host={host}, port={port}, collection={collection}"
        )
        if url:
            logger.info(f"Using Qdrant URL: {url}")

        # Create memory service
        try:
            memory_service = QdrantMemoryService(
                collection_name=collection,
                host=host,
                port=int(port) if isinstance(port, str) else port,
                url=url,
                api_key=api_key,
            )
            logger.info(
                f"Successfully initialized QdrantMemoryService with collection '{collection}'"
            )
        except Exception as e:
            logger.error(f"Failed to initialize QdrantMemoryService: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    # Ensure memory tools are included
    memory_tools = [search_past_conversations, store_important_information]
    all_tools = list(tools or []) + memory_tools

    # Create the memory manager
    memory_manager = create_enhanced_memory_manager(
        memory_service=memory_service, **(memory_manager_config or {})
    )

    # Create the enhanced memory agent
    model = config_manager.get_main_model()

    # Create the agent with tools and memory service
    agent = EnhancedMemoryAgent(
        memory_manager=memory_manager,
        name=name,
        session_service=session_service,
        tools=all_tools,
        model=model,
        instruction_name=instruction_name,
        memory_service=memory_service,
    )

    return agent
