"""Service reachability checks for auto-skipping unavailable integration tests."""

import logging
import os

logger = logging.getLogger(__name__)


def _try_import_and_check(check_fn) -> bool:
    """Run a check function, return False on any error."""
    try:
        return check_fn()
    except Exception as e:
        logger.debug(f"Service check failed: {e}")
        return False


def is_gemini_available() -> bool:
    """Check if the Google Gemini API key is configured."""
    def _check():
        # Check env var first
        if os.environ.get("GOOGLE_API_KEY"):
            return True
        # Check config file
        from radbot.config.config_loader import config_loader
        cfg = config_loader.get_config()
        api_key = cfg.get("api_keys", {}).get("google", "")
        if api_key:
            return True
        # Check credential store
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        api_key = store.get("google_api_key")
        return bool(api_key)
    return _try_import_and_check(_check)


def is_ha_reachable() -> bool:
    """Check if Home Assistant is reachable."""
    def _check():
        from radbot.config.config_loader import config_loader
        cfg = config_loader.get_integrations_config().get("home_assistant", {})
        url = cfg.get("url") or os.environ.get("HA_URL", "")
        token = cfg.get("token") or os.environ.get("HA_TOKEN", "")
        if not url or not token:
            # Try credential store
            from radbot.credentials.store import get_credential_store
            store = get_credential_store()
            if not token:
                token = store.get("ha_token") or ""
            if not url:
                url = store.get("ha_url") or ""
        if not url or not token:
            return False
        import httpx
        resp = httpx.get(
            f"{url.rstrip('/')}/api/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        return resp.status_code == 200
    return _try_import_and_check(_check)


def is_calendar_available() -> bool:
    """Check if Google Calendar credentials are available."""
    def _check():
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        creds = store.get("google_calendar_credentials")
        return bool(creds)
    return _try_import_and_check(_check)


def is_gmail_available() -> bool:
    """Check if Gmail credentials are available."""
    def _check():
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        # Gmail stores credentials per-account
        cred_list = store.list()
        return any(c.get("name", "").startswith("gmail_credentials_") for c in cred_list)
    return _try_import_and_check(_check)


def is_jira_reachable() -> bool:
    """Check if Jira is configured and reachable."""
    def _check():
        from radbot.config.config_loader import config_loader
        cfg = config_loader.get_integrations_config().get("jira", {})
        url = cfg.get("url") or os.environ.get("JIRA_URL", "")
        if not url:
            return False
        import httpx
        resp = httpx.get(f"{url.rstrip('/')}/rest/api/2/serverInfo", timeout=5.0)
        return resp.status_code in (200, 401)  # 401 means reachable but needs auth
    return _try_import_and_check(_check)


def is_overseerr_reachable() -> bool:
    """Check if Overseerr is configured and reachable."""
    def _check():
        from radbot.config.config_loader import config_loader
        cfg = config_loader.get_integrations_config().get("overseerr", {})
        url = cfg.get("url") or os.environ.get("OVERSEERR_URL", "")
        api_key = cfg.get("api_key") or os.environ.get("OVERSEERR_API_KEY", "")
        if not url:
            return False
        import httpx
        headers = {}
        if api_key:
            headers["X-Api-Key"] = api_key
        resp = httpx.get(f"{url.rstrip('/')}/api/v1/status", headers=headers, timeout=5.0)
        return resp.status_code == 200
    return _try_import_and_check(_check)


def is_picnic_available() -> bool:
    """Check if Picnic credentials are configured."""
    def _check():
        from radbot.config.config_loader import config_loader
        cfg = config_loader.get_integrations_config().get("picnic", {})
        username = cfg.get("username") or os.environ.get("PICNIC_USERNAME", "")
        password = cfg.get("password") or os.environ.get("PICNIC_PASSWORD", "")
        return bool(username and password)
    return _try_import_and_check(_check)


def is_tts_available() -> bool:
    """Check if Google Cloud TTS is available."""
    def _check():
        from google.cloud import texttospeech  # noqa: F401
        # Check if credentials are available
        client = texttospeech.TextToSpeechClient()
        # Quick test — list voices
        client.list_voices(language_code="en-US")
        return True
    return _try_import_and_check(_check)


def is_stt_available() -> bool:
    """Check if Google Cloud STT is available."""
    def _check():
        from radbot.tools.stt.stt_service import STTService
        svc = STTService.get_instance()
        return svc is not None and svc.available
    return _try_import_and_check(_check)
