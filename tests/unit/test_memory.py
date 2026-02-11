"""
Unit tests for the memory system.
"""

import enum
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from qdrant_client import QdrantClient, models


# Patch the PayloadSchemaType in models before importing the modules that use it
# This avoids the need for patching in each test
class MockPayloadSchemaType(enum.Enum):
    """Mock enum for Qdrant models.PayloadSchemaType."""

    KEYWORD = "keyword"
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    DATETIME = "datetime"
    GEO = "geo"
    BOOL = "bool"


# Save the original and replace with mock
original_payload_schema_type = models.PayloadSchemaType
models.PayloadSchemaType = MockPayloadSchemaType

# Import needed modules
from radbot.memory.embedding import EmbeddingModel, embed_text
from radbot.memory.qdrant_memory import QdrantMemoryService
from radbot.tools.memory.memory_tools import (
    search_past_conversations,
    store_important_information,
)


class TestEmbedding:
    """Tests for the embedding module."""

    def test_embedding_model_dataclass(self):
        """Test the EmbeddingModel dataclass."""
        model = EmbeddingModel(name="test-model", vector_size=768, client=MagicMock())
        assert model.name == "test-model"
        assert model.vector_size == 768
        assert isinstance(model.client, MagicMock)

    @patch("radbot.memory.embedding._initialize_gemini_embedding")
    def test_get_embedding_model_gemini(self, mock_init):
        """Test getting Gemini embedding model."""
        from radbot.memory.embedding import get_embedding_model

        # Mock the initialization function
        mock_model = EmbeddingModel(
            name="mock-gemini", vector_size=768, client=MagicMock()
        )
        mock_init.return_value = mock_model

        # Call the function with environment set to use gemini
        with patch.dict("os.environ", {"radbot_EMBED_MODEL": "gemini"}):
            model = get_embedding_model()

        # Verify the result
        assert model == mock_model
        mock_init.assert_called_once()

    def test_embed_text_with_gemini(self):
        """Test embedding text with Gemini model."""
        # Setup mock embedding model
        model = MagicMock()
        model.name = "gemini-embedding-001"
        model.vector_size = 3

        # Mock the client.models.embed_content method (actual API path)
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2, 0.3]
        mock_result = MagicMock()
        mock_result.embeddings = [mock_embedding]
        model.client.models.embed_content.return_value = mock_result

        # Call the function
        result = embed_text("test text", model)

        # Verify the result
        assert result == [0.1, 0.2, 0.3]


class TestQdrantMemoryService:
    """Tests for the QdrantMemoryService class."""

    @patch("radbot.memory.qdrant_memory.QdrantClient")
    @patch("radbot.memory.qdrant_memory.get_embedding_model")
    def test_init_with_host_port(self, mock_get_model, mock_client):
        """Test initialization with host and port."""
        # Setup mocks
        mock_model = MagicMock()
        mock_model.vector_size = 768
        mock_get_model.return_value = mock_model

        # Setup client instance mock
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance

        # Mock the collections response
        collections_response = MagicMock()
        collections_response.collections = []
        mock_client_instance.get_collections.return_value = collections_response

        # Initialize the service
        with patch.dict("os.environ", {}, clear=False):
            # Remove QDRANT_COLLECTION if set to test defaults
            import os

            old_val = os.environ.pop("QDRANT_COLLECTION", None)
            try:
                service = QdrantMemoryService(host="localhost", port=6333)
            finally:
                if old_val is not None:
                    os.environ["QDRANT_COLLECTION"] = old_val

        # Verify client initialization
        assert mock_client.call_count == 1
        call_kwargs = mock_client.call_args.kwargs
        assert call_kwargs["prefer_grpc"] is False

        # Verify collection initialization was attempted
        mock_client_instance.get_collections.assert_called_once()

    @patch("radbot.memory.qdrant_memory.QdrantClient")
    @patch("radbot.memory.qdrant_memory.get_embedding_model")
    def test_init_with_url_api_key(self, mock_get_model, mock_client):
        """Test initialization with URL and API key."""
        # Setup mocks
        mock_model = MagicMock()
        mock_model.vector_size = 768
        mock_get_model.return_value = mock_model

        # Setup client instance mock
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance

        # Mock the collections response
        collections_response = MagicMock()
        collections_response.collections = []
        mock_client_instance.get_collections.return_value = collections_response

        # Initialize the service
        service = QdrantMemoryService(url="https://test.qdrant.io", api_key="test-key")

        # Verify client initialization
        mock_client.assert_called_once_with(
            url="https://test.qdrant.io", api_key="test-key", prefer_grpc=False
        )

    @patch("radbot.memory.qdrant_memory.QdrantClient")
    @patch("radbot.memory.qdrant_memory.get_embedding_model")
    def test_search_memory(self, mock_get_model, mock_client):
        """Test searching memory."""
        # Setup mocks
        mock_model = MagicMock()
        mock_model.vector_size = 768
        mock_get_model.return_value = mock_model

        # Setup client instance mock
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance

        # Mock the collections response
        collections_response = MagicMock()
        collections_response.collections = []
        mock_client_instance.get_collections.return_value = collections_response

        # Mock embedding function
        with patch("radbot.memory.qdrant_memory.embed_text") as mock_embed:
            mock_vector = [0.1] * 768
            mock_embed.return_value = mock_vector

            # Mock search results - query_points returns a response with .points
            mock_point = MagicMock()
            mock_point.payload = {
                "text": "Test memory",
                "memory_type": "test",
                "timestamp": "2023-01-01T00:00:00",
            }
            mock_point.score = 0.95

            # Set up the client query_points mock (code uses query_points, not search)
            mock_query_response = MagicMock()
            mock_query_response.points = [mock_point]
            mock_client_instance.query_points.return_value = mock_query_response

            # Initialize service (without QDRANT_COLLECTION env var interference)
            import os

            old_val = os.environ.pop("QDRANT_COLLECTION", None)
            try:
                service = QdrantMemoryService(collection_name="test_memories")
            finally:
                if old_val is not None:
                    os.environ["QDRANT_COLLECTION"] = old_val

            results = service.search_memory(
                app_name="test-app", user_id="user123", query="test query", limit=5
            )

            # Verify query_points was called
            mock_client_instance.query_points.assert_called_once()
            call_args = mock_client_instance.query_points.call_args[1]
            assert call_args["collection_name"] == "test_memories"
            assert call_args["query"] == mock_vector
            assert call_args["limit"] == 5

            # Verify results
            assert len(results) == 1
            assert results[0]["text"] == "Test memory"
            assert results[0]["memory_type"] == "test"
            assert results[0]["relevance_score"] == 0.95


class TestMemoryTools:
    """Tests for memory tools."""

    def test_search_past_conversations_without_context(self):
        """Test search tool without tool context."""
        result = search_past_conversations("test query")
        # The behavior has changed - now it uses a default web_user
        assert "status" in result
        assert isinstance(result, dict)

    def test_search_past_conversations_with_context(self):
        """Test search tool with proper context."""
        # Create mock tool context with _invocation_context
        mock_context = MagicMock()
        mock_memory_service = MagicMock()
        mock_invocation_ctx = MagicMock()
        mock_invocation_ctx.memory_service = mock_memory_service
        mock_invocation_ctx.user_id = "user123"
        mock_context._invocation_context = mock_invocation_ctx

        # Set up mock search results
        mock_memory_service.search_memory.return_value = [
            {
                "text": "Test memory",
                "memory_type": "conversation_turn",
                "relevance_score": 0.95,
                "timestamp": "2023-01-01T00:00:00",
            }
        ]

        # Call the tool
        result = search_past_conversations(
            query="test query", max_results=3, tool_context=mock_context
        )

        # Verify result
        assert result["status"] == "success"
        assert len(result["memories"]) == 1
        assert result["memories"][0]["text"] == "Test memory"

    def test_store_important_information(self):
        """Test store information tool."""
        # Create mock tool context with _invocation_context
        mock_context = MagicMock()
        mock_memory_service = MagicMock()
        mock_invocation_ctx = MagicMock()
        mock_invocation_ctx.memory_service = mock_memory_service
        mock_invocation_ctx.user_id = "user123"
        mock_context._invocation_context = mock_invocation_ctx

        # Set up mock point creation
        mock_point = MagicMock()
        mock_memory_service._create_memory_point.return_value = mock_point

        # Call the tool
        result = store_important_information(
            information="Important test fact",
            memory_type="important_fact",
            tool_context=mock_context,
        )

        # Verify result
        assert result["status"] == "success"
        mock_memory_service._create_memory_point.assert_called_once_with(
            user_id="user123",
            text="Important test fact",
            metadata={"memory_type": "important_fact"},
        )
        mock_memory_service.client.upsert.assert_called_once()


# Restore the original PayloadSchemaType at the end of tests
def teardown_module():
    """Restore original PayloadSchemaType after all tests are done."""
    import qdrant_client.models as qdrant_models

    qdrant_models.PayloadSchemaType = original_payload_schema_type
