"""
Enhanced memory manager for radbot.

This module implements the memory system upgrade as described in the design document,
providing a multi-layered memory system with different resolutions and tagging capabilities.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from google.adk.tools.tool_context import ToolContext

from radbot.memory.enhanced_memory.memory_detector import MemoryDetector
from radbot.tools.memory.memory_tools import store_important_information

# Set up logging
logger = logging.getLogger(__name__)


class EnhancedMemoryManager:
    """
    Enhanced memory manager that provides multi-layered memory capabilities.

    This class implements the memory system upgrade described in the design document,
    providing different "resolutions" of memory: raw chat (low), general memories (medium),
    and important facts (high).
    """

    def __init__(
        self,
        memory_detector: Optional[MemoryDetector] = None,
        memory_service=None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize the enhanced memory manager.

        Args:
            memory_detector: Optional custom memory detector
            memory_service: Optional memory service for direct access
            conversation_history: Optional list to track conversation history
        """
        # Create or use provided memory detector
        self.memory_detector = memory_detector or MemoryDetector()

        # Store the memory service if provided
        self.memory_service = memory_service

        # Initialize conversation history
        self.conversation_history = conversation_history or []

        logger.info("Enhanced memory manager initialized")

    def process_message(
        self,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        tool_context: Optional[ToolContext] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message for memory triggers and store appropriate memories.

        Args:
            message: The user's message
            user_id: User identifier
            session_id: Optional session identifier
            tool_context: Optional tool context for memory storage

        Returns:
            Result of memory processing with status information
        """
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": message})

        # Analyze message for memory triggers
        analysis = self.memory_detector.analyze_message(message)

        # If no memory trigger detected, just return
        if not analysis["memory_type"]:
            return {"status": "no_trigger", "message": "No memory triggers detected."}

        # Extract text to be stored
        information = self.memory_detector.extract_information_text(
            message=message,
            analysis=analysis,
            conversation_history=self.conversation_history,
        )

        # Prepare metadata with custom tags
        metadata = self.memory_detector.prepare_memory_metadata(
            memory_type=analysis["memory_type"],
            custom_tags=analysis.get("custom_tags", []),
            user_id=user_id,
            session_id=session_id,
        )

        # Store the memory
        try:
            result = store_important_information(
                information=information,
                memory_type=analysis["memory_type"],
                metadata=metadata,
                tool_context=tool_context,
            )

            logger.info(
                f"Stored {analysis['memory_type']} memory "
                f"triggered by '{analysis['trigger_word']}'"
            )

            # Add custom tag info to result
            if analysis.get("custom_tags"):
                result["custom_tags"] = analysis["custom_tags"]

            return result

        except Exception as e:
            logger.error(f"Error storing memory: {str(e)}")
            return {
                "status": "error",
                "error_message": f"Failed to store memory: {str(e)}",
            }

    def record_agent_response(self, response: str) -> None:
        """
        Record an agent's response in the conversation history.

        Args:
            response: The agent's response text
        """
        self.conversation_history.append({"role": "assistant", "content": response})

    def clear_conversation_history(self) -> None:
        """Clear the stored conversation history."""
        self.conversation_history = []


def create_enhanced_memory_manager(
    memory_service=None, **kwargs
) -> EnhancedMemoryManager:
    """
    Create and configure an EnhancedMemoryManager.

    Args:
        memory_service: Optional memory service to use
        **kwargs: Additional configuration options

    Returns:
        Configured EnhancedMemoryManager instance
    """
    # Create memory detector with any provided options
    memory_detector = MemoryDetector(**kwargs.get("detector_config", {}))

    # Create and return the manager
    return EnhancedMemoryManager(
        memory_detector=memory_detector, memory_service=memory_service
    )
