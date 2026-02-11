"""
Home Assistant entity search tools for MCP integration.

This module provides tools for searching and working with Home Assistant entities
via MCP Server integration.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def create_find_ha_entities_tool():
    """Create a function tool to search for Home Assistant entities."""
    import logging

    from radbot.tools.mcp.mcp_utils import find_home_assistant_entities

    logger = logging.getLogger(__name__)

    # For ADK 0.3.0 compatibility, we'll use the built-in tool creation
    # mechanism from the Agent Development Kit instead of directly creating a FunctionTool
    try:
        # ADK 0.3.0 approach using @tool decorator
        from google.adk.tools.decorators import tool

        # Create a decorated function with proper schema
        @tool(
            name="search_home_assistant_entities",
            description="Search for Home Assistant entities by name or area",
            parameters={
                "search_term": {
                    "type": "string",
                    "description": "Term to search for in entity names, like 'kitchen' or 'plant'",
                },
                "domain_filter": {
                    "type": "string",
                    "description": "Optional domain type to filter by (light, switch, etc.)",
                    "enum": [
                        "light",
                        "switch",
                        "sensor",
                        "media_player",
                        "climate",
                        "cover",
                        "vacuum",
                    ],
                    "required": False,
                },
            },
            required=["search_term"],
        )
        def search_home_assistant_entities(
            search_term: str, domain_filter: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Search for Home Assistant entities by name.

            Args:
                search_term: Text to search for in entity names/IDs
                domain_filter: Optional domain type to filter by (light, switch, etc.)

            Returns:
                Dictionary with matching entities
            """
            logger.info(
                f"Entity search called with term: '{search_term}', domain_filter: '{domain_filter}'"
            )
            result = find_home_assistant_entities(search_term, domain_filter)
            logger.info(
                f"Entity search result: {result.get('status', 'unknown')} (found {result.get('match_count', 0)} matches)"
            )
            return result

        logger.info(f"Created entity search tool using @tool decorator")
        return search_home_assistant_entities

    except (ImportError, AttributeError):
        # Fall back to direct FunctionTool creation
        logger.warning(
            "@tool decorator not available, falling back to FunctionTool creation"
        )

        from google.adk.tools import FunctionTool

        # Define the search function with exactly matching name as specified in schema
        def search_home_assistant_entities(
            search_term: str, domain_filter: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Search for Home Assistant entities by name.

            Args:
                search_term: Text to search for in entity names/IDs
                domain_filter: Optional domain type to filter by (light, switch, etc.)

            Returns:
                Dictionary with matching entities
            """
            logger.info(
                f"Entity search called with term: '{search_term}', domain_filter: '{domain_filter}'"
            )
            result = find_home_assistant_entities(search_term, domain_filter)
            logger.info(
                f"Entity search result: {result.get('status', 'unknown')} (found {result.get('match_count', 0)} matches)"
            )
            return result

        # Try FunctionTool creation with different approaches
        try:
            # First try the newer ADK 0.3.0 style
            tool = FunctionTool(
                function=search_home_assistant_entities,
                function_schema={
                    "name": "search_home_assistant_entities",
                    "description": "Search for Home Assistant entities by name or area",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_term": {
                                "type": "string",
                                "description": "Term to search for in entity names, like 'kitchen' or 'plant'",
                            },
                            "domain_filter": {
                                "type": "string",
                                "description": "Optional domain type to filter by (light, switch, etc.)",
                                "enum": [
                                    "light",
                                    "switch",
                                    "sensor",
                                    "media_player",
                                    "climate",
                                    "cover",
                                    "vacuum",
                                ],
                            },
                        },
                        "required": ["search_term"],
                    },
                },
            )
            logger.info("Created entity search tool using ADK 0.3.0 FunctionTool style")
        except TypeError:
            # Fall back to older ADK API
            tool = FunctionTool(
                search_home_assistant_entities,
                {
                    "name": "search_home_assistant_entities",
                    "description": "Search for Home Assistant entities by name or area",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_term": {
                                "type": "string",
                                "description": "Term to search for in entity names, like 'kitchen' or 'plant'",
                            },
                            "domain_filter": {
                                "type": "string",
                                "description": "Optional domain type to filter by (light, switch, etc.)",
                                "enum": [
                                    "light",
                                    "switch",
                                    "sensor",
                                    "media_player",
                                    "climate",
                                    "cover",
                                    "vacuum",
                                ],
                            },
                        },
                        "required": ["search_term"],
                    },
                },
            )
            logger.info("Created entity search tool using legacy FunctionTool style")

        return tool


# Create a pure function version of the search tool
def search_home_assistant_entities(
    search_term: str, domain_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for Home Assistant entities by name or area.

    Args:
        search_term: Term to search for in entity names, like 'kitchen' or 'plant'
        domain_filter: Optional domain type to filter by (light, switch, etc.)

    Returns:
        Dictionary with matching entities
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info(
        f"Entity search called with term: '{search_term}', domain_filter: '{domain_filter}'"
    )
    from radbot.tools.mcp.mcp_utils import find_home_assistant_entities

    try:
        result = find_home_assistant_entities(search_term, domain_filter)
        logger.info(
            f"Entity search result: {result.get('status', 'unknown')} (found {result.get('match_count', 0)} matches)"
        )

        # If no entities were found, provide a helpful message
        if not result.get("success"):
            if result.get("status") == "no_entities":
                return {
                    "success": False,
                    "status": "no_entities",
                    "message": "I couldn't find any entities in your Home Assistant system. This could be because:\n"
                    "1. Home Assistant MCP server is not properly configured\n"
                    "2. Your Home Assistant instance doesn't have any entities that match your search\n"
                    "3. The MCP integration doesn't support entity listing for your Home Assistant version\n\n"
                    "Please check your Home Assistant MCP server configuration.",
                    "search_term": search_term,
                    "domain_filter": domain_filter,
                    "supported_domains": result.get("supported_domains", []),
                    "match_count": 0,
                    "matches": [],
                }
            elif result.get("status") == "unsupported_domain":
                domain = (
                    search_term.split(".", 1)[0]
                    if "." in search_term
                    else domain_filter
                )
                supported_domains = result.get("supported_domains", [])

                return {
                    "success": False,
                    "status": "unsupported_domain",
                    "message": f"I couldn't find the entity because the domain '{domain}' is not supported by your Home Assistant MCP integration.\n\n"
                    f"Supported domains are: {', '.join(supported_domains) if supported_domains else 'None detected'}\n\n"
                    "This could be because:\n"
                    "1. The domain is not properly enabled in your Home Assistant instance\n"
                    "2. The domain is not exposed via the MCP integration\n"
                    "3. The MCP server configuration needs updating\n\n"
                    f"You searched for: {search_term}",
                    "search_term": search_term,
                    "domain_filter": domain_filter,
                    "supported_domains": supported_domains,
                    "domain": domain,
                    "match_count": 0,
                    "matches": [],
                }

        return result
    except Exception as e:
        logger.error(f"Error in search_home_assistant_entities: {str(e)}")
        # Return a more helpful error message
        return {
            "success": False,
            "error": str(e),
            "message": "There was a problem connecting to your Home Assistant system. "
            "Please check your Home Assistant MCP server configuration and ensure it's running.",
            "search_term": search_term,
            "domain_filter": domain_filter,
            "match_count": 0,
            "matches": [],
            "status": "error",
        }
