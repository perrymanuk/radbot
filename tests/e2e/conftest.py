"""
Core fixtures for RadBot e2e tests.

E2e tests always run against an external Docker compose stack via RADBOT_TEST_URL.
The stack must be running before tests start (use `make test-e2e` to automate this).
"""

import os
import uuid

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

# External server URL — required for all e2e tests
RADBOT_TEST_URL = os.environ.get("RADBOT_TEST_URL", "")


def pytest_configure(config):
    """Fail early if RADBOT_TEST_URL is not set."""
    if not os.environ.get("RADBOT_TEST_URL"):
        raise pytest.UsageError(
            "RADBOT_TEST_URL is required for e2e tests. "
            "Use `make test-e2e` to start the Docker stack and run tests, "
            "or set RADBOT_TEST_URL manually for a running instance."
        )


# ---------------------------------------------------------------------------
# httpx client (real HTTP transport against external server)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    """Async httpx client targeting the Docker stack."""
    async with httpx.AsyncClient(
        base_url=RADBOT_TEST_URL,
        timeout=30.0,
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Live server URL (needed for WebSocket tests)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def live_server():
    """Return the base URL for WebSocket connections."""
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
