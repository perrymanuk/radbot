"""
Core fixtures for RadBot e2e tests.

Two execution modes are supported:

**External mode** (original)
    ``RADBOT_TEST_URL`` is set to the base URL of a running Docker stack.
    Tests connect via real HTTP/WebSocket to the external process.

**In-process mode** (new — for cassette-backed deterministic testing)
    ``RADBOT_TEST_URL`` is *not* set.  The FastAPI app is started inside the
    test process via ``httpx.ASGITransport`` (HTTP) and
    ``starlette.testclient.TestClient`` (WebSocket).  The genai interceptor in
    ``tests/e2e/cassettes.py`` is activated automatically so Gemini API calls
    are replayed from JSON cassettes without any live API key.

    Backing services (PostgreSQL, Qdrant) must still be reachable — only the
    Python app moves in-process.  Set ``RADBOT_RECORD_CASSETTES=1`` to record
    new cassettes (requires live GOOGLE_API_KEY / GEMINI_API_KEY).
"""

import asyncio
import os
import uuid

import httpx
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

RADBOT_TEST_URL: str = os.environ.get("RADBOT_TEST_URL", "").rstrip("/")
INPROCESS: bool = not bool(RADBOT_TEST_URL)


def pytest_configure(config):
    """Warn (no longer hard-fail) when RADBOT_TEST_URL is absent.

    In-process mode is the fallback; tests that require external services
    will be auto-skipped via the service-availability markers below.
    """
    if not RADBOT_TEST_URL:
        config.addinivalue_line(
            "markers",
            "e2e: end-to-end tests (running in in-process mode — "
            "RADBOT_TEST_URL not set)",
        )


def pytest_addoption(parser):
    """Add custom CLI options."""
    parser.addoption(
        "--run-writes",
        action="store_true",
        default=False,
        help="Run tests that mutate external systems (writes_external marker)",
    )


# ---------------------------------------------------------------------------
# In-process ASGI app (only created when INPROCESS=True)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def genai_interceptor():
    """Thin shim: delegate to the cassettes module interceptor.

    Defined here so conftest auto-wires it before ``asgi_app``.  If
    cassettes.py is not importable (e.g. google.genai not installed) the
    fixture silently skips patching.
    """
    try:
        from tests.e2e.cassettes import patch_genai_client  # noqa: PLC0415

        with patch_genai_client():
            yield
    except ImportError:
        yield


@pytest.fixture(scope="session")
def asgi_app(genai_interceptor):
    """Return the FastAPI ASGI application for in-process testing.

    The ``genai_interceptor`` dependency ensures the genai.Client patch is
    in place before any ADK runner is created.
    """
    if not INPROCESS:
        return None
    from radbot.web.app import app  # noqa: PLC0415

    return app


# ---------------------------------------------------------------------------
# httpx client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(asgi_app):
    """Async httpx client.

    * External mode: connects to ``RADBOT_TEST_URL`` (Docker stack).
    * In-process mode: uses ``httpx.ASGITransport`` against the ASGI app.
    """
    if INPROCESS:
        transport = httpx.ASGITransport(app=asgi_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            timeout=30.0,
        ) as c:
            yield c
    else:
        async with httpx.AsyncClient(
            base_url=RADBOT_TEST_URL,
            timeout=30.0,
        ) as c:
            yield c


# ---------------------------------------------------------------------------
# Live server URL (needed for WebSocket tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_server(asgi_app):
    """Return the base URL for WebSocket connections.

    * External mode: the Docker stack URL.
    * In-process mode: ``None`` — callers must use ``asgi_app`` directly
      (via ``WSTestClient.connect_inprocess``).
    """
    if INPROCESS:
        return None
    return RADBOT_TEST_URL


# ---------------------------------------------------------------------------
# Admin auth header
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def admin_token():
    """Return the admin bearer token from env."""
    return os.environ.get("RADBOT_ADMIN_TOKEN", "")


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
async def cleanup(client, admin_headers):
    """Track and clean up test resources after each test."""
    tracker = CleanupTracker()
    yield tracker

    admin_routes = {"alert_policy"}

    delete_routes = {
        "session": "/api/sessions/{id}",
        "task": "/api/tasks/{id}",
        "scheduled_task": "/api/scheduler/tasks/{id}",
        "reminder": "/api/reminders/{id}",
        "webhook": "/api/webhooks/definitions/{id}",
        "alert_policy": "/api/alerts/policies/{id}",
        "terminal_session": "/terminal/sessions/{id}",
        "workspace": "/terminal/workspaces/{id}",
    }

    for resource_type, resource_id in reversed(tracker.items):
        route = delete_routes.get(resource_type)
        if route:
            url = route.format(id=resource_id)
            try:
                headers = admin_headers if resource_type in admin_routes else {}
                await client.delete(url, headers=headers)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Service availability auto-skip fixtures
# ---------------------------------------------------------------------------

from tests.e2e.helpers.service_checks import (  # noqa: E402
    is_calendar_available,
    is_claude_code_available,
    is_gemini_available,
    is_github_available,
    is_gmail_available,
    is_ha_reachable,
    is_jira_reachable,
    is_lidarr_reachable,
    is_nomad_available,
    is_ntfy_available,
    is_overseerr_reachable,
    is_picnic_available,
    is_stt_available,
    is_tts_available,
)


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
def lidarr_available():
    return is_lidarr_reachable()


@pytest.fixture(scope="session")
def picnic_available():
    return is_picnic_available()


@pytest.fixture(scope="session")
def tts_available():
    return is_tts_available()


@pytest.fixture(scope="session")
def stt_available():
    return is_stt_available()


@pytest.fixture(scope="session")
def nomad_available():
    return is_nomad_available()


@pytest.fixture(scope="session")
def github_available():
    return is_github_available()


@pytest.fixture(scope="session")
def ntfy_available():
    return is_ntfy_available()


@pytest.fixture(scope="session")
def claude_code_available():
    return is_claude_code_available()


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests based on service availability markers."""
    marker_checks = {
        "requires_gemini": is_gemini_available,
        "requires_ha": is_ha_reachable,
        "requires_calendar": is_calendar_available,
        "requires_gmail": is_gmail_available,
        "requires_jira": is_jira_reachable,
        "requires_overseerr": is_overseerr_reachable,
        "requires_lidarr": is_lidarr_reachable,
        "requires_picnic": is_picnic_available,
        "requires_tts": is_tts_available,
        "requires_stt": is_stt_available,
        "requires_nomad": is_nomad_available,
        "requires_github": is_github_available,
        "requires_ntfy": is_ntfy_available,
        "requires_claude_code": is_claude_code_available,
    }

    _cache: dict[str, bool] = {}

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

    # Skip writes_external tests unless --run-writes is passed
    run_writes = config.getoption("--run-writes", default=False)
    if not run_writes:
        for item in items:
            if "writes_external" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(reason="Skipped without --run-writes flag")
                )
