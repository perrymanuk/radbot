"""Media REST endpoints for direct-action buttons in MediaCard.

Thin wrappers over :mod:`radbot.tools.overseerr.overseerr_client` that let the
frontend populate and act on media cards without a full LLM roundtrip.

Endpoints:
  * ``GET  /api/media/search?query=...``    — top-N search results
  * ``GET  /api/media/{tmdb_id}?media_type`` — enriched details
  * ``POST /api/media/request``              — submit download request

Response shape matches the frontend ``MediaCardData`` so the search endpoint
can feed the card UI directly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from radbot.tools.overseerr.overseerr_client import get_overseerr_client
from radbot.tools.overseerr.overseerr_tools import MEDIA_STATUS, REQUEST_STATUS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])

_MAX_SEARCH_RESULTS = 15

# TMDB poster image base. w342 is a good middle-ground (342px wide).
_TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"


def _poster_url(path: Optional[str]) -> Optional[str]:
    """Build a full TMDB poster URL from a posterPath ('/abc.jpg')."""
    if not path or not isinstance(path, str):
        return None
    if path.startswith("http"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"{_TMDB_IMAGE_BASE}{path}"


# ── Shape helpers ─────────────────────────────────────────


def _status_from_media_info(media_info: Optional[Dict[str, Any]]) -> str:
    """Map Overseerr MediaStatus → frontend status enum."""
    if not media_info:
        return "missing"
    code = media_info.get("status", 0)
    # 5 Available, 4 Partially, 3 Processing/Downloading, 2 Pending, else missing
    if code == 5:
        return "available"
    if code == 4:
        return "partial"
    if code in (2, 3):
        return "downloading"
    return "missing"


def _year_from(raw: Dict[str, Any], media_type: str) -> Optional[int]:
    date = raw.get("releaseDate") if media_type == "movie" else raw.get("firstAirDate")
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


def _year_range_from(raw: Dict[str, Any]) -> Optional[str]:
    start = raw.get("firstAirDate")
    end = raw.get("lastAirDate")
    if not isinstance(start, str) or len(start) < 4:
        return None
    s = start[:4]
    if isinstance(end, str) and len(end) >= 4 and end[:4] != s:
        return f"{s}-{end[:4]}"
    return s


def _search_item_to_card(item: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a raw Overseerr search hit into MediaCardData."""
    media_type = item.get("mediaType", "unknown")
    if media_type not in ("movie", "tv"):
        return {}
    kind = "movie" if media_type == "movie" else "show"
    title = (item.get("title") or item.get("name") or "").strip()
    year = _year_from(item, media_type)
    overview = (item.get("overview") or "").strip()
    status = _status_from_media_info(item.get("mediaInfo"))

    poster: Dict[str, Any] = {
        "accent": _accent_for(title),
        "title": _poster_glyph(title),
    }
    url = _poster_url(item.get("posterPath"))
    if url:
        poster["url"] = url

    card: Dict[str, Any] = {
        "title": title or "?",
        "kind": kind,
        "status": status,
        "tmdb_id": item.get("id"),
        "media_type": media_type,
        "poster": poster,
    }
    if year:
        card["year"] = year
    if overview:
        card["note"] = overview[:140] + ("…" if len(overview) > 140 else "")
    return card


_ACCENTS = ("sunset", "violet", "sky", "magenta")


def _accent_for(s: str) -> str:
    """Stable accent color per title so the same show always gets the same hue."""
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return _ACCENTS[h % len(_ACCENTS)]


def _poster_glyph(title: str) -> str:
    """Large centered glyph for the poster placeholder. First non-space char
    from the title, or the first letter."""
    for ch in title.strip():
        if not ch.isspace():
            return ch.upper()
    return "?"


# ── Routes ────────────────────────────────────────────────


@router.get("/search")
async def search_media(
    query: str = Query(..., min_length=1),
    limit: int = Query(_MAX_SEARCH_RESULTS, ge=1, le=50),
) -> Dict[str, Any]:
    """Search Overseerr. Returns ``{results: MediaCardData[]}``."""
    client = get_overseerr_client()
    if client is None:
        raise HTTPException(503, "Overseerr not configured — set up via Admin UI")
    try:
        data = client.search(query)
    except Exception as e:
        logger.error("Overseerr search failed: %s", e)
        raise HTTPException(502, f"Overseerr search failed: {e}")

    raw_results = (data or {}).get("results", [])[:limit]
    cards: List[Dict[str, Any]] = []
    for item in raw_results:
        card = _search_item_to_card(item)
        if card:
            cards.append(card)
    return {"results": cards, "total": (data or {}).get("totalResults", len(cards))}


@router.get("/{tmdb_id}")
async def get_media_details(
    tmdb_id: int,
    media_type: str = Query(..., pattern="^(movie|tv)$"),
) -> Dict[str, Any]:
    """Enriched detail for a single title. Returns MediaCardData + seasons."""
    client = get_overseerr_client()
    if client is None:
        raise HTTPException(503, "Overseerr not configured — set up via Admin UI")
    try:
        raw = client.get_movie(tmdb_id) if media_type == "movie" else client.get_tv(tmdb_id)
    except Exception as e:
        logger.error("Overseerr detail fetch failed: %s", e)
        raise HTTPException(502, f"Overseerr detail fetch failed: {e}")

    title = (raw.get("title") or raw.get("name") or "").strip()
    kind = "movie" if media_type == "movie" else "show"
    status = _status_from_media_info(raw.get("mediaInfo"))

    poster: Dict[str, Any] = {
        "accent": _accent_for(title),
        "title": _poster_glyph(title),
    }
    url = _poster_url(raw.get("posterPath"))
    if url:
        poster["url"] = url

    card: Dict[str, Any] = {
        "title": title or "?",
        "kind": kind,
        "status": status,
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "content_rating": _extract_content_rating(raw, media_type),
        "poster": poster,
    }
    year = _year_from(raw, media_type)
    if year:
        card["year"] = year
    if media_type == "tv":
        yr = _year_range_from(raw)
        if yr:
            card["year_range"] = yr
        seasons = [
            s for s in (raw.get("seasons") or []) if s.get("seasonNumber", 0) > 0
        ]
        total_eps = sum(int(s.get("episodeCount") or 0) for s in seasons)
        card["season_count"] = len(seasons)
        card["episode_count"] = total_eps
        runtime = raw.get("episodeRunTime") or []
        if runtime:
            card["episode_runtime"] = f"{int(runtime[0])}m"

        # Partial availability: pull per-season episode counts from mediaInfo if present
        media_info = raw.get("mediaInfo") or {}
        if status == "partial":
            have = 0
            total = 0
            for s in media_info.get("seasons", []) or []:
                if s.get("status") in (4, 5):  # partially available / available
                    have += int(s.get("episodeCount") or 0)
                total += int(s.get("episodeCount") or 0)
            if total_eps:
                card["on_server"] = {"have": have or 0, "total": total or total_eps}

    overview = (raw.get("overview") or "").strip()
    if overview:
        card["note"] = overview[:200] + ("…" if len(overview) > 200 else "")

    return card


class MediaRequestBody(BaseModel):
    tmdb_id: int
    media_type: str  # "movie" | "tv"
    seasons: Optional[List[int]] = None  # TV only; empty → all


@router.post("/request")
async def request_media(body: MediaRequestBody) -> Dict[str, Any]:
    """Submit a download request to Overseerr."""
    if body.media_type not in ("movie", "tv"):
        raise HTTPException(400, "media_type must be 'movie' or 'tv'")
    client = get_overseerr_client()
    if client is None:
        raise HTTPException(503, "Overseerr not configured — set up via Admin UI")

    seasons = body.seasons
    if body.media_type == "tv" and seasons is None:
        try:
            raw = client.get_tv(body.tmdb_id)
            seasons = [
                s["seasonNumber"]
                for s in (raw.get("seasons") or [])
                if s.get("seasonNumber", 0) > 0
            ]
        except Exception as e:
            logger.warning("Could not fetch seasons for TV request: %s", e)
            seasons = []

    try:
        result = client.create_request(body.media_type, body.tmdb_id, seasons=seasons)
    except Exception as e:
        logger.error("Overseerr request failed: %s", e)
        raise HTTPException(502, f"Overseerr request failed: {e}")

    req_status = REQUEST_STATUS.get(result.get("status", 0), "Submitted")
    media_info = result.get("media") or {}
    media_status = MEDIA_STATUS.get(media_info.get("status", 0), "Unknown")
    return {
        "status": "success",
        "request_id": result.get("id"),
        "request_status": req_status,
        "media_status": media_status,
    }


def _extract_content_rating(raw: Dict[str, Any], media_type: str) -> Optional[str]:
    """Best-effort TV-rating / MPAA rating extraction from Overseerr details."""
    if media_type == "tv":
        for cr in raw.get("contentRatings") or []:
            if cr.get("iso_3166_1") == "US" and cr.get("rating"):
                return cr["rating"]
    else:
        for rr in raw.get("releases") or []:
            if rr.get("iso_3166_1") == "US":
                for r in rr.get("release_dates") or []:
                    if r.get("certification"):
                        return r["certification"]
    return None


def register_media_router(app):
    app.include_router(router)
    logger.debug("Media router registered")
