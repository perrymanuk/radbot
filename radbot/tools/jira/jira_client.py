"""
Lazy-initialized singleton Jira Cloud client.

Reads credentials from config.yaml ``integrations.jira`` first, then falls
back to JIRA_URL / JIRA_EMAIL / JIRA_API_TOKEN environment variables.

Returns None when unconfigured so tools can handle gracefully.
"""

import logging
from typing import Optional

from radbot.tools.shared.config_helper import get_integration_config

logger = logging.getLogger(__name__)

_jira_client = None
_jira_email: Optional[str] = None
_initialized = False


def _get_config() -> dict:
    """Pull Jira settings from config manager, falling back to credential store then env vars."""
    return get_integration_config(
        "jira",
        fields={
            "url": "JIRA_URL",
            "email": "JIRA_EMAIL",
            "api_token": "JIRA_API_TOKEN",
        },
        credential_keys={"api_token": "jira_api_token"},
    )


def get_jira_client():
    """Return the singleton Jira client, or None if unconfigured."""
    global _jira_client, _jira_email, _initialized

    if _initialized:
        return _jira_client

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("Jira integration is disabled in config")
        _initialized = True
        return None

    url = cfg["url"]
    email = cfg["email"]
    api_token = cfg["api_token"]

    if not all([url, email, api_token]):
        logger.info(
            "Jira integration not configured — set integrations.jira in "
            "config.yaml or JIRA_URL/JIRA_EMAIL/JIRA_API_TOKEN env vars"
        )
        _initialized = True
        return None

    try:
        from atlassian import Jira

        client = Jira(url=url, username=email, password=api_token, cloud=True, timeout=15)
        # Verify connectivity
        myself = client.myself()
        logger.info(
            "Connected to Jira Cloud as %s (%s)",
            myself.get("displayName", "unknown"),
            myself.get("emailAddress", email),
        )
        _jira_client = client
        _jira_email = email
        _initialized = True
        return _jira_client
    except Exception as e:
        logger.error("Failed to initialise Jira client: %s", e)
        return None


def reset_jira_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _jira_client, _jira_email, _initialized
    if _jira_client is not None:
        try:
            _jira_client.close()
        except Exception:
            pass
    _jira_client = None
    _jira_email = None
    _initialized = False
    logger.info("Jira client singleton reset")


def get_jira_email() -> Optional[str]:
    """Return the configured Jira email address."""
    global _jira_email
    if _jira_email is None:
        cfg = _get_config()
        _jira_email = cfg.get("email")
    return _jira_email
