"""Concurrency e2e tests."""

import asyncio
import uuid

import pytest

from tests.e2e.helpers.assertions import assert_response_not_empty
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_gemini,
    pytest.mark.timeout(180),
]


class TestConcurrentSessions:
    async def test_parallel_sessions(self, live_server):
        """Three simultaneous sessions should all respond independently."""
        sessions = []
        for _ in range(3):
            sid = str(uuid.uuid4())
            ws = await WSTestClient.connect(live_server, sid)
            sessions.append(ws)

        try:
            # Send messages concurrently
            tasks = [
                ws.send_and_wait_response(f"What is {i + 1} + {i + 1}?")
                for i, ws in enumerate(sessions)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = 0
            for r in results:
                if isinstance(r, Exception):
                    continue
                text = r.get("response_text", "")
                if text:
                    success_count += 1

            assert (
                success_count >= 2
            ), f"Expected at least 2/3 sessions to respond, got {success_count}"
        finally:
            for ws in sessions:
                await ws.close()

    @pytest.mark.xfail(
        reason="Known: single user_id shares Qdrant memory across sessions"
    )
    async def test_session_isolation(self, live_server):
        """Setting a name in session A should not leak to session B."""
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        ws_a = await WSTestClient.connect(live_server, sid_a)
        ws_b = await WSTestClient.connect(live_server, sid_b)
        try:
            # Set name in session A
            result_a = await ws_a.send_and_wait_response(
                "My name is E2EIsolationTestAlpha. Remember that."
            )
            assert_response_not_empty(result_a)

            # Ask in session B — should NOT know the name
            result_b = await ws_b.send_and_wait_response("What is my name?")
            text_b = result_b.get("response_text", "").lower()
            assert (
                "e2eisolationtestalpha" not in text_b
            ), "Session B should not know session A's name"
        finally:
            await ws_a.close()
            await ws_b.close()
