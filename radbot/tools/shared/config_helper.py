"""Shared integration configuration helper.

Eliminates the duplicated ``_get_config()`` pattern found across all
integration client modules.  Each integration can call
``get_integration_config()`` with its name, field map, and optional
credential-store keys to get a dict of resolved values.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_integration_config(
    integration_name: str,
    fields: Dict[str, str],
    credential_keys: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Load integration config from config_loader, env vars, and credential store.

    Args:
        integration_name: Name of the integration (e.g., "overseerr", "lidarr").
        fields: Mapping of field_name -> ENV_VAR_NAME for each config field.
                e.g., {"url": "OVERSEERR_URL", "api_key": "OVERSEERR_API_KEY"}
        credential_keys: Optional mapping of field_name -> credential_store_key
                for fields that should fall back to the encrypted credential store.
                e.g., {"api_key": "overseerr_api_key"}

    Returns:
        Dict with all field values (may be ``None`` if not configured).
        Always includes an ``enabled`` key (defaults to ``True``).
    """
    result: Dict[str, Any] = {}

    # 1. Try config_loader (merged file + DB config)
    cfg: Dict[str, Any] = {}
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get(integration_name, {})
    except Exception:
        logger.debug(
            "Could not load config for %s from config_loader", integration_name
        )

    # 2. For each field, try config then env var
    for field_name, env_var in fields.items():
        result[field_name] = cfg.get(field_name) or os.environ.get(env_var)

    # 3. Fall back to credential store for secrets
    if credential_keys:
        for field_name, cred_key in credential_keys.items():
            if not result.get(field_name):
                try:
                    from radbot.credentials.store import get_credential_store

                    store = get_credential_store()
                    result[field_name] = store.get(cred_key)
                except Exception:
                    logger.debug(
                        "Could not load credential %s for %s",
                        cred_key,
                        integration_name,
                    )

    # Include enabled flag (default True)
    result.setdefault("enabled", cfg.get("enabled", True))

    return result
