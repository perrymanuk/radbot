"""
Home Assistant entity state cache and search functionality.

This module provides a cache for Home Assistant entity states and search functionality
to find entities by name, domain, or attributes.
"""

import logging
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

from radbot.tools.homeassistant.ha_client_singleton import get_ha_client

logger = logging.getLogger(__name__)


class HomeAssistantStateCache:
    """
    Cache for Home Assistant entity states with search functionality.

    This class provides methods to:
    - Cache entity states for faster access
    - Search entities by name, domain, or other criteria
    - Match user queries to entity IDs
    """

    def __init__(self, cache_ttl: int = 30):
        """
        Initialize the state cache.

        Args:
            cache_ttl: Time-to-live for cached states in seconds (default: 30)
        """
        self.states = {}  # Dict[entity_id, state_obj]
        self.last_updated = 0  # Timestamp of last update
        self.cache_ttl = cache_ttl  # TTL in seconds
        self.domain_entities = {}  # Dict[domain, Set[entity_id]]
        self.name_map = {}  # Dict[friendly_name.lower(), entity_id]

    def _is_cache_valid(self) -> bool:
        """
        Check if cache is still valid based on TTL.

        Returns:
            True if cache is valid, False otherwise
        """
        return (time.time() - self.last_updated) < self.cache_ttl

    def update_cache(self) -> bool:
        """
        Update the state cache from Home Assistant.

        Returns:
            True if update successful, False otherwise
        """
        client = get_ha_client()
        if not client:
            logger.error("Cannot update cache: Home Assistant client not configured.")
            return False

        try:
            states = client.list_entities()
            if not states:
                logger.warning("No entities received from Home Assistant.")
                return False

            self.states = {}
            self.domain_entities = {}
            self.name_map = {}

            for state in states:
                entity_id = state.get("entity_id")
                if not entity_id:
                    continue

                # Store the state
                self.states[entity_id] = state

                # Group by domain
                domain = entity_id.split(".")[0] if "." in entity_id else "unknown"
                if domain not in self.domain_entities:
                    self.domain_entities[domain] = set()
                self.domain_entities[domain].add(entity_id)

                # Map friendly names for search
                friendly_name = state.get("attributes", {}).get("friendly_name")
                if friendly_name:
                    self.name_map[friendly_name.lower()] = entity_id

            self.last_updated = time.time()
            logger.info(f"Updated state cache with {len(self.states)} entities.")
            return True

        except Exception as e:
            logger.error(f"Error updating state cache: {e}")
            return False

    def get_entity_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get entity state with automatic cache update if needed.

        Args:
            entity_id: The entity ID to get state for

        Returns:
            Entity state object or None if not found
        """
        if not self._is_cache_valid():
            self.update_cache()

        return self.states.get(entity_id)

    def get_all_entities(self) -> List[Dict[str, Any]]:
        """
        Get all entity states with automatic cache update if needed.

        Returns:
            List of all entity state objects
        """
        if not self._is_cache_valid():
            self.update_cache()

        return list(self.states.values())

    def get_entities_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """
        Get all entities in a specific domain.

        Args:
            domain: Domain to filter by (e.g., 'light', 'switch')

        Returns:
            List of entity state objects in the domain
        """
        if not self._is_cache_valid():
            self.update_cache()

        entity_ids = self.domain_entities.get(domain, set())
        return [
            self.states[entity_id]
            for entity_id in entity_ids
            if entity_id in self.states
        ]

    def get_domains(self) -> List[str]:
        """
        Get list of available domains.

        Returns:
            List of domain names
        """
        if not self._is_cache_valid():
            self.update_cache()

        return list(self.domain_entities.keys())

    def search_entities(
        self, search_term: str, domain_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for entities by name, ID, or state attributes.

        Args:
            search_term: Text to search for in names and IDs
            domain_filter: Optional domain to restrict search to

        Returns:
            List of matching entity state objects with scores
        """
        if not self._is_cache_valid():
            self.update_cache()

        search_term = search_term.lower()

        # Store matches with their scores
        matches = []

        # If domain_filter is provided, only search within that domain
        target_entities = []
        if domain_filter and domain_filter in self.domain_entities:
            for entity_id in self.domain_entities[domain_filter]:
                if entity_id in self.states:
                    target_entities.append(self.states[entity_id])
        else:
            target_entities = list(self.states.values())

        # Exact friendly name match has highest priority
        for entity in target_entities:
            entity_id = entity.get("entity_id", "")
            friendly_name = entity.get("attributes", {}).get("friendly_name")

            score = 0
            match_reasons = []

            # Check exact matches first (highest priority)
            if friendly_name and search_term == friendly_name.lower():
                score = 100
                match_reasons.append("exact friendly name match")
            elif search_term == entity_id.lower():
                score = 95
                match_reasons.append("exact entity ID match")

            # Check partial matches
            elif friendly_name and search_term in friendly_name.lower():
                # Calculate similarity score
                similarity = (
                    SequenceMatcher(None, search_term, friendly_name.lower()).ratio()
                    * 80
                )
                score = max(score, similarity)
                match_reasons.append("partial friendly name match")

            elif search_term in entity_id.lower():
                # Calculate similarity score
                similarity = (
                    SequenceMatcher(None, search_term, entity_id.lower()).ratio() * 70
                )
                score = max(score, similarity)
                match_reasons.append("partial entity ID match")

            # Check attribute matches
            for attr_name, attr_value in entity.get("attributes", {}).items():
                if isinstance(attr_value, str) and search_term in attr_value.lower():
                    score = max(score, 50)
                    match_reasons.append(f"attribute {attr_name} match")

            # Check state match
            entity_state = entity.get("state", "")
            if isinstance(entity_state, str) and search_term in entity_state.lower():
                score = max(score, 40)
                match_reasons.append("state match")

            # Add to matches if score is above threshold
            if score > 0:
                matches.append(
                    {"entity": entity, "score": score, "reasons": match_reasons}
                )

        # Sort by score (highest first)
        matches.sort(key=lambda x: x["score"], reverse=True)

        # Format the results
        results = []
        for match in matches:
            entity = match["entity"]
            entity_id = entity.get("entity_id")
            friendly_name = entity.get("attributes", {}).get("friendly_name", entity_id)

            results.append(
                {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "state": entity.get("state"),
                    "domain": (
                        entity_id.split(".")[0] if "." in entity_id else "unknown"
                    ),
                    "score": match["score"],
                    "match_reasons": match["reasons"],
                }
            )

        return results


# Create a singleton instance
_cache_instance = None


def get_state_cache() -> HomeAssistantStateCache:
    """
    Get the singleton state cache instance.

    Returns:
        The state cache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = HomeAssistantStateCache()

    return _cache_instance


def search_ha_entities(
    search_term: str, domain_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for Home Assistant entities by name, ID, or state.

    Args:
        search_term: Text to search for in names and IDs
        domain_filter: Optional domain to restrict search to

    Returns:
        Dictionary with search results
    """
    if not search_term:
        return {"status": "error", "message": "Search term cannot be empty."}

    try:
        cache = get_state_cache()
        matches = cache.search_entities(search_term, domain_filter)

        domains = cache.get_domains()

        if not matches:
            if domain_filter and domain_filter not in domains:
                return {
                    "status": "error",
                    "message": f"Domain '{domain_filter}' not found. Available domains: {', '.join(sorted(domains))}",
                    "search_term": search_term,
                    "domain_filter": domain_filter,
                    "available_domains": sorted(domains),
                    "match_count": 0,
                    "matches": [],
                }
            else:
                return {
                    "status": "success",
                    "message": f"No entities found matching '{search_term}'",
                    "search_term": search_term,
                    "domain_filter": domain_filter,
                    "available_domains": sorted(domains),
                    "match_count": 0,
                    "matches": [],
                }

        return {
            "status": "success",
            "search_term": search_term,
            "domain_filter": domain_filter,
            "match_count": len(matches),
            "matches": matches[:10],  # Return top 10 matches
            "available_domains": sorted(domains),
        }
    except Exception as e:
        logger.error(f"Error in search_ha_entities: {e}")
        return {
            "status": "error",
            "message": f"An error occurred during search: {str(e)}",
            "search_term": search_term,
            "domain_filter": domain_filter,
            "match_count": 0,
            "matches": [],
        }
