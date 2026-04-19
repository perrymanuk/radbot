"""
Agent tools for Lidarr music collection management.

Provides tools to search for and add artists & albums via Lidarr.
All tools return ``{"status": "success", ...}`` or
``{"status": "error", "message": ...}`` per project convention.
"""

import logging
from typing import Any, Dict

from google.adk.tools import FunctionTool

from radbot.tools.shared.client_utils import client_or_error
from radbot.tools.shared.tool_decorator import tool_error_handler

from .lidarr_client import get_lidarr_client

logger = logging.getLogger(__name__)

# Max search results to return in chat (keeps responses readable)
_MAX_SEARCH_RESULTS = 15


def _format_artist(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a Lidarr artist lookup result into a compact dict."""
    return {
        "artist_name": item.get("artistName", ""),
        "foreign_artist_id": item.get("foreignArtistId", ""),
        "overview": (item.get("overview") or "")[:200],
        "status": item.get("status", ""),
        "artist_type": item.get("artistType", ""),
        "disambiguation": item.get("disambiguation", ""),
        "already_in_library": item.get("id", 0) > 0,
    }


def _format_album(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a Lidarr album lookup result into a compact dict."""
    artist = item.get("artist", {})
    return {
        "album_title": item.get("title", ""),
        "foreign_album_id": item.get("foreignAlbumId", ""),
        "artist_name": artist.get("artistName", ""),
        "foreign_artist_id": artist.get("foreignArtistId", ""),
        "release_date": item.get("releaseDate", ""),
        "album_type": item.get("albumType", ""),
        "overview": (item.get("overview") or "")[:200],
        "already_in_library": item.get("id", 0) > 0,
    }


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


@tool_error_handler("search Lidarr artists")
def search_lidarr_artist(query: str) -> Dict[str, Any]:
    """
    Search for music artists on Lidarr.

    Args:
        query: The artist name to search for.

    Returns:
        On success: {"status": "success", "results": [...], "total": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = client_or_error(get_lidarr_client, "Lidarr")
    if err:
        return err

    raw = client.lookup_artist(query)
    results = [_format_artist(a) for a in raw[:_MAX_SEARCH_RESULTS]]
    return {
        "status": "success",
        "results": results,
        "total": len(raw),
    }


@tool_error_handler("search Lidarr albums")
def search_lidarr_album(query: str) -> Dict[str, Any]:
    """
    Search for music albums on Lidarr.

    Args:
        query: The album name to search for.

    Returns:
        On success: {"status": "success", "results": [...], "total": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = client_or_error(get_lidarr_client, "Lidarr")
    if err:
        return err

    raw = client.lookup_album(query)
    results = [_format_album(a) for a in raw[:_MAX_SEARCH_RESULTS]]
    return {
        "status": "success",
        "results": results,
        "total": len(raw),
    }


@tool_error_handler("add Lidarr artist")
def add_lidarr_artist(
    foreign_artist_id: str,
    artist_name: str,
    monitored: bool = True,
) -> Dict[str, Any]:
    """
    Add an artist to Lidarr for monitoring and download.

    Use search_lidarr_artist first to get the foreign_artist_id.
    Automatically uses the first available root folder, quality profile,
    and metadata profile.

    Args:
        foreign_artist_id: The MusicBrainz artist ID (from search results).
        artist_name: The artist's name (for confirmation logging).
        monitored: Whether to monitor for new releases (default True).

    Returns:
        On success: {"status": "success", "artist_id": N, "artist_name": "...", "path": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = client_or_error(get_lidarr_client, "Lidarr")
    if err:
        return err

    # Fetch defaults for root folder, quality profile, metadata profile
    root_folders = client.get_root_folders()
    if not root_folders:
        return {"status": "error", "message": "No root folders configured in Lidarr"}

    quality_profiles = client.get_quality_profiles()
    if not quality_profiles:
        return {
            "status": "error",
            "message": "No quality profiles configured in Lidarr",
        }

    metadata_profiles = client.get_metadata_profiles()
    if not metadata_profiles:
        return {
            "status": "error",
            "message": "No metadata profiles configured in Lidarr",
        }

    artist_data = {
        "artistName": artist_name,
        "foreignArtistId": foreign_artist_id,
        "qualityProfileId": quality_profiles[0]["id"],
        "metadataProfileId": metadata_profiles[0]["id"],
        "rootFolderPath": root_folders[0]["path"],
        "monitored": monitored,
        "addOptions": {
            "monitor": "all" if monitored else "none",
            "searchForMissingAlbums": monitored,
        },
    }

    result = client.add_artist(artist_data)
    logger.info(
        "Lidarr artist added: %s (id=%s)",
        artist_name,
        result.get("id"),
    )
    return {
        "status": "success",
        "artist_id": result.get("id"),
        "artist_name": result.get("artistName", artist_name),
        "path": result.get("path", ""),
    }


@tool_error_handler("add Lidarr album")
def add_lidarr_album(
    foreign_album_id: str,
    album_title: str,
    foreign_artist_id: str,
    artist_name: str,
    monitored: bool = True,
) -> Dict[str, Any]:
    """
    Add a specific album to Lidarr for download.

    Use search_lidarr_album first to get the foreign_album_id and
    foreign_artist_id. If the artist is not already in Lidarr, the artist
    will be added automatically with only this album monitored.

    Args:
        foreign_album_id: The MusicBrainz album/release-group ID (from search results).
        album_title: The album title (for confirmation logging).
        foreign_artist_id: The MusicBrainz artist ID (from search results).
        artist_name: The artist's name.
        monitored: Whether to monitor this album (default True).

    Returns:
        On success: {"status": "success", "album_title": "...", "artist_name": "...", "artist_id": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = client_or_error(get_lidarr_client, "Lidarr")
    if err:
        return err

    # Fetch defaults
    root_folders = client.get_root_folders()
    if not root_folders:
        return {"status": "error", "message": "No root folders configured in Lidarr"}

    quality_profiles = client.get_quality_profiles()
    if not quality_profiles:
        return {
            "status": "error",
            "message": "No quality profiles configured in Lidarr",
        }

    metadata_profiles = client.get_metadata_profiles()
    if not metadata_profiles:
        return {
            "status": "error",
            "message": "No metadata profiles configured in Lidarr",
        }

    # Adding an album in Lidarr requires adding the artist with the
    # specific album selected for monitoring.
    artist_data = {
        "artistName": artist_name,
        "foreignArtistId": foreign_artist_id,
        "qualityProfileId": quality_profiles[0]["id"],
        "metadataProfileId": metadata_profiles[0]["id"],
        "rootFolderPath": root_folders[0]["path"],
        "monitored": True,
        "addOptions": {
            "monitor": "none",
            "searchForMissingAlbums": False,
            "albumsToMonitor": [foreign_album_id],
        },
    }

    result = client.add_artist(artist_data)
    logger.info(
        "Lidarr album added: '%s' by %s (artist_id=%s)",
        album_title,
        artist_name,
        result.get("id"),
    )
    return {
        "status": "success",
        "album_title": album_title,
        "artist_name": result.get("artistName", artist_name),
        "artist_id": result.get("id"),
    }


@tool_error_handler("list Lidarr quality profiles")
def list_lidarr_quality_profiles() -> Dict[str, Any]:
    """
    List available quality profiles in Lidarr.

    Returns:
        On success: {"status": "success", "profiles": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = client_or_error(get_lidarr_client, "Lidarr")
    if err:
        return err

    raw = client.get_quality_profiles()
    profiles = [
        {
            "id": p.get("id"),
            "name": p.get("name", ""),
        }
        for p in raw
    ]
    return {
        "status": "success",
        "profiles": profiles,
    }


# ---------------------------------------------------------------------------
# Wrap as ADK FunctionTools
# ---------------------------------------------------------------------------

search_lidarr_artist_tool = FunctionTool(search_lidarr_artist)
search_lidarr_album_tool = FunctionTool(search_lidarr_album)
add_lidarr_artist_tool = FunctionTool(add_lidarr_artist)
add_lidarr_album_tool = FunctionTool(add_lidarr_album)
list_lidarr_quality_profiles_tool = FunctionTool(list_lidarr_quality_profiles)

LIDARR_TOOLS = [
    search_lidarr_artist_tool,
    search_lidarr_album_tool,
    add_lidarr_artist_tool,
    add_lidarr_album_tool,
    list_lidarr_quality_profiles_tool,
]
