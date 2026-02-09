"""
Home Assistant tool implementations for interacting with Home Assistant via REST API.

This module provides tools for getting entity states and controlling Home Assistant
entities through the REST API.
"""

import logging
import time
from typing import Dict, Any, List, Optional, Union

# Import the client singleton
from radbot.tools.homeassistant.ha_client_singleton import get_ha_client

logger = logging.getLogger(__name__)

def list_ha_entities() -> Dict[str, Any]:
    """
    Lists all available entities in Home Assistant, returning their ID, state,
    and friendly name if available.
    
    Returns:
        A dictionary with status and data containing entity information.
    """
    try:
        client = get_ha_client()
        if not client:
            return {"status": "error", "message": "Home Assistant client not configured."}
            
        entities = client.list_entities()
        if entities is None:  # Check if client returned None due to error
            return {"status": "error", "message": "Failed to retrieve entities from Home Assistant."}

        # Filter and format the output for the LLM
        formatted_entities = []
        for entity in entities:
            entity_id = entity.get('entity_id')
            state = entity.get('state')
            attributes = entity.get('attributes', {})
            friendly_name = attributes.get('friendly_name')
            if entity_id:
                formatted_entities.append({
                    "entity_id": entity_id,
                    "state": state,
                    "friendly_name": friendly_name if friendly_name else entity_id,  # Use ID if no friendly name
                    "attributes": {
                        k: v for k, v in attributes.items() 
                        if k in ["friendly_name", "unit_of_measurement", "device_class", "supported_features"]
                    }  # Only include key attributes
                })
        return {"status": "success", "data": formatted_entities}
    except Exception as e:
        logger.error(f"Error in list_ha_entities tool: {e}")
        return {"status": "error", "message": f"An internal error occurred: {str(e)}"}

def get_ha_entity_state(entity_id: str) -> Dict[str, Any]:
    """
    Gets the current state and attributes of a specific entity in Home Assistant.

    IMPORTANT: If you do not know the exact entity_id, call search_ha_entities
    first with the user's description to find the correct ID before calling this.

    Args:
        entity_id: The unique identifier of the entity (e.g., 'sensor.temperature_probe').

    Returns:
        A dictionary with status and data containing entity state information.
    """
    if not entity_id:
        return {"status": "error", "message": "Entity ID cannot be empty."}
        
    try:
        client = get_ha_client()
        if not client:
            return {"status": "error", "message": "Home Assistant client not configured."}
            
        state = client.get_state(entity_id)
        if state:
            # Return relevant parts of the state object
            return {"status": "success", "data": {
                "entity_id": state.get("entity_id"),
                "state": state.get("state"),
                "attributes": state.get("attributes", {}),
                "last_changed": state.get("last_changed")
            }}
        else:
            # Handles 404 or other client errors resulting in None
            return {"status": "error", "message": f"Entity '{entity_id}' not found or failed to retrieve state."}
    except Exception as e:
        logger.error(f"Error in get_ha_entity_state tool for {entity_id}: {e}")
        return {"status": "error", "message": f"An internal error occurred while fetching state for {entity_id}: {str(e)}"}

def turn_on_ha_entity(entity_id: str) -> Dict[str, Any]:
    """
    Turns on a Home Assistant entity (e.g., light, switch, etc.).

    IMPORTANT: If you do not know the exact entity_id, call search_ha_entities
    first with the user's description to find the correct ID before calling this.

    Args:
        entity_id: The unique identifier of the entity to turn on (e.g., 'switch.basement_plant_lamp').

    Returns:
        A dictionary with status and message about the action result.
    """
    if not entity_id:
        return {"status": "error", "message": "Entity ID cannot be empty."}
        
    try:
        client = get_ha_client()
        if not client:
            return {"status": "error", "message": "Home Assistant client not configured."}
            
        result = client.turn_on_entity(entity_id)
        if result is not None:
            # Format changed entities to make them more readable
            changed_states = [{"entity_id": s.get("entity_id"), "state": s.get("state")} for s in result]
            return {
                "status": "success", 
                "message": f"Turn on command sent to '{entity_id}'.", 
                "changed_states": changed_states
            }
        else:
            return {
                "status": "error", 
                "message": f"Failed to turn on entity '{entity_id}'. It might not support turn_on or an API error occurred."
            }
    except Exception as e:
        logger.error(f"Error in turn_on_ha_entity tool for {entity_id}: {e}")
        return {"status": "error", "message": f"An internal error occurred while turning on {entity_id}: {str(e)}"}

def turn_off_ha_entity(entity_id: str) -> Dict[str, Any]:
    """
    Turns off a Home Assistant entity (e.g., light, switch, etc.).

    IMPORTANT: If you do not know the exact entity_id, call search_ha_entities
    first with the user's description to find the correct ID before calling this.

    Args:
        entity_id: The unique identifier of the entity to turn off (e.g., 'switch.basement_plant_lamp').

    Returns:
        A dictionary with status and message about the action result.
    """
    if not entity_id:
        return {"status": "error", "message": "Entity ID cannot be empty."}
        
    try:
        client = get_ha_client()
        if not client:
            return {"status": "error", "message": "Home Assistant client not configured."}
            
        result = client.turn_off_entity(entity_id)
        if result is not None:
            # Format changed entities to make them more readable
            changed_states = [{"entity_id": s.get("entity_id"), "state": s.get("state")} for s in result]
            return {
                "status": "success", 
                "message": f"Turn off command sent to '{entity_id}'.", 
                "changed_states": changed_states
            }
        else:
            return {
                "status": "error", 
                "message": f"Failed to turn off entity '{entity_id}'. It might not support turn_off or an API error occurred."
            }
    except Exception as e:
        logger.error(f"Error in turn_off_ha_entity tool for {entity_id}: {e}")
        return {"status": "error", "message": f"An internal error occurred while turning off {entity_id}: {str(e)}"}

def toggle_ha_entity(entity_id: str) -> Dict[str, Any]:
    """
    Toggles the state of a Home Assistant entity (e.g., turns a light/switch on or off).

    IMPORTANT: If you do not know the exact entity_id, call search_ha_entities
    first with the user's description to find the correct ID before calling this.

    Args:
        entity_id: The unique identifier of the entity to toggle (e.g., 'switch.basement_plant_lamp').

    Returns:
        A dictionary with status and message about the action result.
    """
    if not entity_id:
        return {"status": "error", "message": "Entity ID cannot be empty."}
        
    try:
        client = get_ha_client()
        if not client:
            return {"status": "error", "message": "Home Assistant client not configured."}
            
        result = client.toggle_entity(entity_id)
        if result is not None:
            # Format changed entities to make them more readable
            changed_states = [{"entity_id": s.get("entity_id"), "state": s.get("state")} for s in result]
            return {
                "status": "success", 
                "message": f"Toggle command sent to '{entity_id}'.", 
                "changed_states": changed_states
            }
        else:
            return {
                "status": "error", 
                "message": f"Failed to toggle entity '{entity_id}'. It might not support toggle or an API error occurred."
            }
    except Exception as e:
        logger.error(f"Error in toggle_ha_entity tool for {entity_id}: {e}")
        return {"status": "error", "message": f"An internal error occurred while toggling {entity_id}: {str(e)}"}


def search_ha_entities(search_term: str, domain_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Search for Home Assistant entities by name, ID, or other attributes.
    Use this tool FIRST to find entity IDs before calling turn_on/turn_off/toggle/get_state.

    For example, if a user says "turn on the basement lights", call this with
    search_term="basement" to discover the correct entity_id, then use that ID
    with turn_on_ha_entity.

    Args:
        search_term: Text to search for in entity names and IDs (e.g., "basement", "kitchen light")
        domain_filter: Optional domain to restrict search (e.g., "light", "switch", "sensor")

    Returns:
        Dictionary with matching entities including their entity_id, friendly_name, and state
    """
    logger.info(f"Searching for Home Assistant entities with term: '{search_term}', domain: '{domain_filter}'")
    
    try:
        # Get the client
        client = get_ha_client()
        if not client:
            return {
                "status": "error", 
                "message": "Home Assistant client not configured",
                "search_term": search_term,
                "domain_filter": domain_filter,
                "match_count": 0,
                "matches": []
            }
            
        # Get all entities
        entities = client.list_entities()
        if entities is None:
            return {
                "status": "error",
                "message": "Failed to retrieve entities from Home Assistant",
                "search_term": search_term,
                "domain_filter": domain_filter,
                "match_count": 0,
                "matches": []
            }
            
        logger.info(f"Retrieved {len(entities)} entities from Home Assistant")
        
        # Collect all available domains
        domains = set()
        for entity in entities:
            entity_id = entity.get('entity_id', '')
            if '.' in entity_id:
                domain = entity_id.split('.')[0]
                domains.add(domain)
                
        # Convert search term to lowercase for case-insensitive matching
        search_term = search_term.lower()
        
        # Filter entities by domain if specified
        if domain_filter:
            entities = [
                entity for entity in entities
                if entity.get('entity_id', '').split('.')[0] == domain_filter
            ]
            
            if not entities:
                return {
                    "status": "error" if domain_filter not in domains else "success",
                    "message": f"Domain '{domain_filter}' {'not found' if domain_filter not in domains else 'has no entities'}",
                    "search_term": search_term,
                    "domain_filter": domain_filter,
                    "available_domains": sorted(list(domains)),
                    "match_count": 0,
                    "matches": []
                }
                
            logger.info(f"Filtered to {len(entities)} entities in domain '{domain_filter}'")
            
        # Find entities matching the search term
        matches = []
        for entity in entities:
            entity_id = entity.get('entity_id', '').lower()
            friendly_name = entity.get('attributes', {}).get('friendly_name', '').lower()
            
            # Calculate a match score
            score = 0
            match_reasons = []
            
            # Check for exact matches (highest priority)
            if search_term and search_term == entity_id:
                score = 100
                match_reasons.append("exact entity ID match")
            elif search_term and friendly_name and search_term == friendly_name:
                score = 95
                match_reasons.append("exact friendly name match")
                
            # Check for partial matches
            elif search_term and search_term in entity_id:
                score = 80
                match_reasons.append("partial entity ID match")
            elif search_term and friendly_name and search_term in friendly_name:
                score = 75
                match_reasons.append("partial friendly name match")
                
            # Include all entities if no search term provided
            elif not search_term:
                score = 50
                match_reasons.append("domain match")
                
            # Add to matches if there's a match
            if score > 0:
                matches.append({
                    "entity_id": entity.get('entity_id'),
                    "friendly_name": entity.get('attributes', {}).get('friendly_name', entity.get('entity_id')),
                    "state": entity.get('state'),
                    "domain": entity.get('entity_id', '').split('.')[0] if '.' in entity.get('entity_id', '') else "unknown",
                    "score": score,
                    "match_reasons": match_reasons
                })
                
        # Sort matches by score (highest first)
        matches.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(f"Found {len(matches)} matching entities for search term '{search_term}'")
        
        # Return the results
        return {
            "status": "success",
            "search_term": search_term,
            "domain_filter": domain_filter,
            "match_count": len(matches),
            "matches": matches[:10] if matches else [],  # Return top 10 matches
            "available_domains": sorted(list(domains))
        }
    except Exception as e:
        logger.error(f"Error in search_ha_entities: {e}")
        return {
            "status": "error",
            "message": f"An error occurred during search: {str(e)}",
            "search_term": search_term,
            "domain_filter": domain_filter,
            "match_count": 0,
            "matches": []
        }