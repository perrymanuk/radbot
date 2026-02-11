"""
Unit tests for basic tools.
"""

from unittest.mock import MagicMock

import pytest

from radbot.tools.basic import get_current_time


class TestGetCurrentTime:
    def test_get_current_time_success(self):
        """Test successful time retrieval for a known city."""
        result = get_current_time("London")
        assert "The current time in London is" in result

    def test_get_current_time_unknown_city(self):
        """Test error handling for an unknown city."""
        result = get_current_time("UnknownCity")
        assert "don't have timezone information" in result

    def test_get_current_time_with_context(self):
        """Test that tool_context is used to store last city."""
        mock_context = MagicMock()
        mock_context.state = {}

        result = get_current_time("Tokyo", tool_context=mock_context)

        assert "The current time in Tokyo is" in result
        assert mock_context.state["last_time_city"] == "Tokyo"
