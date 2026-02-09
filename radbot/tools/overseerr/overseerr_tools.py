"""
Agent tools for Overseerr media request management.

Provides tools to search, inspect, and request movies & TV shows via
Overseerr.  All tools return ``{"status": "success", ...}`` or
``{"status": "error", "message": ...}`` per project convention.
"""

import logging
import traceback
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from .overseerr_client import get_overseerr_client

logger = logging.getLogger(__name__)

# Max search results to return in chat (keeps responses readable)
_MAX_SEARCH_RESULTS = 15

# Request status codes (from Overseerr MediaRequestStatus)
REQUEST_STATUS = {
    1: "Pending",
    2: "Approved",
    3: "Declined",
    4: "Failed",
    5: "Completed",
}

# Media status codes (from Overseerr MediaStatus) — different numbering!
MEDIA_STATUS = {
    1: "Unknown",
    2: "Pending",
    3: "Processing",
    4: "Partially Available",
    5: "Available",
    6: "Deleted",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _client_or_error():
    """Return (client, None) or (None, error_dict)."""
    client = get_overseerr_client()
    if client is None:
        return None, {
            "status": "error",
            "message": (
                "Overseerr is not configured. Set integrations.overseerr in "
                "the admin UI or OVERSEERR_URL/OVERSEERR_API_KEY env vars."
            ),
        }
    return client, None


def _format_search_result(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise an Overseerr search result into a compact dict."""
    media_type = item.get("mediaType", "unknown")
    result: Dict[str, Any] = {
        "media_type": media_type,
        "tmdb_id": item.get("id"),
    }
    if media_type == "movie":
        result["title"] = item.get("title", "")
        result["release_date"] = item.get("releaseDate", "")
        result["overview"] = (item.get("overview") or "")[:200]
    elif media_type == "tv":
        result["title"] = item.get("name", "")
        result["first_air_date"] = item.get("firstAirDate", "")
        result["overview"] = (item.get("overview") or "")[:200]
    else:
        result["title"] = item.get("title") or item.get("name") or "?"

    # Media status from Overseerr (if already requested/available)
    media_info = item.get("mediaInfo")
    if media_info:
        result["media_status"] = MEDIA_STATUS.get(
            media_info.get("status", 0), "Unknown"
        )
    return result


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def search_overseerr_media(
    query: str,
    page: int = 1,
) -> Dict[str, Any]:
    """
    Search for movies and TV shows on Overseerr.

    Args:
        query: The search term (movie or TV show name).
        page: Result page number (default 1).

    Returns:
        On success: {"status": "success", "results": [...], "total": N, "page": N, "total_pages": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        data = client.search(query, page=max(1, page))
        raw_results = data.get("results", [])
        results = [_format_search_result(r) for r in raw_results[:_MAX_SEARCH_RESULTS]]
        return {
            "status": "success",
            "results": results,
            "total": data.get("totalResults", len(results)),
            "page": data.get("page", page),
            "total_pages": data.get("totalPages", 1),
        }
    except Exception as e:
        msg = f"Overseerr search failed: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_overseerr_media_details(
    tmdb_id: int,
    media_type: str,
) -> Dict[str, Any]:
    """
    Get detailed information about a movie or TV show from Overseerr.

    Args:
        tmdb_id: The TMDB ID of the movie or TV show.
        media_type: Either "movie" or "tv".

    Returns:
        On success: {"status": "success", "details": {...}}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    if media_type not in ("movie", "tv"):
        return {"status": "error", "message": "media_type must be 'movie' or 'tv'"}

    try:
        if media_type == "movie":
            raw = client.get_movie(tmdb_id)
            details: Dict[str, Any] = {
                "media_type": "movie",
                "tmdb_id": raw.get("id"),
                "title": raw.get("title", ""),
                "release_date": raw.get("releaseDate", ""),
                "overview": raw.get("overview", ""),
                "runtime": raw.get("runtime"),
                "genres": [g.get("name", "") for g in raw.get("genres", [])],
                "vote_average": raw.get("voteAverage"),
            }
        else:
            raw = client.get_tv(tmdb_id)
            seasons = []
            for s in raw.get("seasons", []):
                if s.get("seasonNumber", 0) > 0:  # skip specials (season 0)
                    seasons.append({
                        "season_number": s.get("seasonNumber"),
                        "episode_count": s.get("episodeCount", 0),
                        "name": s.get("name", ""),
                    })
            details = {
                "media_type": "tv",
                "tmdb_id": raw.get("id"),
                "title": raw.get("name", ""),
                "first_air_date": raw.get("firstAirDate", ""),
                "overview": raw.get("overview", ""),
                "number_of_seasons": raw.get("numberOfSeasons"),
                "genres": [g.get("name", "") for g in raw.get("genres", [])],
                "vote_average": raw.get("voteAverage"),
                "seasons": seasons,
            }

        # Include Overseerr media status if present
        media_info = raw.get("mediaInfo")
        if media_info:
            details["media_status"] = MEDIA_STATUS.get(
                media_info.get("status", 0), "Unknown"
            )

        return {"status": "success", "details": details}
    except Exception as e:
        msg = f"Failed to get {media_type} details (TMDB {tmdb_id}): {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def request_overseerr_media(
    tmdb_id: int,
    media_type: str,
    seasons: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Submit a media request to Overseerr.

    Args:
        tmdb_id: The TMDB ID of the movie or TV show to request.
        media_type: Either "movie" or "tv".
        seasons: Optional list of season numbers to request (TV only).
                 If omitted for TV, requests all seasons.

    Returns:
        On success: {"status": "success", "request_id": N, "media_status": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    if media_type not in ("movie", "tv"):
        return {"status": "error", "message": "media_type must be 'movie' or 'tv'"}

    try:
        # For TV with no seasons specified, fetch all season numbers
        tv_seasons = seasons
        if media_type == "tv" and tv_seasons is None:
            raw = client.get_tv(tmdb_id)
            tv_seasons = [
                s["seasonNumber"]
                for s in raw.get("seasons", [])
                if s.get("seasonNumber", 0) > 0
            ]

        result = client.create_request(media_type, tmdb_id, seasons=tv_seasons)
        req_status = REQUEST_STATUS.get(
            result.get("status", 0), "Submitted"
        )
        logger.info(
            "Overseerr request created: %s %s (id=%s)",
            media_type, tmdb_id, result.get("id"),
        )
        return {
            "status": "success",
            "request_id": result.get("id"),
            "media_status": req_status,
        }
    except Exception as e:
        msg = f"Failed to request {media_type} (TMDB {tmdb_id}): {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def list_overseerr_requests(
    max_results: int = 20,
    filter_status: str = "all",
) -> Dict[str, Any]:
    """
    List current media requests on Overseerr.

    Args:
        max_results: Maximum number of requests to return (default 20, max 50).
        filter_status: Filter by status: "all", "pending", "approved",
                       "processing", "available", "unavailable", "failed",
                       "completed", or "deleted".

    Returns:
        On success: {"status": "success", "requests": [...], "total": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        take = min(max(1, max_results), 50)
        data = client.list_requests(
            take=take,
            filter_status=filter_status if filter_status != "all" else None,
        )

        requests_list = []
        for req in data.get("results", []):
            media = req.get("media", {})
            info = req.get("requestedBy", {})
            item: Dict[str, Any] = {
                "request_id": req.get("id"),
                "media_type": req.get("type"),
                "tmdb_id": media.get("tmdbId"),
                "request_status": REQUEST_STATUS.get(
                    req.get("status", 0), "Unknown"
                ),
                "media_status": MEDIA_STATUS.get(
                    media.get("status", 0), "Unknown"
                ),
                "requested_by": info.get("displayName") or info.get("email", ""),
                "created_at": req.get("createdAt", ""),
            }
            requests_list.append(item)

        return {
            "status": "success",
            "requests": requests_list,
            "total": data.get("pageInfo", {}).get("results", len(requests_list)),
        }
    except Exception as e:
        msg = f"Failed to list Overseerr requests: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


# ---------------------------------------------------------------------------
# Wrap as ADK FunctionTools
# ---------------------------------------------------------------------------

search_overseerr_media_tool = FunctionTool(search_overseerr_media)
get_overseerr_media_details_tool = FunctionTool(get_overseerr_media_details)
request_overseerr_media_tool = FunctionTool(request_overseerr_media)
list_overseerr_requests_tool = FunctionTool(list_overseerr_requests)

OVERSEERR_TOOLS = [
    search_overseerr_media_tool,
    get_overseerr_media_details_tool,
    request_overseerr_media_tool,
    list_overseerr_requests_tool,
]
