"""Terminal session e2e tests — PTY + WebSocket lifecycle.

These tests require the Claude Code CLI to be installed and a valid
OAuth token configured. They are auto-skipped when unavailable.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio

from tests.e2e.helpers.terminal_ws_client import TerminalWSClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.requires_claude_code,
    pytest.mark.timeout(120),
]


@pytest_asyncio.fixture(loop_scope="session")
async def terminal_session(client, live_server, cleanup):
    """Create a scratch workspace + terminal session, yield context, cleanup.

    Yields a dict with keys: workspace_id, terminal_id, ws (TerminalWSClient).
    """
    # Create scratch workspace
    resp = await client.post(
        "/terminal/workspaces/scratch/",
        json={"name": f"e2e-session-{uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 200, f"Scratch workspace creation failed: {resp.text}"
    workspace_id = resp.json()["workspace"]["workspace_id"]
    cleanup.track("workspace", workspace_id)

    # Create terminal session
    resp = await client.post(
        "/terminal/sessions/",
        json={"workspace_id": workspace_id},
    )
    assert resp.status_code == 200, f"Terminal session creation failed: {resp.text}"
    terminal_id = resp.json()["terminal_id"]
    cleanup.track("terminal_session", terminal_id)

    # Connect via WebSocket
    ws = await TerminalWSClient.connect(live_server, terminal_id, timeout=15.0)

    ctx = {
        "workspace_id": workspace_id,
        "terminal_id": terminal_id,
        "ws": ws,
    }

    yield ctx

    # Cleanup
    await ws.close()
    try:
        await client.delete(f"/terminal/sessions/{terminal_id}")
    except Exception:
        pass


class TestTerminalSessionLifecycle:
    """Tier 1: Full PTY lifecycle tests with pre-configured token."""

    async def test_full_session_lifecycle(self, client, live_server, cleanup):
        """Create workspace -> session -> connect WS -> verify output -> cleanup."""
        # 1. Create scratch workspace
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-lifecycle"},
        )
        assert resp.status_code == 200
        workspace_id = resp.json()["workspace"]["workspace_id"]
        cleanup.track("workspace", workspace_id)

        # 2. Create terminal session
        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": workspace_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        terminal_id = data["terminal_id"]
        assert data["owner"] == "_scratch"
        assert "pid" in data
        cleanup.track("terminal_session", terminal_id)

        # 3. Connect via binary WebSocket
        ws = await TerminalWSClient.connect(live_server, terminal_id, timeout=15.0)
        try:
            # 4. Wait for Claude Code to produce output (up to 30s)
            output = await ws.recv_output(timeout=30.0)
            assert len(output) > 0, "Expected PTY output from Claude Code"

            # 5. Verify no OAuth login prompt appeared (token injection worked)
            stripped = ws.get_output()
            oauth_indicators = ["login", "sign in", "/oauth/authorize"]
            for indicator in oauth_indicators:
                assert indicator not in stripped.lower(), (
                    f"OAuth prompt detected ({indicator!r}) — "
                    f"token injection or onboarding flag may have failed. "
                    f"Output: {stripped[:300]}"
                )

            # 6. Verify session appears in active list
            resp = await client.get("/terminal/sessions/")
            sessions = resp.json()["sessions"]
            our_session = [s for s in sessions if s["terminal_id"] == terminal_id]
            assert len(our_session) == 1
            assert not our_session[0]["closed"]
        finally:
            await ws.close()

        # 7. Kill session
        resp = await client.delete(f"/terminal/sessions/{terminal_id}")
        assert resp.status_code == 200

    async def test_send_input_receives_output(self, client, live_server, cleanup):
        """Sending keystrokes should produce PTY output."""
        # Setup
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-input"},
        )
        workspace_id = resp.json()["workspace"]["workspace_id"]
        cleanup.track("workspace", workspace_id)

        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": workspace_id},
        )
        terminal_id = resp.json()["terminal_id"]
        cleanup.track("terminal_session", terminal_id)

        ws = await TerminalWSClient.connect(live_server, terminal_id, timeout=15.0)
        try:
            # Wait for initial output (Claude Code startup)
            await ws.recv_output(timeout=30.0)

            # Send a newline — should produce some response
            await ws.send_input("\n")
            await ws.recv_output(timeout=15.0)
            # Any output means the PTY I/O round-trip works
            assert ws.get_output(), "No output received after sending input"
        finally:
            await ws.close()
            await client.delete(f"/terminal/sessions/{terminal_id}")

    async def test_resize_terminal(self, client, live_server, cleanup):
        """Resize messages should not crash the session."""
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-resize"},
        )
        workspace_id = resp.json()["workspace"]["workspace_id"]
        cleanup.track("workspace", workspace_id)

        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": workspace_id},
        )
        terminal_id = resp.json()["terminal_id"]
        cleanup.track("terminal_session", terminal_id)

        ws = await TerminalWSClient.connect(live_server, terminal_id, timeout=15.0)
        try:
            # Wait for initial output
            await ws.recv_output(timeout=30.0)

            # Send resize
            await ws.send_resize(132, 43)
            await asyncio.sleep(1)

            # Session should still be alive
            resp = await client.get("/terminal/sessions/")
            sessions = resp.json()["sessions"]
            our = [s for s in sessions if s["terminal_id"] == terminal_id]
            assert len(our) == 1
            assert not our[0]["closed"], "Session died after resize"
        finally:
            await ws.close()
            await client.delete(f"/terminal/sessions/{terminal_id}")

    async def test_scrollback_replay_on_reconnect(self, client, live_server, cleanup):
        """Second WS connection should receive scrollback replay."""
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-scrollback"},
        )
        workspace_id = resp.json()["workspace"]["workspace_id"]
        cleanup.track("workspace", workspace_id)

        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": workspace_id},
        )
        terminal_id = resp.json()["terminal_id"]
        cleanup.track("terminal_session", terminal_id)

        ws1 = await TerminalWSClient.connect(live_server, terminal_id, timeout=15.0)
        try:
            # Wait for initial output on ws1
            await ws1.recv_output(timeout=30.0)
            initial_output = ws1.get_output()
            assert len(initial_output) > 0, "No initial output on ws1"

            # Connect ws2 — should receive scrollback replay
            ws2 = await TerminalWSClient.connect(live_server, terminal_id, timeout=10.0)
            try:
                scrollback = await ws2.recv_output(timeout=10.0)
                assert len(scrollback) > 0, "Expected scrollback replay on ws2"
            finally:
                await ws2.close()
        finally:
            await ws1.close()
            await client.delete(f"/terminal/sessions/{terminal_id}")

    async def test_session_closed_notification(self, client, live_server, cleanup):
        """Killing a session should send MSG_CLOSED to connected clients."""
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-close-notify"},
        )
        workspace_id = resp.json()["workspace"]["workspace_id"]
        cleanup.track("workspace", workspace_id)

        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": workspace_id},
        )
        terminal_id = resp.json()["terminal_id"]
        # Don't track for cleanup — we're explicitly killing it

        ws = await TerminalWSClient.connect(live_server, terminal_id, timeout=15.0)
        try:
            # Wait for some output first
            await ws.recv_output(timeout=30.0)

            # Kill the session via API
            resp = await client.delete(f"/terminal/sessions/{terminal_id}")
            assert resp.status_code == 200

            # Client should receive close notification
            closed = await ws.wait_for_close(timeout=10.0)
            assert closed, "Did not receive MSG_CLOSED after session kill"
            assert ws.exit_code is not None
        finally:
            await ws.close()

    async def test_max_concurrent_sessions(self, client, cleanup):
        """Creating more than MAX_CONCURRENT_SESSIONS should return 429."""
        workspace_ids = []
        terminal_ids = []

        try:
            # Create 3 sessions (the max)
            for i in range(3):
                resp = await client.post(
                    "/terminal/workspaces/scratch/",
                    json={"name": f"e2e-max-{i}"},
                )
                assert resp.status_code == 200
                wid = resp.json()["workspace"]["workspace_id"]
                workspace_ids.append(wid)
                cleanup.track("workspace", wid)

                resp = await client.post(
                    "/terminal/sessions/",
                    json={"workspace_id": wid},
                )
                assert (
                    resp.status_code == 200
                ), f"Session {i} creation failed: {resp.text}"
                tid = resp.json()["terminal_id"]
                terminal_ids.append(tid)
                cleanup.track("terminal_session", tid)

            # 4th should fail with 429
            resp = await client.post(
                "/terminal/workspaces/scratch/",
                json={"name": "e2e-max-overflow"},
            )
            overflow_wid = resp.json()["workspace"]["workspace_id"]
            cleanup.track("workspace", overflow_wid)

            resp = await client.post(
                "/terminal/sessions/",
                json={"workspace_id": overflow_wid},
            )
            assert (
                resp.status_code == 429
            ), f"Expected 429 for 4th session, got {resp.status_code}: {resp.text}"
        finally:
            # Kill all sessions to avoid leaking into other tests
            for tid in terminal_ids:
                try:
                    await client.delete(f"/terminal/sessions/{tid}")
                except Exception:
                    pass
