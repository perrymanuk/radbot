"""
Lidarr music collection manager tools for the radbot agent.

This package provides tools for searching and adding artists & albums
via a Lidarr instance.
"""

from .lidarr_tools import (
    LIDARR_TOOLS,
    add_lidarr_album_tool,
    add_lidarr_artist_tool,
    list_lidarr_quality_profiles_tool,
    search_lidarr_album_tool,
    search_lidarr_artist_tool,
)

__all__ = [
    "search_lidarr_artist_tool",
    "search_lidarr_album_tool",
    "add_lidarr_artist_tool",
    "add_lidarr_album_tool",
    "list_lidarr_quality_profiles_tool",
    "LIDARR_TOOLS",
]
