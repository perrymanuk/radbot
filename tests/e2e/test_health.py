"""Health endpoint e2e tests."""

import time

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        """GET /health should return 200 with status ok."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_health_is_fast(self, client):
        """Health check should respond in under 500ms."""
        start = time.monotonic()
        resp = await client.get("/health")
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"Health check took {elapsed:.3f}s, expected < 0.5s"
