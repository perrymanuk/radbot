"""Service reachability checks for auto-skipping unavailable integration tests.

All checks query the Docker stack's admin status endpoint via RADBOT_TEST_URL.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Cached Docker admin status response
_docker_status_cache = None


def _get_docker_status() -> dict:
    """Fetch and cache the integration status from the Docker stack."""
    global _docker_status_cache
    if _docker_status_cache is not None:
        return _docker_status_cache

    test_url = os.environ.get("RADBOT_TEST_URL", "").rstrip("/")
    admin_token = os.environ.get("RADBOT_ADMIN_TOKEN", "")
    if not test_url or not admin_token:
        return {}

    try:
        import httpx

        resp = httpx.get(
            f"{test_url}/admin/api/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            _docker_status_cache = resp.json()
            return _docker_status_cache
        logger.debug(f"Docker status check returned {resp.status_code}")
    except Exception as e:
        logger.debug(f"Docker status check failed: {e}")

    return {}


def _docker_check(integration_key: str) -> bool:
    """Check if an integration is available via the Docker admin status endpoint.

    Returns True if the integration reports status "ok".
    Returns False for "unconfigured", "error", or if the key is missing.
    """
    status = _get_docker_status()
    info = status.get(integration_key, {})
    if isinstance(info, dict):
        return info.get("status") == "ok"
    return False


def is_gemini_available() -> bool:
    return _docker_check("google")


def is_ha_reachable() -> bool:
    return _docker_check("home_assistant")


def is_calendar_available() -> bool:
    return _docker_check("calendar")


def is_gmail_available() -> bool:
    return _docker_check("gmail")


def is_jira_reachable() -> bool:
    return _docker_check("jira")


def is_overseerr_reachable() -> bool:
    return _docker_check("overseerr")


def is_picnic_available() -> bool:
    return _docker_check("picnic")


def is_tts_available() -> bool:
    return _docker_check("tts")


def is_stt_available() -> bool:
    return _docker_check("stt")
