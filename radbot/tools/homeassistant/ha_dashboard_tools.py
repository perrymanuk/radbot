"""
Agent tools for Home Assistant dashboard (Lovelace) management.

All tools are async and return ``{"status": "success", ...}`` or
``{"status": "error", "message": ...}`` per project convention.
"""

import json
import logging
import traceback
from typing import Any, Dict, Optional

from google.adk.tools import FunctionTool

from .ha_ws_singleton import get_ha_ws_client

logger = logging.getLogger(__name__)


async def _client_or_error():
    """Return (client, None) or (None, error_dict)."""
    client = await get_ha_ws_client()
    if client is None:
        return None, {
            "status": "error",
            "message": (
                "Home Assistant WebSocket client is not configured. "
                "Ensure Home Assistant URL and token are set in the admin UI "
                "or via HA_URL/HA_TOKEN environment variables."
            ),
        }
    return client, None


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


async def list_ha_dashboards() -> Dict[str, Any]:
    """List all Lovelace dashboards in Home Assistant.

    Returns:
        On success: {"status": "success", "dashboards": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = await _client_or_error()
    if err:
        return err
    try:
        dashboards = await client.list_dashboards()
        return {"status": "success", "dashboards": dashboards}
    except Exception as e:
        msg = f"Failed to list dashboards: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


async def get_ha_dashboard_config(url_path: str = "") -> Dict[str, Any]:
    """Get the full configuration (views and cards) for a dashboard.

    Args:
        url_path: The URL path of the dashboard. Empty string for the default
                  overview dashboard.

    Returns:
        On success: {"status": "success", "url_path": "...", "config": {...}}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = await _client_or_error()
    if err:
        return err
    try:
        config = await client.get_dashboard_config(url_path)
        return {
            "status": "success",
            "url_path": url_path or "(default)",
            "config": config,
        }
    except Exception as e:
        msg = f"Failed to get dashboard config for '{url_path or 'default'}': {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


async def create_ha_dashboard(
    url_path: str,
    title: str,
    icon: Optional[str] = None,
    require_admin: bool = False,
    show_in_sidebar: bool = True,
) -> Dict[str, Any]:
    """Create a new Lovelace dashboard.

    Args:
        url_path: URL slug for the dashboard (e.g. "energy-monitor").
                  Must contain a hyphen.
        title: Display title for the dashboard.
        icon: Optional MDI icon (e.g. "mdi:view-dashboard").
        require_admin: If True, only admins can view this dashboard.
        show_in_sidebar: If True, show in the HA sidebar.

    Returns:
        On success: {"status": "success", "dashboard": {...}}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = await _client_or_error()
    if err:
        return err
    try:
        result = await client.create_dashboard(
            url_path=url_path,
            title=title,
            icon=icon,
            require_admin=require_admin,
            show_in_sidebar=show_in_sidebar,
        )
        logger.info(f"Created HA dashboard: {title} ({url_path})")
        return {"status": "success", "dashboard": result}
    except Exception as e:
        msg = f"Failed to create dashboard '{url_path}': {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


async def update_ha_dashboard(
    dashboard_id: int,
    title: Optional[str] = None,
    icon: Optional[str] = None,
    require_admin: Optional[bool] = None,
    show_in_sidebar: Optional[bool] = None,
) -> Dict[str, Any]:
    """Update metadata for an existing dashboard.

    Args:
        dashboard_id: The numeric ID of the dashboard (from list_ha_dashboards).
        title: New title (optional).
        icon: New icon (optional, e.g. "mdi:home").
        require_admin: Whether admin-only (optional).
        show_in_sidebar: Whether to show in sidebar (optional).

    Returns:
        On success: {"status": "success", "dashboard": {...}}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = await _client_or_error()
    if err:
        return err

    kwargs: Dict[str, Any] = {}
    if title is not None:
        kwargs["title"] = title
    if icon is not None:
        kwargs["icon"] = icon
    if require_admin is not None:
        kwargs["require_admin"] = require_admin
    if show_in_sidebar is not None:
        kwargs["show_in_sidebar"] = show_in_sidebar

    if not kwargs:
        return {"status": "error", "message": "No fields to update were provided."}

    try:
        result = await client.update_dashboard(dashboard_id, **kwargs)
        logger.info(f"Updated HA dashboard id={dashboard_id}")
        return {"status": "success", "dashboard": result}
    except Exception as e:
        msg = f"Failed to update dashboard id={dashboard_id}: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


async def delete_ha_dashboard(dashboard_id: int) -> Dict[str, Any]:
    """Delete a dashboard by its numeric ID.

    Args:
        dashboard_id: The numeric ID of the dashboard (from list_ha_dashboards).

    Returns:
        On success: {"status": "success", "deleted_id": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = await _client_or_error()
    if err:
        return err
    try:
        await client.delete_dashboard(dashboard_id)
        logger.info(f"Deleted HA dashboard id={dashboard_id}")
        return {"status": "success", "deleted_id": dashboard_id}
    except Exception as e:
        msg = f"Failed to delete dashboard id={dashboard_id}: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


async def save_ha_dashboard_config(
    config: str,
    url_path: str = "",
) -> Dict[str, Any]:
    """Save a full Lovelace configuration (views and cards) for a dashboard.

    Args:
        config: The dashboard configuration as a JSON string. Must contain a
                "views" array at the top level.
        url_path: The URL path of the dashboard. Empty string for the default
                  overview dashboard.

    Returns:
        On success: {"status": "success", "url_path": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = await _client_or_error()
    if err:
        return err

    try:
        config_dict = json.loads(config)
    except (json.JSONDecodeError, TypeError) as e:
        return {"status": "error", "message": f"Invalid JSON config: {e}"}

    if not isinstance(config_dict, dict):
        return {"status": "error", "message": "Config must be a JSON object."}

    try:
        await client.save_dashboard_config(config_dict, url_path)
        logger.info(f"Saved dashboard config for '{url_path or 'default'}'")
        return {"status": "success", "url_path": url_path or "(default)"}
    except Exception as e:
        msg = f"Failed to save dashboard config for '{url_path or 'default'}': {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


# ---------------------------------------------------------------------------
# Wrap as ADK FunctionTools
# ---------------------------------------------------------------------------

list_ha_dashboards_tool = FunctionTool(list_ha_dashboards)
get_ha_dashboard_config_tool = FunctionTool(get_ha_dashboard_config)
create_ha_dashboard_tool = FunctionTool(create_ha_dashboard)
update_ha_dashboard_tool = FunctionTool(update_ha_dashboard)
delete_ha_dashboard_tool = FunctionTool(delete_ha_dashboard)
save_ha_dashboard_config_tool = FunctionTool(save_ha_dashboard_config)

HA_DASHBOARD_TOOLS = [
    list_ha_dashboards_tool,
    get_ha_dashboard_config_tool,
    create_ha_dashboard_tool,
    update_ha_dashboard_tool,
    delete_ha_dashboard_tool,
    save_ha_dashboard_config_tool,
]
