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

    async def test_health_ready_components(self, client):
        """GET /health/ready should return component health details."""
        resp = await client.get("/health/ready")
        # May return 200 or 503 depending on component health
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "components" in data
        assert isinstance(data["components"], dict)

    async def test_healthz_alias(self, client):
        """GET /healthz should work as a liveness probe alias."""
        resp = await client.get("/healthz")
        assert resp.status_code == 200
