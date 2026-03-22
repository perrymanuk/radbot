"""Overseerr integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Overseerr is unreachable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import PERSONALITY_NOT_FOUND, assert_response_contains_any, assert_response_not_empty
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_overseerr,
    pytest.mark.timeout(120),
]


class TestOverseerrIntegration:
    async def test_search_media(self, live_server):
        """Search for a well-known movie on Overseerr."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for The Matrix on Overseerr"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(result, "matrix", "movie", "film", "media", "result")
        finally:
            await ws.close()

    async def test_search_tv_show(self, live_server):
        """Search for a TV show specifically."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for Breaking Bad on Overseerr"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(result, "breaking bad", "tv", "show", "series", "result")
        finally:
            await ws.close()

    async def test_get_media_details(self, live_server):
        """Ask for detailed information about a specific movie."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Tell me about the movie The Matrix on Overseerr. "
                "Include details like genre, year, and rating."
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "matrix", "genre", "sci-fi", "science fiction",
                "1999", "action", "rating", "tmdb",
            )
        finally:
            await ws.close()

    async def test_list_media_requests(self, live_server):
        """List existing Overseerr media requests."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Show me my current Overseerr media requests"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "request", "media", "movie", "tv", "no request",
                "pending", "approved", "available", "none",
            )
        finally:
            await ws.close()

    async def test_search_nonexistent_media(self, live_server):
        """Search for nonexistent media — should handle gracefully."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for xyznonexistent98765abc on Overseerr"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "no result", "not found", "couldn't find", "no match",
                "nothing", "0 result", "zero", *PERSONALITY_NOT_FOUND,
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_request_tv_show_flow(self, live_server):
        """Full flow: search for a TV show and request it for download."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "I want to add a TV show to be downloaded. "
                "Search for Severance on Overseerr and request it."
            )
            text = assert_response_not_empty(result)
            # Should mention the show and indicate a request was made
            assert_response_contains_any(
                result, "severance", "request", "submitted", "already",
                "available", "approved", "added",
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_request_movie_flow(self, live_server):
        """Full flow: search for a movie and request it for download."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for the movie Inception on Overseerr and request it for download"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "inception", "request", "submitted", "already",
                "available", "approved", "added", "movie",
            )
        finally:
            await ws.close()
