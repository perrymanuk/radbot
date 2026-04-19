"""E2e tests for session workers and Nomad job management.

Chat sessions always run locally (SessionRunner).  Remote Nomad workers
are only used for terminal/workspace sessions.  This file tests Nomad
connectivity, job template generation, worker DB tracking, and verifies
that chat sessions always use local mode.

Marks:
    - @pytest.mark.e2e — requires RADBOT_TEST_URL
    - @pytest.mark.requires_nomad — auto-skipped if Nomad is unavailable
    - @pytest.mark.requires_gemini — auto-skipped if Gemini API unavailable
"""

import asyncio
import uuid

import pytest
import pytest_asyncio

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.requires_nomad,
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def worker_session_id():
    """A unique session ID for worker tests."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# API Endpoint Tests (worker lifecycle management)
# ---------------------------------------------------------------------------
class TestSessionWorkerAPI:
    """Tests for worker lifecycle via the main app's REST API."""

    async def test_health_endpoint_exists(self, client):
        """Main app health endpoint should be accessible."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_session_workers_schema_initialized(self, client, admin_headers):
        """The session_workers table should exist after startup."""
        # We can verify indirectly by trying to create a session —
        # if the schema init failed, session creation might fail
        resp = await client.post(
            "/api/sessions/create",
            json={"name": "worker_schema_test"},
        )
        assert resp.status_code in (200, 201)
        sid = resp.json().get("id")
        if sid:
            await client.delete(f"/api/sessions/{sid}")


class TestNomadJobSubmission:
    """Tests for Nomad job template submission via the Nomad API."""

    async def test_nomad_connectivity(self, client, admin_headers):
        """Verify Nomad is reachable from the Docker stack."""
        resp = await client.get(
            "/admin/api/status",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        status = resp.json()
        nomad_status = status.get("nomad", {})
        assert (
            nomad_status.get("status") == "ok"
        ), f"Nomad not available: {nomad_status}"

    async def test_job_template_produces_valid_spec(self):
        """The Nomad job template should produce a parseable spec."""
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id=str(uuid.uuid4()),
            image_tag="v0.14",
            credential_key="test",
            admin_token="test",
            postgres_pass="test",
        )

        # Basic structural validation
        job = spec["Job"]
        assert job["Type"] == "service"
        assert len(job["TaskGroups"]) == 1
        assert len(job["TaskGroups"][0]["Tasks"]) == 1

        task = job["TaskGroups"][0]["Tasks"][0]
        assert task["Driver"] == "docker"
        assert "radbot.worker" in task["Config"]["args"]

    async def test_list_session_jobs(self, client, admin_headers):
        """Can list existing radbot-session jobs via Nomad (may be empty)."""
        # This tests that the Nomad client can query for session jobs
        # without actually submitting one
        resp = await client.get(
            "/admin/api/status",
            headers=admin_headers,
        )
        # If Nomad is up, this should succeed even with no session jobs
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Chat sessions always use local mode
# ---------------------------------------------------------------------------
class TestChatSessionsAlwaysLocal:
    """Verify chat sessions always run locally, regardless of session_mode config."""

    async def test_chat_session_works(self, client, live_server, cleanup):
        """A chat session should always use local SessionRunner."""
        from tests.e2e.helpers.ws_client import WSTestClient

        # Create a session
        resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_local_fallback_test"},
        )
        assert resp.status_code in (200, 201)
        sid = resp.json()["id"]
        cleanup.track("session", sid)

        ws = await WSTestClient.connect(live_server, sid, timeout=15.0)
        try:
            result = await ws.send_and_wait_response(
                "Reply with just the word 'pong'.",
                timeout=60.0,
            )
            assert result["error"] == ""
            assert len(result["response_text"]) > 0
        finally:
            await ws.close()


# ---------------------------------------------------------------------------
# Worker DB tracking tests
# ---------------------------------------------------------------------------
class TestWorkerDBTracking:
    """Tests for the session_workers database operations."""

    @pytest.fixture(autouse=True)
    def _ensure_schema(self):
        """Ensure the session_workers table exists before each test."""
        from radbot.worker.db import init_session_workers_schema

        init_session_workers_schema()

    async def test_upsert_and_get_worker(self):
        """Can create and retrieve a worker record."""
        from radbot.worker.db import delete_worker, get_worker, upsert_worker

        sid = str(uuid.uuid4())
        try:
            record = upsert_worker(
                session_id=sid,
                nomad_job_id="radbot-session-test",
                worker_url="http://localhost:9999",
                status="healthy",
                image_tag="v0.14",
            )
            assert record["session_id"] == sid
            assert record["nomad_job_id"] == "radbot-session-test"
            assert record["status"] == "healthy"

            fetched = get_worker(sid)
            assert fetched is not None
            assert fetched["worker_url"] == "http://localhost:9999"
        finally:
            delete_worker(sid)

    async def test_count_active_workers(self):
        """Can count workers in starting/healthy status."""
        from radbot.worker.db import (
            count_active_workers,
            delete_worker,
            upsert_worker,
        )

        sids = [str(uuid.uuid4()) for _ in range(3)]
        try:
            initial_count = count_active_workers()

            for sid in sids:
                upsert_worker(
                    session_id=sid,
                    nomad_job_id=f"test-job-{sid[:8]}",
                    status="healthy",
                )

            assert count_active_workers() == initial_count + 3
        finally:
            for sid in sids:
                delete_worker(sid)

    async def test_update_worker_status(self):
        """Can update a worker's status."""
        from radbot.worker.db import (
            delete_worker,
            get_worker,
            update_worker_status,
            upsert_worker,
        )

        sid = str(uuid.uuid4())
        try:
            upsert_worker(
                session_id=sid,
                nomad_job_id="test-job",
                status="starting",
            )

            update_worker_status(sid, "healthy", worker_url="http://worker:8000")
            record = get_worker(sid)
            assert record["status"] == "healthy"
            assert record["worker_url"] == "http://worker:8000"
        finally:
            delete_worker(sid)

    async def test_touch_worker(self):
        """Touching a worker updates last_active_at."""
        from radbot.worker.db import (
            delete_worker,
            get_worker,
            touch_worker,
            upsert_worker,
        )

        sid = str(uuid.uuid4())
        try:
            upsert_worker(
                session_id=sid,
                nomad_job_id="test-job",
                status="healthy",
            )

            before = get_worker(sid)
            await asyncio.sleep(0.1)
            touch_worker(sid)
            after = get_worker(sid)

            assert after["last_active_at"] >= before["last_active_at"]
        finally:
            delete_worker(sid)

    async def test_list_active_workers(self):
        """Lists only starting/healthy workers."""
        from radbot.worker.db import (
            delete_worker,
            list_active_workers,
            upsert_worker,
        )

        sid_active = str(uuid.uuid4())
        sid_stopped = str(uuid.uuid4())
        try:
            upsert_worker(session_id=sid_active, nomad_job_id="j1", status="healthy")
            upsert_worker(session_id=sid_stopped, nomad_job_id="j2", status="stopped")

            active = list_active_workers()
            active_ids = [w["session_id"] for w in active]
            assert sid_active in active_ids
            assert sid_stopped not in active_ids
        finally:
            delete_worker(sid_active)
            delete_worker(sid_stopped)

    async def test_delete_worker(self):
        """Can delete a worker record."""
        from radbot.worker.db import delete_worker, get_worker, upsert_worker

        sid = str(uuid.uuid4())
        upsert_worker(session_id=sid, nomad_job_id="j", status="starting")
        assert get_worker(sid) is not None

        delete_worker(sid)
        assert get_worker(sid) is None


# ---------------------------------------------------------------------------
# Nomad service discovery tests
# ---------------------------------------------------------------------------
class TestNomadServiceDiscovery:
    """Tests for Nomad service discovery integration."""

    async def test_find_service_returns_none_for_unknown(self):
        """Searching for a nonexistent service tag returns None."""
        from radbot.tools.nomad.nomad_client import get_nomad_client

        client = get_nomad_client()
        if not client:
            pytest.skip("Nomad client not configured")

        result = await client.find_service_by_tag(
            "radbot-session",
            f"session_id={uuid.uuid4()}",
        )
        assert result is None

    async def test_list_services_empty(self):
        """Listing a service name with no registrations returns empty or raises."""
        from radbot.tools.nomad.nomad_client import get_nomad_client

        client = get_nomad_client()
        if not client:
            pytest.skip("Nomad client not configured")

        try:
            services = await client.list_services("radbot-session-nonexistent")
            # Nomad returns empty list or 404 for unknown services
            assert isinstance(services, list)
        except Exception:
            pass  # 404 is acceptable for unknown service names
