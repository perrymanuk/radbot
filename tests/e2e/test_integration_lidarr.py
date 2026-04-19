"""Lidarr integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Lidarr is unreachable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import (
    PERSONALITY_NOT_FOUND,
    assert_response_contains_any,
    assert_response_not_empty,
)
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_lidarr,
    pytest.mark.timeout(120),
]


class TestLidarrIntegration:
    async def test_search_artist(self, live_server):
        """Search for a well-known artist on Lidarr."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Search for Metallica on Lidarr")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "metallica",
                "artist",
                "metal",
                "band",
                "result",
            )
        finally:
            await ws.close()

    async def test_search_album(self, live_server):
        """Search for a specific album on Lidarr."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for the album Abbey Road on Lidarr"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "abbey road",
                "beatles",
                "album",
                "result",
            )
        finally:
            await ws.close()

    async def test_list_quality_profiles(self, live_server):
        """List available quality profiles from Lidarr."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "What quality profiles are available on Lidarr?"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "profile",
                "quality",
                "lossless",
                "standard",
                "any",
                "flac",
                "mp3",
            )
        finally:
            await ws.close()

    async def test_search_nonexistent_artist(self, live_server):
        """Search for nonexistent artist — should handle gracefully."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for xyznonexistent98765abc on Lidarr"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "no result",
                "not found",
                "couldn't find",
                "no match",
                "nothing",
                "0 result",
                "zero",
                *PERSONALITY_NOT_FOUND,
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_add_artist_flow(self, live_server):
        """Full flow: search for an artist and add them to Lidarr."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for Radiohead on Lidarr and add them for download"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "radiohead",
                "added",
                "already",
                "monitoring",
                "library",
                "artist",
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_add_album_flow(self, live_server):
        """Full flow: search for an album and add it to Lidarr."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for the album OK Computer by Radiohead on Lidarr "
                "and add it for download"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "ok computer",
                "radiohead",
                "added",
                "already",
                "album",
                "download",
            )
        finally:
            await ws.close()
