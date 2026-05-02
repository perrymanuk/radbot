"""Unit tests for worker package components."""

from unittest.mock import MagicMock

import pytest


class TestSessionManagerMode:
    """Tests for SessionManager (always local for chat sessions)."""

    @pytest.mark.asyncio
    async def test_set_and_get_runner(self):
        from radbot.web.api.session.session_manager import SessionManager

        mgr = SessionManager()
        mock_runner = MagicMock()
        await mgr.set_runner("session-1", mock_runner)

        result = await mgr.get_runner("session-1")
        assert result is mock_runner

    @pytest.mark.asyncio
    async def test_get_nonexistent_runner(self):
        from radbot.web.api.session.session_manager import SessionManager

        mgr = SessionManager()
        result = await mgr.get_runner("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_session(self):
        from radbot.web.api.session.session_manager import SessionManager

        mgr = SessionManager()
        mock_runner = MagicMock()
        await mgr.set_runner("session-1", mock_runner)
        await mgr.remove_session("session-1")

        result = await mgr.get_runner("session-1")
        assert result is None
