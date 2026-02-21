"""
Core fixtures for RadBot e2e tests.

Sets RADBOT_ENV=dev before any radbot imports, creates the ASGI test client
and a live uvicorn server for WebSocket tests.

When RADBOT_TEST_URL is set (e.g. http://localhost:8000), fixtures target
the external server (docker compose stack) instead of running in-process.
"""

import asyncio
import os
import uuid

# Set dev environment BEFORE any radbot imports
os.environ.setdefault("RADBOT_ENV", "dev")

import httpx
import pytest
import pytest_asyncio

from tests.e2e.helpers.service_checks import (
    is_calendar_available,
    is_gemini_available,
    is_gmail_available,
    is_ha_reachable,
    is_jira_reachable,
    is_overseerr_reachable,
    is_picnic_available,
    is_stt_available,
    is_tts_available,
)

# External server URL — when set, tests hit this instead of an in-process app
RADBOT_TEST_URL = os.environ.get("RADBOT_TEST_URL", "")


# ---------------------------------------------------------------------------
# App fixture (session-scoped — expensive startup, shared across all tests)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def app():
    """Import the FastAPI app and run startup/shutdown handlers.

    When RADBOT_TEST_URL is set, yields None (no in-process app needed).
    """
    if RADBOT_TEST_URL:
        yield None
        return

    from radbot.web.app import app as _app

    # Fire startup handlers
    for handler in _app.router.on_startup:
        await handler()

    yield _app

    # Fire shutdown handlers
    for handler in _app.router.on_shutdown:
        await handler()


# ---------------------------------------------------------------------------
# httpx client (ASGI transport in-process, or real HTTP to external server)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(app):
    """Async httpx client.

    In-process mode: uses ASGI transport (no actual server required).
    Docker mode: uses real HTTP transport against RADBOT_TEST_URL.
    """
    if RADBOT_TEST_URL:
        async with httpx.AsyncClient(
            base_url=RADBOT_TEST_URL,
            timeout=30.0,
        ) as c:
            yield c
    else:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            timeout=30.0,
        ) as c:
            yield c


# ---------------------------------------------------------------------------
# Live server URL (needed for WebSocket tests)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def live_server(app):
    """Yield a base URL for WebSocket connections.

    In-process mode: starts uvicorn on a random port.
    Docker mode: yields RADBOT_TEST_URL directly.
    """
    if RADBOT_TEST_URL:
        yield RADBOT_TEST_URL
        return

    import uvicorn

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,  # random port
        log_level="warning",
    )
    server = uvicorn.Server(config)

    # Start server in a background task
    serve_task = asyncio.create_task(server.serve())

    # Wait for the server to bind
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)

    # Get the actual port
    port = 8000  # fallback
    if server.servers:
        sockets = server.servers[0].sockets
        if sockets:
            port = sockets[0].getsockname()[1]

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    # Shutdown
    server.should_exit = True
    try:
        await asyncio.wait_for(serve_task, timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass


# ---------------------------------------------------------------------------
# Admin auth header
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def admin_token():
    """Return the admin bearer token from config or env."""
    token = os.environ.get("RADBOT_ADMIN_TOKEN", "")
    if not token:
        try:
            from radbot.config.config_loader import config_loader

            token = config_loader.get_config().get("admin_token", "")
        except Exception:
            pass
    return token


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    """Authorization headers for admin endpoints."""
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Test isolation helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def test_prefix():
    """Unique prefix for test data to avoid collisions."""
    return f"e2e_test_{uuid.uuid4().hex[:8]}"


class CleanupTracker:
    """Tracks created resources for cleanup in teardown."""

    def __init__(self):
        self._items: list[tuple[str, str]] = []  # (resource_type, resource_id)

    def track(self, resource_type: str, resource_id: str):
        self._items.append((resource_type, resource_id))

    @property
    def items(self):
        return list(self._items)


@pytest_asyncio.fixture(loop_scope="session")
async def cleanup(client):
    """Track and clean up test resources after each test."""
    tracker = CleanupTracker()
    yield tracker

    # Teardown: delete all tracked resources via REST API
    delete_routes = {
        "session": "/api/sessions/{id}",
        "task": "/api/tasks/{id}",
        "scheduled_task": "/api/scheduler/tasks/{id}",
        "reminder": "/api/reminders/{id}",
        "webhook": "/api/webhooks/definitions/{id}",
    }

    for resource_type, resource_id in reversed(tracker.items):
        route = delete_routes.get(resource_type)
        if route:
            url = route.format(id=resource_id)
            try:
                await client.delete(url)
            except Exception:
                pass  # best-effort cleanup


# ---------------------------------------------------------------------------
# Service availability auto-skip fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def ha_available():
    return is_ha_reachable()


@pytest.fixture(scope="session")
def calendar_available():
    return is_calendar_available()


@pytest.fixture(scope="session")
def gmail_available():
    return is_gmail_available()


@pytest.fixture(scope="session")
def jira_available():
    return is_jira_reachable()


@pytest.fixture(scope="session")
def overseerr_available():
    return is_overseerr_reachable()


@pytest.fixture(scope="session")
def picnic_available():
    return is_picnic_available()


@pytest.fixture(scope="session")
def tts_available():
    return is_tts_available()


@pytest.fixture(scope="session")
def stt_available():
    return is_stt_available()


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests based on service availability markers."""
    marker_checks = {
        "requires_gemini": is_gemini_available,
        "requires_ha": is_ha_reachable,
        "requires_calendar": is_calendar_available,
        "requires_gmail": is_gmail_available,
        "requires_jira": is_jira_reachable,
        "requires_overseerr": is_overseerr_reachable,
        "requires_picnic": is_picnic_available,
        "requires_tts": is_tts_available,
        "requires_stt": is_stt_available,
    }

    _cache = {}

    for item in items:
        for marker_name, check_fn in marker_checks.items():
            if marker_name in item.keywords:
                if marker_name not in _cache:
                    _cache[marker_name] = check_fn()
                if not _cache[marker_name]:
                    service = marker_name.replace("requires_", "").upper()
                    item.add_marker(
                        pytest.mark.skip(reason=f"{service} service not available")
                    )
