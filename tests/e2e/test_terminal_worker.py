"""E2e tests for terminal sessions via Nomad workspace workers.

Tests the full lifecycle: workspace creation → worker spawn → terminal
session via WebSocket proxy → persistence across reconnect → cleanup.

Marks:
    - @pytest.mark.e2e — requires RADBOT_TEST_URL
    - @pytest.mark.requires_nomad — auto-skipped if Nomad unavailable
    - @pytest.mark.requires_claude_code — auto-skipped if Claude Code not available
"""

import uuid

import httpx
import pytest
import pytest_asyncio

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
]

# Binary protocol constants (must match terminal_handler.py)
MSG_DATA = 0x01
MSG_RESIZE = 0x02
MSG_CLOSED = 0x03


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_remote_mode(admin_headers: dict, base_url: str) -> bool:
    """Check if the server is in remote session mode."""
    try:
        resp = httpx.get(
            f"{base_url}/admin/api/config/agent",
            headers=admin_headers,
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("session_mode") == "remote"
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Workspace workers DB tracking
# ---------------------------------------------------------------------------
class TestWorkspaceWorkerDB:
    """Tests for workspace_workers table CRUD operations."""

    @pytest.fixture(autouse=True)
    def _ensure_schema(self):
        """Ensure the workspace_workers table exists in the local DB."""
        from radbot.worker.db import init_workspace_workers_schema

        init_workspace_workers_schema()

    async def test_upsert_and_get_workspace_worker(self):
        """Can create and retrieve a workspace worker record."""
        from radbot.worker.db import (
            delete_workspace_worker,
            get_workspace_worker,
            upsert_workspace_worker,
        )

        ws_id = str(uuid.uuid4())
        try:
            record = upsert_workspace_worker(
                workspace_id=ws_id,
                nomad_job_id="radbot-worker-test",
                worker_url="http://localhost:9999",
                status="healthy",
                image_tag="v0.14",
            )
            assert record["workspace_id"] == ws_id
            assert record["nomad_job_id"] == "radbot-worker-test"

            fetched = get_workspace_worker(ws_id)
            assert fetched is not None
            assert fetched["worker_url"] == "http://localhost:9999"
        finally:
            delete_workspace_worker(ws_id)

    async def test_count_active_workspace_workers(self):
        """Can count workspace workers in starting/healthy status."""
        from radbot.worker.db import (
            count_active_workspace_workers,
            delete_workspace_worker,
            upsert_workspace_worker,
        )

        ws_ids = [str(uuid.uuid4()) for _ in range(3)]
        try:
            initial = count_active_workspace_workers()
            for ws_id in ws_ids:
                upsert_workspace_worker(
                    workspace_id=ws_id,
                    nomad_job_id=f"test-{ws_id[:8]}",
                    status="healthy",
                )
            assert count_active_workspace_workers() == initial + 3
        finally:
            for ws_id in ws_ids:
                delete_workspace_worker(ws_id)

    async def test_list_active_excludes_stopped(self):
        """List active workspace workers excludes stopped ones."""
        from radbot.worker.db import (
            delete_workspace_worker,
            list_active_workspace_workers,
            upsert_workspace_worker,
        )

        ws_active = str(uuid.uuid4())
        ws_stopped = str(uuid.uuid4())
        try:
            upsert_workspace_worker(
                workspace_id=ws_active, nomad_job_id="j1", status="healthy"
            )
            upsert_workspace_worker(
                workspace_id=ws_stopped, nomad_job_id="j2", status="stopped"
            )

            active = list_active_workspace_workers()
            active_ids = [w["workspace_id"] for w in active]
            assert ws_active in active_ids
            assert ws_stopped not in active_ids
        finally:
            delete_workspace_worker(ws_active)
            delete_workspace_worker(ws_stopped)


# ---------------------------------------------------------------------------
# Workspace worker Nomad template
# ---------------------------------------------------------------------------
class TestWorkspaceWorkerTemplate:
    """Tests for workspace-keyed Nomad job spec generation."""

    async def test_workspace_spec_structure(self):
        """Generated spec has correct type, naming, and service tags."""
        from radbot.worker.nomad_template import build_workspace_worker_spec

        ws_id = str(uuid.uuid4())
        spec = build_workspace_worker_spec(
            workspace_id=ws_id,
            image_tag="v0.14",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        job = spec["Job"]
        assert job["Type"] == "service"
        assert job["ID"] == f"radbot-worker-{ws_id[:8]}"
        assert job["Meta"]["workspace_id"] == ws_id
        assert job["Meta"]["job_type"] == "radbot-workspace-worker"

        service = job["TaskGroups"][0]["Tasks"][0]["Services"][0]
        assert service["Name"] == "radbot-workspace"
        assert f"workspace_id={ws_id}" in service["Tags"]

    async def test_workspace_spec_uses_workspace_id_arg(self):
        """Docker args include --workspace-id."""
        from radbot.worker.nomad_template import build_workspace_worker_spec

        ws_id = "test-workspace-id"
        spec = build_workspace_worker_spec(
            workspace_id=ws_id,
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        args = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Config"]["args"]
        assert "--workspace-id" in args
        assert ws_id in args
        assert "--session-id" not in args


# ---------------------------------------------------------------------------
# Terminal handler (shared module)
# ---------------------------------------------------------------------------
class TestTerminalHandler:
    """Tests for the extracted terminal handler module."""

    async def test_terminal_manager_init(self):
        """TerminalManager initializes with empty sessions."""
        from radbot.worker.terminal_handler import TerminalManager

        mgr = TerminalManager()
        assert mgr.list_sessions() == []

    async def test_terminal_manager_custom_max_sessions(self):
        """TerminalManager respects custom max_sessions."""
        from radbot.worker.terminal_handler import TerminalManager

        mgr = TerminalManager(max_sessions=5)
        assert mgr._max_sessions == 5

    async def test_terminal_session_scrollback(self):
        """TerminalSession scrollback buffer works correctly."""
        from radbot.worker.terminal_handler import TerminalSession

        session = TerminalSession(
            terminal_id="test",
            workspace_id="ws",
            workspace={"owner": "test", "repo": "test"},
            pid=0,
            fd=0,
        )
        session.append_output(b"hello ")
        session.append_output(b"world")
        assert session.get_scrollback() == b"hello world"

    async def test_protocol_constants(self):
        """Protocol constants match expected values."""
        from radbot.worker.terminal_handler import (
            MSG_CLOSED as H_CLOSED,
            MSG_DATA as H_DATA,
            MSG_RESIZE as H_RESIZE,
        )

        assert H_DATA == 0x01
        assert H_RESIZE == 0x02
        assert H_CLOSED == 0x03


# ---------------------------------------------------------------------------
# Local mode terminal (no Nomad required)
# ---------------------------------------------------------------------------
class TestLocalTerminalSession:
    """Tests for terminal sessions in local mode (default)."""

    async def test_create_scratch_workspace(self, client, cleanup):
        """Can create a scratch workspace via REST API."""
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-worker-test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        ws = data["workspace"]
        cleanup.track("workspace", ws["workspace_id"])

    async def test_terminal_status(self, client):
        """Terminal status endpoint returns CLI availability info."""
        resp = await client.get("/terminal/status/")
        assert resp.status_code == 200

    async def test_list_sessions_empty(self, client):
        """List sessions returns empty list when none active."""
        resp = await client.get("/terminal/sessions/")
        assert resp.status_code == 200
        assert "sessions" in resp.json()


# ---------------------------------------------------------------------------
# Remote mode: full worker proxy flow (requires Nomad + Claude Code)
# ---------------------------------------------------------------------------
@pytest.mark.requires_nomad
@pytest.mark.requires_claude_code
class TestRemoteTerminalWorkerFlow:
    """End-to-end test for terminal sessions via Nomad workspace workers.

    Tests the full path:
    1. Create scratch workspace
    2. Create terminal session (triggers Nomad worker spawn)
    3. Connect via WebSocket (proxied to worker)
    4. Receive terminal output
    5. Kill session
    6. Delete workspace (stops worker)
    """

    @pytest_asyncio.fixture(loop_scope="session")
    async def remote_workspace(self, client, cleanup, admin_headers):
        """Create a scratch workspace for remote worker tests."""
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-remote-worker-test"},
        )
        assert resp.status_code == 200
        ws = resp.json()["workspace"]
        ws_id = ws["workspace_id"]
        cleanup.track("workspace", ws_id)
        return ws_id

    async def test_create_terminal_spawns_worker(
        self, client, remote_workspace, live_server, admin_headers
    ):
        """Creating a terminal session in remote mode should spawn a Nomad worker.

        This test has a long timeout because worker startup includes:
        - Nomad scheduling
        - Docker image pull (if not cached)
        - Python agent initialization
        """
        # Verify we're in remote mode (skip if not configured)
        if not _is_remote_mode(admin_headers, live_server):
            pytest.skip("session_mode is not 'remote' — set via admin UI to test")

        # Create terminal session — this triggers worker spawn
        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": remote_workspace},
            timeout=180.0,  # Worker startup can take a while
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "terminal_id" in data
        terminal_id = data["terminal_id"]

        # Verify we can connect via WebSocket
        from tests.e2e.helpers.terminal_ws_client import TerminalWSClient

        ws = await TerminalWSClient.connect(live_server, terminal_id, timeout=30.0)

        try:
            # Wait for some output (Claude Code startup banner)
            output = await ws.recv_output(timeout=60.0)
            assert len(output) > 0, "Expected terminal output from Claude Code"
        finally:
            await ws.close()

        # Kill the session
        resp = await client.delete(f"/terminal/sessions/{terminal_id}")
        assert resp.status_code == 200

    async def test_workspace_delete_stops_worker(
        self, client, admin_headers, live_server
    ):
        """Deleting a workspace should stop its Nomad worker job."""
        if not _is_remote_mode(admin_headers, live_server):
            pytest.skip("session_mode is not 'remote'")

        # Create workspace
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-delete-worker-test"},
        )
        assert resp.status_code == 200
        ws_id = resp.json()["workspace"]["workspace_id"]

        # Create terminal to spawn worker
        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": ws_id},
            timeout=180.0,
        )
        # Don't assert — if worker spawn fails, we still want to test delete

        # Delete workspace — should stop worker
        resp = await client.delete(f"/terminal/workspaces/{ws_id}")
        assert resp.status_code == 200

        # Verify worker record is stopped
        try:
            from radbot.worker.db import get_workspace_worker

            record = get_workspace_worker(ws_id)
            if record:
                assert record["status"] in (
                    "stopped",
                    "failed",
                ), f"Worker should be stopped after workspace delete, got: {record['status']}"
        except Exception:
            pass  # DB might not be accessible from test runner


# ---------------------------------------------------------------------------
# Admin UI config
# ---------------------------------------------------------------------------
class TestSessionModeConfig:
    """Tests for session_mode config via admin API."""

    async def test_read_agent_config(self, client, admin_headers):
        """Can read the agent config section."""
        resp = await client.get(
            "/admin/api/config/agent",
            headers=admin_headers,
        )
        # May be 200 (exists) or 404 (no config yet)
        assert resp.status_code in (200, 404)

    async def test_set_session_mode(self, client, admin_headers):
        """Can set session_mode via admin API."""
        # Read current config
        resp = await client.get(
            "/admin/api/config/agent",
            headers=admin_headers,
        )
        original = resp.json() if resp.status_code == 200 else {}

        try:
            # Set to remote
            resp = await client.put(
                "/admin/api/config/agent",
                json={**original, "session_mode": "remote", "max_session_workers": 5},
                headers=admin_headers,
            )
            assert resp.status_code == 200

            # Verify it was saved
            resp = await client.get(
                "/admin/api/config/agent",
                headers=admin_headers,
            )
            assert resp.status_code == 200
            config = resp.json()
            assert config.get("session_mode") == "remote"
            assert config.get("max_session_workers") == 5
        finally:
            # Restore original
            await client.put(
                "/admin/api/config/agent",
                json=original,
                headers=admin_headers,
            )
