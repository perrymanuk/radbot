"""Home Assistant REST endpoints for direct-action buttons in HaDeviceCard.

Thin wrappers over :mod:`radbot.tools.homeassistant.ha_rest_client` so the
chat frontend can toggle devices inline without a full LLM roundtrip.

Endpoints:
  * ``GET  /api/ha/state/{entity_id}``   — live state + normalised card shape
  * ``POST /api/ha/service``             — call an HA service (toggle/turn on/off/…)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from radbot.tools.homeassistant.ha_client_singleton import get_ha_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ha", tags=["home-assistant"])


_ICON_MAP = {
    "light": "light",
    "switch": "light",
    "lock": "lock",
    "camera": "camera",
    "climate": "climate",
}


def _domain(entity_id: str) -> str:
    return (entity_id or "").split(".", 1)[0]


def _infer_icon(entity_id: str) -> Optional[str]:
    d = _domain(entity_id)
    rest = entity_id.split(".", 1)[1] if "." in entity_id else ""
    if d == "cover" and "garage" in rest:
        return "garage"
    return _ICON_MAP.get(d)


def _brightness_pct(attrs: Dict[str, Any]) -> Optional[int]:
    b = attrs.get("brightness")
    if b is None:
        return None
    try:
        return round(int(b) * 100 / 255)
    except (ValueError, TypeError):
        return None


def _state_to_card_state(state: str) -> str:
    s = (state or "").lower()
    if s in ("on", "off", "open", "closed", "unavailable"):
        return s
    # covers, garage_doors
    if s in ("opening", "closing"):
        return "open" if s == "opening" else "closed"
    # locks
    if s == "locked":
        return "off"
    if s == "unlocked":
        return "on"
    return s or "unavailable"


def _to_card(state_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Translate an HA state object into HaDevice card shape."""
    entity_id = state_obj.get("entity_id", "")
    attrs = state_obj.get("attributes") or {}
    friendly = attrs.get("friendly_name") or entity_id
    area = attrs.get("area_id") or attrs.get("area") or ""
    card: Dict[str, Any] = {
        "id": entity_id,
        "name": friendly,
        "area": area or "—",
        "state": _state_to_card_state(state_obj.get("state", "")),
    }
    icon = _infer_icon(entity_id)
    if icon:
        card["icon"] = icon
    bright = _brightness_pct(attrs)
    if bright is not None:
        card["brightness_pct"] = bright
    # Climate: current temperature / target
    if _domain(entity_id) == "climate":
        t = attrs.get("current_temperature")
        if t is not None:
            card["detail"] = f"{t}°"
    return card


@router.get("/state/{entity_id}")
async def get_entity_state(entity_id: str = Path(...)) -> Dict[str, Any]:
    client = get_ha_client()
    if client is None:
        raise HTTPException(503, "Home Assistant not configured — set it up via /admin/")
    state = client.get_state(entity_id)
    if state is None:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return _to_card(state)


class ServiceCallBody(BaseModel):
    domain: str
    service: str
    entity_id: Union[str, List[str]]
    data: Optional[Dict[str, Any]] = None


@router.post("/service")
async def call_service(body: ServiceCallBody) -> Dict[str, Any]:
    """Call an HA service (e.g. domain='light', service='toggle')."""
    client = get_ha_client()
    if client is None:
        raise HTTPException(503, "Home Assistant not configured — set it up via /admin/")
    try:
        result = client.call_service(
            body.domain, body.service, body.entity_id, body.data or None
        )
    except Exception as e:
        logger.error("HA service call failed: %s", e)
        raise HTTPException(502, f"HA service call failed: {e}")

    # Fetch the fresh single-entity state so the UI can reconcile.
    updated_card: Optional[Dict[str, Any]] = None
    if isinstance(body.entity_id, str):
        try:
            state = client.get_state(body.entity_id)
            if state is not None:
                updated_card = _to_card(state)
        except Exception:
            pass

    return {
        "status": "success",
        "changed": len(result) if isinstance(result, list) else 0,
        "entity": updated_card,
    }


def register_ha_router(app):
    app.include_router(router)
    logger.debug("HA router registered")
