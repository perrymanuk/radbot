"""
Card-rendering protocol helpers.

Agents emit structured UI cards by returning a fenced code block with an
info string of the form ``radbot:<kind>`` containing a JSON payload.
The web frontend (``ChatMessage.tsx``) parses these blocks and renders
``MediaCard`` / ``SeasonBreakdownCard`` / ``HaDeviceCard`` / ``HandoffLine``
from ``components/chat/AgentCards.tsx``.

This module provides:

* ``format_card_block(kind, data)`` — format a dict as the fenced block.
* FunctionTool wrappers (``show_media_card``, ``show_season_breakdown``,
  ``show_ha_device_card``) so an agent can call a dedicated tool; the
  return value contains the pre-formatted block that the agent includes
  verbatim in its reply.

Shapes follow the TypeScript interfaces in ``AgentCards.tsx``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.tools.shared.tool_decorator import tool_error_handler

logger = logging.getLogger(__name__)

_VALID_KINDS = {"media", "seasons", "ha-device", "handoff", "video"}


def _lookup_poster_url(tmdb_id: int, media_type: str) -> Optional[str]:
    """Best-effort TMDB poster URL lookup via Overseerr.

    Returns None on any failure — callers should treat a missing URL as
    'use the gradient placeholder'. Kept non-fatal because this runs on
    every card emission and Overseerr might be unreachable.
    """
    if media_type not in ("movie", "tv"):
        return None
    try:
        from radbot.tools.overseerr.overseerr_client import get_overseerr_client
        from radbot.tools.overseerr.overseerr_tools import tmdb_poster_url

        client = get_overseerr_client()
        if client is None:
            return None
        raw = (
            client.get_movie(tmdb_id)
            if media_type == "movie"
            else client.get_tv(tmdb_id)
        )
        return tmdb_poster_url((raw or {}).get("posterPath"))
    except Exception as e:
        logger.debug("Poster URL lookup failed for %s/%s: %s", media_type, tmdb_id, e)
        return None


_KIDEO_STATUS_MAP = {
    "ready": "in_library",
    "available": "in_library",
    "downloaded": "in_library",
    "queued": "queued",
    "pending": "queued",
    "downloading": "processing",
    "transcoding": "processing",
    "error": "error",
    "failed": "error",
}


def _lookup_kideo_status(url: Optional[str]) -> tuple:
    """Best-effort Kideo library lookup.

    Returns ``(card_status, kideo_video_id)`` where ``card_status`` is one of
    ``"in_library" | "queued" | "processing" | "error"`` or ``None`` when the
    video is not in Kideo / lookup failed. Mirrors :func:`_lookup_poster_url`
    — never raises.
    """
    if not url:
        return None, None
    try:
        from radbot.tools.youtube.kideo_client import find_video_by_url

        match = find_video_by_url(url)
    except Exception as e:
        logger.debug("Kideo lookup failed for %s: %s", url, e)
        return None, None
    if not match:
        return None, None
    raw_status = (match.get("status") or "").lower()
    return _KIDEO_STATUS_MAP.get(raw_status, "in_library"), match.get("id")


def format_card_block(kind: str, data: Any) -> str:
    r"""Return a ```radbot:<kind>\n{json}\n``` fenced block."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown card kind: {kind!r}. Valid: {sorted(_VALID_KINDS)}")
    payload = json.dumps(data, ensure_ascii=False)
    return f"```radbot:{kind}\n{payload}\n```"


# ---------------------------------------------------------------------------
# Agent-facing tools
# ---------------------------------------------------------------------------


@tool_error_handler("render media card")
def show_media_card(
    title: str,
    kind: str,
    status: str,
    tmdb_id: Optional[int] = None,
    media_type: Optional[str] = None,
    year: Optional[int] = None,
    year_range: Optional[str] = None,
    resolution: Optional[str] = None,
    format_label: Optional[str] = None,
    content_rating: Optional[str] = None,
    season_count: Optional[int] = None,
    episode_count: Optional[int] = None,
    episode_runtime: Optional[str] = None,
    on_server_have: Optional[int] = None,
    on_server_total: Optional[int] = None,
    progress: Optional[int] = None,
    note: Optional[str] = None,
    subtitle: Optional[str] = None,
    poster_accent: Optional[str] = None,
    poster_badge: Optional[str] = None,
    poster_footer: Optional[str] = None,
    poster_title: Optional[str] = None,
    poster_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Render a media availability card inline in chat.

    Args:
        title: Movie or show title.
        kind: "movie" or "show".
        status: "available" | "partial" | "downloading" | "missing".
        tmdb_id: TMDB id — enables the REQUEST DOWNLOAD / FILL THE GAPS button.
        media_type: "movie" or "tv" — also required for the action button.
        year: Release year (movies) or first-air year.
        year_range: For TV, e.g. "2005-2008".
        resolution: Resolution label, e.g. "4K HDR".
        format_label: Format label, e.g. "1080p WEB-DL".
        content_rating: TV rating (TV-Y7, TV-14) or MPAA (PG, PG-13).
        season_count / episode_count / episode_runtime: TV metadata.
        on_server_have / on_server_total: partial availability fractions.
        progress: 0-100 download progress (when status="downloading").
        note: Italic footer line (one-sentence overview / status note).
        subtitle: Optional secondary title line.
        poster_accent: "sunset" | "violet" | "sky" | "magenta".
        poster_badge: Small top-left poster badge, e.g. "ATLA", "LIVE".
        poster_footer: Small poster footer, e.g. "RADBOT·SCOUT".
        poster_title: Large poster glyph (defaults to first char of title).

    Returns:
        ``{"status": "success", "block": "...", "instructions": "..."}``.
        Include the ``block`` string verbatim in your reply.
    """
    if kind not in ("movie", "show"):
        return {"status": "error", "message": "kind must be 'movie' or 'show'"}
    if status not in ("available", "partial", "downloading", "missing"):
        return {
            "status": "error",
            "message": "status must be 'available', 'partial', 'downloading', or 'missing'",
        }

    data: Dict[str, Any] = {"title": title, "kind": kind, "status": status}
    if tmdb_id is not None:
        data["tmdb_id"] = tmdb_id
    if media_type in ("movie", "tv"):
        data["media_type"] = media_type
    if year is not None:
        data["year"] = year
    if year_range:
        data["year_range"] = year_range
    if resolution:
        data["resolution"] = resolution
    if format_label:
        data["format"] = format_label
    if content_rating:
        data["content_rating"] = content_rating
    if season_count is not None:
        data["season_count"] = season_count
    if episode_count is not None:
        data["episode_count"] = episode_count
    if episode_runtime:
        data["episode_runtime"] = episode_runtime
    if on_server_have is not None and on_server_total:
        data["on_server"] = {"have": int(on_server_have), "total": int(on_server_total)}
    if progress is not None and status == "downloading":
        data["progress"] = max(0, min(100, progress))
    if note:
        data["note"] = note
    if subtitle:
        data["subtitle"] = subtitle
    # Auto-fill poster_url from Overseerr when Casa didn't pass one.
    resolved_url = poster_url
    if not resolved_url and tmdb_id is not None and media_type in ("movie", "tv"):
        resolved_url = _lookup_poster_url(tmdb_id, media_type)

    if poster_accent or poster_badge or poster_footer or poster_title or resolved_url:
        glyph = poster_title or (title.strip()[:1].upper() if title else "?")
        poster: Dict[str, Any] = {"title": glyph}
        if poster_accent:
            poster["accent"] = poster_accent
        if poster_badge:
            poster["badge"] = poster_badge
        if poster_footer:
            poster["footer"] = poster_footer
        if resolved_url:
            poster["url"] = resolved_url
        data["poster"] = poster

    return {
        "status": "success",
        "block": format_card_block("media", data),
        "instructions": "Include the 'block' string verbatim in your reply.",
    }


@tool_error_handler("render season breakdown card")
def show_season_breakdown(
    show: str,
    seasons: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Render a per-season episode-availability breakdown.

    Args:
        show: Show title.
        seasons: List of ``{"num": int, "have": int, "total": int,
            "missing": ["E03", "E07", ...]}``.

    Returns:
        ``{"status": "success", "block": "...", "instructions": "..."}``.
    """
    normalised: List[Dict[str, Any]] = []
    for s in seasons:
        normalised.append(
            {
                "num": int(s.get("num", 0)),
                "have": int(s.get("have", 0)),
                "total": int(s.get("total", 0)),
                "missing": list(s.get("missing", []) or []),
            }
        )
    return {
        "status": "success",
        "block": format_card_block("seasons", {"show": show, "seasons": normalised}),
        "instructions": "Include the 'block' string verbatim in your reply.",
    }


_HA_ICON_PREFIX = {
    "light": "light",
    "switch": "light",
    "lock": "lock",
    "camera": "camera",
    "climate": "climate",
}


def infer_ha_icon(entity_id: str) -> Optional[str]:
    """Map an HA entity_id to an AgentCards icon hint."""
    if not entity_id or "." not in entity_id:
        return None
    domain, _, rest = entity_id.partition(".")
    if domain == "cover" and "garage" in rest:
        return "garage"
    return _HA_ICON_PREFIX.get(domain)


@tool_error_handler("render Home Assistant device card")
def show_ha_device_card(
    entity_id: str,
    name: str,
    area: str,
    state: str,
    detail: Optional[str] = None,
    icon: Optional[str] = None,
    brightness_pct: Optional[int] = None,
) -> Dict[str, Any]:
    """Render a Home Assistant device state card with a clickable toggle.

    Args:
        entity_id: HA entity id (used to infer icon + toggle domain).
        name: Display name.
        area: Area / room name.
        state: "on" | "off" | "open" | "closed" | "unavailable".
        detail: Optional extra detail (e.g. temperature, setpoint).
        icon: Optional explicit icon: "light" | "garage" | "lock" |
            "camera" | "climate". Inferred from entity_id if omitted.
        brightness_pct: 0–100 brightness for lights. Rendered as "78%"
            next to the toggle switch in the card.

    Returns:
        ``{"status": "success", "block": "...", "instructions": "..."}``.
    """
    if state not in ("on", "off", "open", "closed", "unavailable"):
        return {
            "status": "error",
            "message": "state must be one of on/off/open/closed/unavailable",
        }
    data: Dict[str, Any] = {
        "id": entity_id,
        "name": name,
        "area": area,
        "state": state,
    }
    if detail:
        data["detail"] = detail
    resolved_icon = icon or infer_ha_icon(entity_id)
    if resolved_icon:
        data["icon"] = resolved_icon
    if brightness_pct is not None:
        try:
            data["brightness_pct"] = max(0, min(100, int(brightness_pct)))
        except (ValueError, TypeError):
            pass

    return {
        "status": "success",
        "block": format_card_block("ha-device", data),
        "instructions": "Include the 'block' string verbatim in your reply.",
    }


_VIDEO_SOURCES = {"youtube", "curiositystream"}
_VIDEO_STATUSES = {"in_library", "queued", "processing", "error", "not_added"}


@tool_error_handler("render kid video card")
def show_video_card(
    title: str,
    source: str,
    url: str,
    video_id: Optional[str] = None,
    channel: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    published_at: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    view_count: Optional[int] = None,
    tags: Optional[List[str]] = None,
    note: Optional[str] = None,
    subtitle: Optional[str] = None,
    status: Optional[str] = None,
    kideo_video_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Render a kid-video recommendation card inline in chat.

    Produces a card with thumbnail, channel/duration/source metadata, a Kideo
    library-status pill, and an "ADD TO KIDEO" direct-action button. Mirrors
    :func:`show_media_card` for movies/TV.

    Args:
        title: Video title.
        source: ``"youtube"`` or ``"curiositystream"``.
        url: Full video URL — required so the ADD TO KIDEO button can submit it.
        video_id: Source-specific id (YouTube watch id, CuriosityStream numeric id).
        channel: Channel / producer name.
        duration_seconds: Length in seconds (rendered as ``Hh MMm`` or ``MM:SS``).
        published_at: ISO timestamp; the year is rendered.
        thumbnail_url: Thumbnail image URL (16:9). Falls back to a glyph poster.
        view_count: View count (rendered as e.g. ``1.2M views``).
        tags: Educational tags rendered as small chips.
        note: Italic footer line — short educational rationale or pacing note.
        subtitle: Optional secondary line under the title.
        status: Override the auto-resolved Kideo status. One of
            ``"in_library" | "queued" | "processing" | "error" | "not_added"``.
        kideo_video_id: Override the auto-resolved Kideo UUID.

    Returns:
        ``{"status": "success", "block": "...", "instructions": "..."}``.
        Include the ``block`` string verbatim in your reply.
    """
    if source not in _VIDEO_SOURCES:
        return {
            "status": "error",
            "message": f"source must be one of {sorted(_VIDEO_SOURCES)}",
        }
    if status is not None and status not in _VIDEO_STATUSES:
        return {
            "status": "error",
            "message": f"status must be one of {sorted(_VIDEO_STATUSES)}",
        }
    if not url:
        return {"status": "error", "message": "url is required"}

    resolved_status: Optional[str] = status
    resolved_kideo_id = kideo_video_id
    if resolved_status is None:
        looked_status, looked_id = _lookup_kideo_status(url)
        resolved_status = looked_status or "not_added"
        if resolved_kideo_id is None:
            resolved_kideo_id = looked_id

    data: Dict[str, Any] = {
        "title": title,
        "source": source,
        "url": url,
        "status": resolved_status,
    }
    if video_id:
        data["video_id"] = video_id
    if channel:
        data["channel"] = channel
    if duration_seconds is not None:
        try:
            data["duration_seconds"] = max(0, int(duration_seconds))
        except (ValueError, TypeError):
            pass
    if published_at:
        data["published_at"] = published_at
    if thumbnail_url:
        data["thumbnail_url"] = thumbnail_url
    if view_count is not None:
        try:
            data["view_count"] = max(0, int(view_count))
        except (ValueError, TypeError):
            pass
    if tags:
        data["tags"] = [str(t) for t in tags if t]
    if note:
        data["note"] = note
    if subtitle:
        data["subtitle"] = subtitle
    if resolved_kideo_id:
        data["kideo_video_id"] = resolved_kideo_id

    return {
        "status": "success",
        "block": format_card_block("video", data),
        "instructions": "Include the 'block' string verbatim in your reply.",
    }


show_media_card_tool = FunctionTool(show_media_card)
show_season_breakdown_tool = FunctionTool(show_season_breakdown)
show_ha_device_card_tool = FunctionTool(show_ha_device_card)
show_video_card_tool = FunctionTool(show_video_card)

CARD_TOOLS = [
    show_media_card_tool,
    show_season_breakdown_tool,
    show_ha_device_card_tool,
    show_video_card_tool,
]
