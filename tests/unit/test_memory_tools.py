"""
Unit tests for EX28 terse-memory storage constraints in store_important_information.
"""

from unittest.mock import MagicMock

from radbot.tools.memory.memory_tools import store_important_information


def _make_context():
    mock_context = MagicMock()
    mock_memory_service = MagicMock()
    mock_invocation_ctx = MagicMock()
    mock_invocation_ctx.memory_service = mock_memory_service
    mock_invocation_ctx.user_id = "user123"
    mock_context._invocation_context = mock_invocation_ctx
    mock_memory_service._create_memory_point.return_value = MagicMock()
    return mock_context, mock_memory_service


class TestTerseMemoryConstraints:
    """EX28: two-tier stateless length guard on store_important_information."""

    def test_store_important_information_under_limit_succeeds(self):
        """Content under 500 chars is stored and returns a success dict."""
        mock_context, mock_memory_service = _make_context()
        info = "a" * 400

        result = store_important_information(
            information=info, tool_context=mock_context
        )

        assert isinstance(result, dict)
        assert result["status"] == "success"
        mock_memory_service._create_memory_point.assert_called_once()
        stored_text = mock_memory_service._create_memory_point.call_args.kwargs["text"]
        assert stored_text == info

    def test_store_important_information_mid_range_returns_error_string(self):
        """Content between 501–1000 chars returns a plain error string (no Qdrant write)."""
        mock_context, mock_memory_service = _make_context()
        info = "b" * 750

        result = store_important_information(
            information=info, tool_context=mock_context
        )

        assert isinstance(result, str)
        assert result.startswith("Error: Memory too long")
        mock_memory_service._create_memory_point.assert_not_called()
        mock_memory_service.client.upsert.assert_not_called()

    def test_store_important_information_over_limit_truncates_and_warns(self):
        """Content over 1000 chars is truncated, stored, and returns a warning string."""
        mock_context, mock_memory_service = _make_context()
        info = "c" * 1500

        result = store_important_information(
            information=info, tool_context=mock_context
        )

        assert isinstance(result, str)
        assert "Warning" in result
        assert "truncated" in result.lower()
        mock_memory_service._create_memory_point.assert_called_once()
        stored_text = mock_memory_service._create_memory_point.call_args.kwargs["text"]
        assert stored_text == "c" * 1000 + "...[TRUNCATED]"
        mock_memory_service.client.upsert.assert_called_once()
