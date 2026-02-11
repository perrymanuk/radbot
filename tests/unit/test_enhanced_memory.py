"""
Tests for the enhanced memory system.

This module contains unit tests for the memory detector, memory manager,
and enhanced memory agent components.
"""

import unittest
from unittest.mock import MagicMock, patch

from radbot.memory.enhanced_memory.memory_detector import MemoryDetector
from radbot.memory.enhanced_memory.memory_manager import EnhancedMemoryManager


class TestMemoryDetector(unittest.TestCase):
    """Test the memory trigger detection and text extraction functionality."""

    def setUp(self):
        """Set up memory detector for testing."""
        self.detector = MemoryDetector()

    def test_memory_trigger_detection(self):
        """Test detection of memory triggers."""
        # Test memory type triggers
        memory_messages = [
            "we designed a new system yesterday",
            "Our plan for the next release involves...",
            "We achieved together a great milestone",
            "memory goal: implement the new feature",
        ]

        for message in memory_messages:
            analysis = self.detector.analyze_message(message)
            self.assertEqual(
                analysis["memory_type"],
                "memories",
                f"Failed to detect memory trigger in: {message}",
            )

        # Test fact type triggers
        fact_messages = [
            "important: always use Python 3.10+",
            "remember this fact: the server is at 192.168.1.100",
            "my preference is to use black for formatting",
            "key detail: API keys are stored in .env file",
        ]

        for message in fact_messages:
            analysis = self.detector.analyze_message(message)
            self.assertEqual(
                analysis["memory_type"],
                "important_fact",
                f"Failed to detect fact trigger in: {message}",
            )

    def test_no_trigger_detection(self):
        """Test that non-trigger messages are correctly identified."""
        regular_messages = [
            "How are you today?",
            "Let's work on the new feature",
            "Can you help me with this bug?",
            "What's the status of the project?",
        ]

        for message in regular_messages:
            analysis = self.detector.analyze_message(message)
            self.assertIsNone(
                analysis["memory_type"], f"Incorrectly detected trigger in: {message}"
            )

    def test_custom_tag_extraction(self):
        """Test extraction of custom tags."""
        # Test with hashtag format
        message_with_hashtags = "we designed a new UI component #beto_design #beto_ui"
        analysis = self.detector.analyze_message(message_with_hashtags)
        self.assertEqual(set(analysis["custom_tags"]), {"beto_design", "beto_ui"})

        # Test with @ format
        message_with_at = "important: server config @beto_infrastructure @beto_security"
        analysis = self.detector.analyze_message(message_with_at)
        self.assertEqual(
            set(analysis["custom_tags"]), {"beto_infrastructure", "beto_security"}
        )

        # Test mixed formats
        message_mixed = "memory goal: document API #beto_api @beto_docs"
        analysis = self.detector.analyze_message(message_mixed)
        self.assertEqual(set(analysis["custom_tags"]), {"beto_api", "beto_docs"})

    def test_text_extraction(self):
        """Test extraction of relevant text from messages."""
        # Test extraction after trigger word
        message = "important: The API key needs to be rotated monthly."
        analysis = self.detector.analyze_message(message)
        extracted = self.detector.extract_information_text(message, analysis)
        self.assertEqual(extracted, "The API key needs to be rotated monthly.")

        # Test extraction with custom tags
        message = "we designed a new algorithm #beto_algorithm today"
        analysis = self.detector.analyze_message(message)
        extracted = self.detector.extract_information_text(message, analysis)
        self.assertNotIn("#beto_algorithm", extracted)
        self.assertIn("a new algorithm", extracted)

        # Test previous message reference
        message = "Please remember the previous message"
        analysis = self.detector.analyze_message(message)
        history = [
            {"role": "user", "content": "The database password is DB_SECRET_123"},
            {"role": "assistant", "content": "I understand."},
            {"role": "user", "content": message},
        ]
        extracted = self.detector.extract_information_text(message, analysis, history)
        self.assertEqual(extracted, "The database password is DB_SECRET_123")


class TestMemoryManager(unittest.TestCase):
    """Test the memory manager functionality."""

    def setUp(self):
        """Set up memory manager for testing."""
        self.detector = MemoryDetector()
        self.memory_manager = EnhancedMemoryManager(memory_detector=self.detector)

    @patch("radbot.memory.enhanced_memory.memory_manager.store_important_information")
    def test_process_message_with_trigger(self, mock_store):
        """Test processing a message with a memory trigger."""
        # Mock the store_important_information function
        mock_store.return_value = {
            "status": "success",
            "message": "Successfully stored.",
        }

        # Test with a memory trigger
        message = "memory goal: implement the webhook handler #beto_api"
        result = self.memory_manager.process_message(message, user_id="test_user")

        # Verify store_important_information was called with correct parameters
        mock_store.assert_called_once()
        args, kwargs = mock_store.call_args
        self.assertEqual(kwargs["memory_type"], "memories")
        self.assertIn("beto_api", str(kwargs["metadata"]))

        # Verify the message was added to history
        self.assertEqual(len(self.memory_manager.conversation_history), 1)
        self.assertEqual(
            self.memory_manager.conversation_history[0]["content"], message
        )

    @patch("radbot.memory.enhanced_memory.memory_manager.store_important_information")
    def test_process_message_no_trigger(self, mock_store):
        """Test processing a message without a memory trigger."""
        message = "How's the project going?"
        result = self.memory_manager.process_message(message, user_id="test_user")

        # Verify store_important_information was not called
        mock_store.assert_not_called()

        # Verify status is correct
        self.assertEqual(result["status"], "no_trigger")

        # Verify the message was still added to history
        self.assertEqual(len(self.memory_manager.conversation_history), 1)
        self.assertEqual(
            self.memory_manager.conversation_history[0]["content"], message
        )

    def test_conversation_history_management(self):
        """Test conversation history management."""
        # Process a user message
        self.memory_manager.process_message("Hello", user_id="test_user")

        # Record an agent response
        self.memory_manager.record_agent_response("Hi there!")

        # Verify history contains both messages
        self.assertEqual(len(self.memory_manager.conversation_history), 2)
        self.assertEqual(self.memory_manager.conversation_history[0]["role"], "user")
        self.assertEqual(
            self.memory_manager.conversation_history[1]["role"], "assistant"
        )

        # Test clearing history
        self.memory_manager.clear_conversation_history()
        self.assertEqual(len(self.memory_manager.conversation_history), 0)


if __name__ == "__main__":
    unittest.main()
