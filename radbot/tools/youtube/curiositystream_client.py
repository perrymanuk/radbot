"""CuriosityStream search client using their Algolia-powered search index.

CuriosityStream is a documentary streaming service with high-quality
educational content. Search uses their public Algolia index with
referer-based access control.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Public Algolia credentials (client-side, extracted from curiositystream.com JS bundle)
_ALGOLIA_APP_ID = "261QMVOKMX"
_ALGOLIA_API_KEY = "947837fd3eb2126d1cd9b2e9265fa7d3"
_ALGOLIA_INDEX = "poc7"
_ALGOLIA_URL = f"https://{_ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"

_ALGOLIA_HEADERS = {
    "X-Algolia-Application-Id": _ALGOLIA_APP_ID,
    "X-Algolia-API-Key": _ALGOLIA_API_KEY,
    "Content-Type": "application/json",
    "Referer": "https://curiositystream.com/",
    "Origin": "https://curiositystream.com",
}


def search_videos(
    query: str,
    max_results: int = 10,
    kid_friendly_only: bool = True,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Search CuriosityStream for documentary videos.

    Args:
        query: Search query string.
        max_results: Number of results (1-50, default 10).
        kid_friendly_only: Only return child-friendly content (default True).
        categories: Optional list of category filters (e.g. ["science", "nature", "history"]).

    Returns:
        Dict with "items" list and total hit count.
    """
    params_parts = [
        f"query={query}",
        f"hitsPerPage={min(max(1, max_results), 50)}",
    ]

    # Build facet filters
    facet_filters = []
    if kid_friendly_only:
        facet_filters.append(["kidFriendly:true"])
    if categories:
        # OR within categories: any of these categories
        facet_filters.append([f"categories:{c}" for c in categories])

    if facet_filters:
        import json

        params_parts.append(f"facetFilters={json.dumps(facet_filters)}")

    params_str = "&".join(params_parts)

    response = httpx.post(
        _ALGOLIA_URL,
        headers=_ALGOLIA_HEADERS,
        json={
            "requests": [
                {"indexName": _ALGOLIA_INDEX, "params": params_str},
            ]
        },
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    result = data["results"][0]
    items = []
    for hit in result.get("hits", []):
        items.append(
            {
                "video_id": hit.get("videoId"),
                "title": hit.get("title"),
                "description": hit.get("description", ""),
                "categories": hit.get("categories", []),
                "producer": hit.get("producer", ""),
                "series_title": hit.get("seriesTitle", ""),
                "kid_friendly": hit.get("kidFriendly", False),
                "duration": hit.get("duration"),
                "rating": hit.get("rating_percentage"),
                "is_short": hit.get("isShort", False),
                "url": f"https://curiositystream.com/video/{hit.get('videoId')}",
                "contents_keywords": hit.get("contents", ""),
            }
        )

    return {
        "items": items,
        "total_results": result.get("nbHits", 0),
    }


def get_categories() -> List[str]:
    """Get available CuriosityStream categories by querying with facets.

    Returns:
        List of category names.
    """
    response = httpx.post(
        _ALGOLIA_URL,
        headers=_ALGOLIA_HEADERS,
        json={
            "requests": [
                {
                    "indexName": _ALGOLIA_INDEX,
                    "params": "query=&hitsPerPage=0&facets=[\"categories\"]",
                },
            ]
        },
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()
    facets = data["results"][0].get("facets", {}).get("categories", {})
    # Return sorted by count (most content first)
    return sorted(facets.keys(), key=lambda k: facets[k], reverse=True)
