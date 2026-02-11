"""
Lazy-initialized singleton Jira Cloud client.

Reads credentials from DB config ``integrations.jira`` first, then falls
back to the credential store (``jira_api_token``).

Returns None when unconfigured so tools can handle gracefully.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_jira_client = None
_jira_email: Optional[str] = None
_initialized = False


def _get_config() -> dict:
    """Pull Jira settings from DB config, falling back to credential store."""
    try:
        from radbot.config.config_loader import config_loader

        jira_cfg = config_loader.get_integrations_config().get("jira", {})
    except Exception:
        jira_cfg = {}

    url = jira_cfg.get("url")
    email = jira_cfg.get("email")
    api_token = jira_cfg.get("api_token")
    enabled = jira_cfg.get("enabled", True)

    # Try credential store for API token if not found in config
    if not api_token:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                api_token = store.get("jira_api_token")
                if api_token:
                    logger.info("Jira: Using API token from credential store")
        except Exception as e:
            logger.debug(f"Jira credential store lookup failed: {e}")

    return {
        "url": url,
        "email": email,
        "api_token": api_token,
        "enabled": enabled,
    }


def get_jira_client():
    """Return the singleton Jira client, or None if unconfigured."""
    global _jira_client, _jira_email, _initialized

    if _initialized:
        return _jira_client

    _initialized = True

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("Jira integration is disabled in config")
        return None

    url = cfg["url"]
    email = cfg["email"]
    api_token = cfg["api_token"]

    if not all([url, email, api_token]):
        logger.info(
            "Jira integration not configured — set integrations.jira in "
            "the Admin UI"
        )
        return None

    try:
        from atlassian import Jira

        client = Jira(url=url, username=email, password=api_token, cloud=True)
        # Verify connectivity
        myself = client.myself()
        logger.info(
            "Connected to Jira Cloud as %s (%s)",
            myself.get("displayName", "unknown"),
            myself.get("emailAddress", email),
        )
        _jira_client = client
        _jira_email = email
        return _jira_client
    except Exception as e:
        logger.error("Failed to initialise Jira client: %s", e)
        return None


def get_jira_email() -> Optional[str]:
    """Return the configured Jira email address."""
    global _jira_email
    if _jira_email is None:
        cfg = _get_config()
        _jira_email = cfg.get("email")
    return _jira_email
