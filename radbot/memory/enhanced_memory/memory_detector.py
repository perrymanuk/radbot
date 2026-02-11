"""
Memory detector for enhanced memory system.

This module implements a keyword-based memory detection system that can identify
when to store higher-resolution memories based on trigger words and custom tags.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Set up logging
logger = logging.getLogger(__name__)


class MemoryDetector:
    """
    Monitors user input for keywords that trigger memory storage at different resolutions.

    This class implements the memory detection system described in the memory system
    upgrade design document. It detects trigger keywords for different memory types
    and extracts custom tags with the beto_ prefix.
    """

    def __init__(
        self,
        memory_triggers: Optional[List[str]] = None,
        fact_triggers: Optional[List[str]] = None,
        tag_prefix: str = "beto_",
    ):
        """
        Initialize the memory detector with trigger keywords.

        Args:
            memory_triggers: List of keywords that trigger 'memories' storage
            fact_triggers: List of keywords that trigger 'important_fact' storage
            tag_prefix: Prefix for custom tags (default: 'beto_')
        """
        # Default memory triggers (collaborative achievements, design discussions)
        self.memory_triggers = memory_triggers or [
            "we designed",
            "we built",
            "our plan for",
            "achieved together",
            "this setup for",
            "memory goal:",
            "let's save this",
            "memory:",
            "remember this conversation",
            "save this design",
            "save our work",
            "store this idea",
        ]

        # Default fact triggers (explicit facts, preferences, key details)
        self.fact_triggers = fact_triggers or [
            "important:",
            "remember this fact:",
            "my preference is",
            "I always do",
            "key detail:",
            "memorize this:",
            "fact:",
            "never forget:",
            "critical info:",
            "note this:",
            "remember:",
            "store this fact",
        ]

        # Tag prefix for custom tags
        self.tag_prefix = tag_prefix

        # Compile regex patterns for efficient matching
        self._compile_patterns()

        logger.info(
            f"Memory detector initialized with {len(self.memory_triggers)} memory triggers "
            f"and {len(self.fact_triggers)} fact triggers"
        )

    def _compile_patterns(self):
        """Compile regex patterns for keyword and tag detection."""

        def _make_pattern(trigger):
            """Build a regex pattern with word boundaries that handles non-word trailing chars."""
            escaped = re.escape(trigger)
            # Only add trailing \b if trigger ends with a word character
            if trigger and (trigger[-1].isalnum() or trigger[-1] == "_"):
                return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
            return re.compile(rf"\b{escaped}", re.IGNORECASE)

        # Case-insensitive patterns for memory triggers
        self.memory_patterns = [_make_pattern(t) for t in self.memory_triggers]

        # Case-insensitive patterns for fact triggers
        self.fact_patterns = [_make_pattern(t) for t in self.fact_triggers]

        # Pattern for detecting custom tags with the specified prefix
        # Matches both hashtag (#beto_tag) and mention (@beto_tag) formats
        self.tag_pattern = re.compile(
            rf"[#@]({re.escape(self.tag_prefix)}[a-zA-Z0-9_]+)"
        )

    def analyze_message(self, message: str) -> Dict[str, Any]:
        """
        Analyze a user message for memory triggers and custom tags.

        Args:
            message: The user message to analyze

        Returns:
            A dictionary with the analysis results:
            {
                'memory_type': None or 'memories' or 'important_fact',
                'trigger_word': The specific trigger word detected or None,
                'custom_tags': List of detected custom tags,
                'reference_type': 'current' or 'previous', whether the memory refers to current
                                  or previous message(s)
            }
        """
        result = {
            "memory_type": None,
            "trigger_word": None,
            "custom_tags": [],
            "reference_type": "current",
        }

        # Check for memory triggers
        for pattern in self.memory_patterns:
            match = pattern.search(message)
            if match:
                result["memory_type"] = "memories"
                result["trigger_word"] = match.group(0)
                break

        # Check for fact triggers if no memory trigger was found
        if not result["memory_type"]:
            for pattern in self.fact_patterns:
                match = pattern.search(message)
                if match:
                    result["memory_type"] = "important_fact"
                    result["trigger_word"] = match.group(0)
                    break

        # Extract custom tags
        tag_matches = self.tag_pattern.findall(message)
        if tag_matches:
            result["custom_tags"] = tag_matches

        # Check for reference to previous messages
        if any(
            ref in message.lower()
            for ref in ["last message", "previous message", "earlier", "above"]
        ):
            result["reference_type"] = "previous"

        return result

    def extract_information_text(
        self,
        message: str,
        analysis: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Extract the relevant text to be stored based on the message analysis.

        Args:
            message: The user message
            analysis: The analysis result from analyze_message()
            conversation_history: Optional list of previous conversation turns

        Returns:
            The text to be stored as a memory
        """
        # If we need to extract from previous messages
        if analysis["reference_type"] == "previous" and conversation_history:
            # Get the last user message from history (excluding current message)
            for turn in reversed(conversation_history[:-1]):
                if turn.get("role") == "user":
                    return turn.get("content", "")

        # For current message, we try to extract the relevant information
        if analysis["trigger_word"]:
            # Remove trigger word and tags from the message if possible
            information = message

            # Remove the trigger word and anything before it
            if analysis["trigger_word"] in message:
                trigger_index = message.find(analysis["trigger_word"])
                information = message[
                    trigger_index + len(analysis["trigger_word"]) :
                ].strip()

                # If information is empty, use the whole message
                if not information:
                    information = message

            # Remove custom tags
            for tag in analysis.get("custom_tags", []):
                information = (
                    information.replace(f"#{tag}", "").replace(f"@{tag}", "").strip()
                )

            return information

        # Default: return the original message
        return message

    def prepare_memory_metadata(
        self,
        memory_type: str,
        custom_tags: List[str],
        user_id: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare metadata for memory storage.

        Args:
            memory_type: Type of memory ('memories' or 'important_fact')
            custom_tags: List of custom tags
            user_id: User ID
            session_id: Optional session ID

        Returns:
            Dictionary of metadata for memory storage
        """
        metadata = {"memory_type": memory_type, "user_id": user_id}

        # Add session ID if provided
        if session_id:
            metadata["session_id"] = session_id

        # Add custom tags if present
        if custom_tags:
            for i, tag in enumerate(custom_tags):
                metadata[f"custom_tag_{i}"] = tag

            # Store a combined tags field for easier searching
            metadata["custom_tags"] = ",".join(custom_tags)

        return metadata


def get_memory_detector(**kwargs) -> MemoryDetector:
    """
    Create and return a memory detector with optional custom configuration.

    Args:
        **kwargs: Optional configuration parameters for MemoryDetector

    Returns:
        Configured MemoryDetector instance
    """
    return MemoryDetector(**kwargs)
