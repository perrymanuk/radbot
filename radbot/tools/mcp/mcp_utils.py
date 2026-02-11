"""
Utility functions for working with the Model Context Protocol (MCP).

This module provides helper functions for testing and debugging MCP connections.
"""

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Union

from dotenv import load_dotenv
from google.adk.tools import FunctionTool

from radbot.tools.mcp.mcp_tools import create_home_assistant_toolset

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def test_home_assistant_connection() -> Dict[str, Any]:
    """
    Test the connection to the Home Assistant MCP server.

    This function attempts to connect to the Home Assistant MCP server and
    retrieve basic information about available tools.

    Returns:
        Dictionary with the test results and information
    """
    # Initialize the Home Assistant MCP tools (ADK 0.4.0 returns a list of tools)
    ha_tools = create_home_assistant_toolset()

    if not ha_tools:
        return {
            "success": False,
            "status": "initialization_failed",
            "error": "Failed to create Home Assistant MCP toolset",
            "details": None,
        }

    # Process the tools
    try:
        # Extract detailed info about each tool
        tool_infos = []
        for tool in ha_tools:
            tool_info = {}

            # Get the name
            if hasattr(tool, "name"):
                tool_info["name"] = tool.name
            elif hasattr(tool, "__name__"):
                tool_info["name"] = tool.__name__
            else:
                tool_info["name"] = str(type(tool))

            # Get the description if available
            if hasattr(tool, "description"):
                tool_info["description"] = tool.description

            # Get parameter info if available
            if hasattr(tool, "parameters"):
                tool_info["parameters"] = str(tool.parameters)

            tool_infos.append(tool_info)

        # Extract just the names for the simple list
        tool_names = [info["name"] for info in tool_infos]

        result = {
            "success": True,
            "status": "connected",
            "tools_count": len(tool_names),
            "tools": tool_names,
            "tool_details": tool_infos[
                :5
            ],  # Include details for the first 5 tools only
        }

        # Extract common domains as well
        domains = set()
        common_domains = [
            "light",
            "switch",
            "sensor",
            "climate",
            "media",
            "vacuum",
            "scene",
            "cover",
            "fan",
            "lock",
            "input",
        ]

        for tool_name in tool_names:
            for domain in common_domains:
                if domain.lower() in tool_name.lower():
                    domains.add(domain)
                    break

        if domains:
            result["detected_domains"] = sorted(list(domains))

        return result
    except Exception as e:
        logger.error(f"Error testing Home Assistant connection: {str(e)}")
        return {
            "success": False,
            "status": "connection_error",
            "error": str(e),
            "details": None,
        }


import asyncio


async def _check_home_assistant_entity_async(entity_id: str) -> Dict[str, Any]:
    """
    Async implementation to check a Home Assistant entity exists and get its current state.

    Args:
        entity_id: The entity ID to check (e.g., 'light.living_room')

    Returns:
        Dictionary with entity information or error details
    """
    # Import here to avoid circular imports
    from radbot.tools.mcp.mcp_tools import _create_home_assistant_toolset_async

    # Initialize the Home Assistant MCP
    ha_tools, exit_stack = await _create_home_assistant_toolset_async()

    if not ha_tools or len(ha_tools) == 0:
        return {
            "success": False,
            "status": "initialization_failed",
            "error": "Failed to create Home Assistant MCP toolset",
            "details": None,
        }

    try:
        # Find the appropriate tool based on entity domain
        domain = entity_id.split(".")[0] if "." in entity_id else None

        if not domain:
            return {
                "success": False,
                "status": "invalid_entity_id",
                "error": f"Invalid entity ID format: {entity_id}",
                "details": "Entity ID should be in the format 'domain.entity_name'",
            }

        # Find the get_state tool for this domain
        get_state_tool = None
        for tool in ha_tools:
            # Check different naming patterns to accommodate ADK 0.4.0 changes
            if hasattr(tool, "name"):
                # Traditional pattern: home_assistant_mcp.{domain}.get_state
                if tool.name == f"home_assistant_mcp.{domain}.get_state":
                    get_state_tool = tool
                    break
                # Alternative pattern: HassDomainGetState
                if tool.name.lower() == f"hass{domain.lower()}getstate":
                    get_state_tool = tool
                    break
                # Other possible patterns
                if tool.name.lower() == f"{domain.lower()}.get_state":
                    get_state_tool = tool
                    break

        if not get_state_tool:
            return {
                "success": False,
                "status": "unsupported_domain",
                "error": f"Domain {domain} is not supported or no get_state tool available",
                "entity_id": entity_id,
                "domain": domain,
            }

        # Call the tool with the entity_id
        try:
            # Call the get_state tool
            result = await get_state_tool(entity_id=entity_id)
            return {
                "success": True,
                "status": "entity_found",
                "entity_id": entity_id,
                "domain": domain,
                "state": result,
                "details": f"Successfully retrieved state for {entity_id}",
            }
        except Exception as call_error:
            return {
                "success": False,
                "status": "entity_error",
                "error": str(call_error),
                "entity_id": entity_id,
                "domain": domain,
            }
    except Exception as e:
        logger.error(f"Error checking Home Assistant entity {entity_id}: {str(e)}")
        return {
            "success": False,
            "status": "check_error",
            "error": str(e),
            "entity_id": entity_id,
        }
    finally:
        # Clean up resources
        if exit_stack:
            try:
                await exit_stack.aclose()
            except Exception as close_error:
                logger.error(f"Error closing resources: {str(close_error)}")


def check_home_assistant_entity(entity_id: str) -> Dict[str, Any]:
    """
    Check if a Home Assistant entity exists and get its current state.

    Synchronous wrapper for the async implementation.

    Args:
        entity_id: The entity ID to check (e.g., 'light.living_room')

    Returns:
        Dictionary with entity information or error details
    """
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_check_home_assistant_entity_async(entity_id))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error in check_home_assistant_entity: {str(e)}")
        return {
            "success": False,
            "status": "runtime_error",
            "error": str(e),
            "entity_id": entity_id,
        }


async def _list_home_assistant_domains_async() -> Dict[str, Any]:
    """
    Async implementation to list all available Home Assistant domains from MCP tools.

    Returns:
        Dictionary with domain information or error details
    """
    # Import here to avoid circular imports
    from radbot.tools.mcp.mcp_tools import _create_home_assistant_toolset_async

    # Initialize the Home Assistant MCP
    ha_tools, exit_stack = await _create_home_assistant_toolset_async()

    if not ha_tools or len(ha_tools) == 0:
        return {
            "success": False,
            "status": "initialization_failed",
            "error": "Failed to create Home Assistant MCP toolset",
            "details": None,
        }

    try:
        # Extract domain information from tool names
        domains = set()

        # Extract domains from tool names
        # Home Assistant MCP tools might use different naming patterns
        for tool in ha_tools:
            if hasattr(tool, "name"):
                tool_name = tool.name

                # Look for traditional pattern: home_assistant_mcp.{domain}.{action}
                parts = tool_name.split(".")
                if len(parts) >= 3 and parts[0] == "home_assistant_mcp":
                    domains.add(parts[1])
                    continue

                # Look for Hass prefix pattern: Hass{Domain}{Action}
                if tool_name.startswith("Hass") and len(tool_name) > 4:
                    # Try to extract the domain from tool description or parameters if available
                    if (
                        hasattr(tool, "description")
                        and isinstance(tool.description, str)
                        and "domain" in tool.description.lower()
                    ):
                        desc = tool.description.lower()
                        domain_start = desc.find("domain:")
                        if domain_start >= 0:
                            domain_end = desc.find(",", domain_start)
                            if domain_end < 0:
                                domain_end = len(desc)
                            domain = desc[domain_start + 7 : domain_end].strip()
                            domains.add(domain)

                    # Extract common domain keywords from the name
                    common_domains = [
                        "light",
                        "switch",
                        "sensor",
                        "climate",
                        "media",
                        "vacuum",
                        "scene",
                        "cover",
                        "fan",
                        "lock",
                        "input",
                    ]

                    for domain in common_domains:
                        if domain.lower() in tool_name.lower():
                            domains.add(domain)
                            break

                # New in ADK 0.4.0: Look for alternative patterns
                common_domains = [
                    "light",
                    "switch",
                    "sensor",
                    "climate",
                    "media_player",
                    "vacuum",
                    "scene",
                    "cover",
                    "fan",
                    "lock",
                    "input_boolean",
                ]

                for domain in common_domains:
                    # Check for patterns like 'LightTurnOn', 'SwitchSetState', etc.
                    domain_pattern = domain.lower()
                    # Special case for media_player which might appear as 'media'
                    if domain == "media_player":
                        domain_pattern = "media"
                    # Special case for input_boolean which might appear as 'input'
                    if domain == "input_boolean":
                        domain_pattern = "input"

                    if domain_pattern in tool_name.lower():
                        # Map back to standard domain names
                        if domain_pattern == "media":
                            domains.add("media_player")
                        elif domain_pattern == "input":
                            domains.add("input_boolean")
                        else:
                            domains.add(domain)
                        break

        return {
            "success": True,
            "status": "domains_listed",
            "domains": sorted(list(domains)),
            "domains_count": len(domains),
        }
    except Exception as e:
        logger.error(f"Error listing Home Assistant domains: {str(e)}")
        return {
            "success": False,
            "status": "listing_error",
            "error": str(e),
            "details": None,
        }
    finally:
        # Clean up resources
        if exit_stack:
            try:
                await exit_stack.aclose()
            except Exception as close_error:
                logger.error(f"Error closing resources: {str(close_error)}")


def list_home_assistant_domains() -> Dict[str, Any]:
    """
    List all available Home Assistant domains from MCP tools.

    Synchronous wrapper for the async implementation.

    Returns:
        Dictionary with domain information or error details
    """
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_list_home_assistant_domains_async())
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error in list_home_assistant_domains: {str(e)}")
        return {
            "success": False,
            "status": "runtime_error",
            "error": str(e),
            "details": None,
        }


async def _find_home_assistant_entities_async(
    search_term: str, domain_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for Home Assistant entities by name or partial match.

    Args:
        search_term: The term to search for in entity IDs
        domain_filter: Optional domain to filter results (e.g., 'light', 'switch')

    Returns:
        Dictionary with entity information or error details
    """
    # Import here to avoid circular imports
    from radbot.tools.mcp.mcp_tools import _create_home_assistant_toolset_async

    # Initialize the Home Assistant MCP
    ha_tools, exit_stack = await _create_home_assistant_toolset_async()

    try:
        if not ha_tools or len(ha_tools) == 0:
            return {
                "success": False,
                "status": "no_tools",
                "error": "No Home Assistant tools available",
                "matches": [],
            }

        # Collect all entity IDs from the available tools
        entity_ids = []

        try:
            # Log all available tools for debugging
            tool_names = []
            for tool in ha_tools:
                if hasattr(tool, "name"):
                    tool_names.append(tool.name)
            logger.info(
                f"Available Home Assistant tools for entity search: {', '.join(tool_names[:10])}..."
            )

            # The ideal approach would be to use a special get_entities tool if available
            get_entities_tool = None

            # Try different tool naming patterns
            for tool in ha_tools:
                if not hasattr(tool, "name"):
                    continue

                tool_name = tool.name
                # Look for entity listing tools with various naming patterns
                if (
                    "get_entities" in tool_name.lower()
                    or "list_entities" in tool_name.lower()
                    or "entities.list" in tool_name.lower()
                    or "entity.list" in tool_name.lower()
                ):
                    get_entities_tool = tool
                    logger.info(f"Found entity listing tool: {tool_name}")
                    break

            # If we found an entity listing tool, try to use it
            if get_entities_tool:
                try:
                    logger.info(
                        f"Calling entity listing tool: {getattr(get_entities_tool, 'name', 'unknown')}"
                    )
                    entities = await get_entities_tool()
                    logger.info(f"Entity listing tool returned: {type(entities)}")

                    if isinstance(entities, list):
                        entity_ids = entities
                        logger.info(f"Found {len(entity_ids)} entities as list")
                    elif isinstance(entities, dict):
                        if "entity_ids" in entities:
                            entity_ids = entities["entity_ids"]
                            logger.info(
                                f"Found {len(entity_ids)} entities in entity_ids key"
                            )
                        elif "entities" in entities:
                            entity_ids = entities["entities"]
                            logger.info(
                                f"Found {len(entity_ids)} entities in entities key"
                            )
                        elif "ids" in entities:
                            entity_ids = entities["ids"]
                            logger.info(f"Found {len(entity_ids)} entities in ids key")
                        else:
                            # Try to extract entity IDs from dict keys
                            possible_entities = [
                                key for key in entities.keys() if "." in key
                            ]
                            if possible_entities:
                                entity_ids = possible_entities
                                logger.info(
                                    f"Extracted {len(entity_ids)} possible entity IDs from dict keys"
                                )
                except Exception as e:
                    logger.warning(f"Error calling get_entities tool: {str(e)}")

            # If we couldn't find entities with the dedicated tool, try to extract from domain tools
            if not entity_ids:
                logger.info(
                    "No entities found with entity listing tool, trying to extract from domains"
                )

                # Try to detect domains like light, switch, etc.
                domains = set()
                domain_tools = {}
                for tool in ha_tools:
                    if not hasattr(tool, "name"):
                        continue

                    tool_name = tool.name.lower()

                    # Extract common domain names from tool names
                    common_domains = [
                        "light",
                        "switch",
                        "climate",
                        "media_player",
                        "cover",
                        "vacuum",
                        "sensor",
                        "binary_sensor",
                        "fan",
                    ]

                    for domain in common_domains:
                        if domain in tool_name:
                            domains.add(domain)

                            # Track tools by domain for later use
                            if domain not in domain_tools:
                                domain_tools[domain] = []
                            domain_tools[domain].append(tool)
                            break

                # If we found domains, try to check if our specific entity exists
                if domains:
                    logger.info(f"Found domains: {', '.join(domains)}")

                    if search_term and "." in search_term:
                        # If the search term is a fully qualified entity_id, check if it exists directly
                        domain, entity_name = search_term.split(".", 1)
                        if domain in domain_tools:
                            # We have tools for this domain, try to build a virtual entity list
                            entity_ids = [f"{domain}.{entity_name}"]
                            logger.info(
                                f"Treating search term as direct entity_id: {search_term}"
                            )
                            logger.info(
                                f"Domain {domain} is supported - adding to virtual entity list"
                            )
                        else:
                            logger.warning(
                                f"Domain {domain} not supported in MCP tools"
                            )
                            # Return an informative error about the specific domain
                            return {
                                "success": False,
                                "status": "unsupported_domain",
                                "error": f"Domain '{domain}' is not supported by the Home Assistant MCP integration",
                                "search_term": search_term,
                                "domain_filter": domain_filter,
                                "supported_domains": list(domains),
                                "match_count": 0,
                                "matches": [],
                            }
                    else:
                        # For search by keyword, create virtual entities for each domain to enable discovery
                        logger.warning(
                            "No entity listing tool available - creating virtual entities for search"
                        )
                        # Using the domains we found, create some placeholder entities that match the search
                        entity_ids = []
                        for domain in domains:
                            # Only create placeholders for the specified domain filter, if provided
                            if domain_filter and domain != domain_filter:
                                continue

                            # Add a placeholder entity that contains the search term for each domain
                            placeholder = f"{domain}.{search_term}"
                            entity_ids.append(placeholder)
                            logger.info(
                                f"Added placeholder entity for search: {placeholder}"
                            )

        except Exception as e:
            logger.warning(f"Error searching for entity tools: {str(e)}")

        # Check if we have entity IDs to work with (either real or virtual)
        if not entity_ids:
            logger.warning("No entity IDs were retrieved from Home Assistant.")
            logger.warning(
                "Make sure Home Assistant MCP server is properly configured."
            )

            # Return an informative error
            return {
                "success": False,
                "status": "no_entities",
                "error": "No entities could be retrieved from Home Assistant MCP server",
                "search_term": search_term,
                "domain_filter": domain_filter,
                "supported_domains": list(domains) if domains else [],
                "match_count": 0,
                "matches": [],
            }

        # Filter entity IDs based on search term and domain filter
        matches = []
        search_parts = search_term.lower().split()

        for entity_id in entity_ids:
            # Apply domain filter if specified
            if domain_filter and not entity_id.startswith(f"{domain_filter}."):
                continue

            # Check if entity matches search term
            entity_lower = entity_id.lower()

            # Score the match based on how many search terms match
            score = 0
            for part in search_parts:
                if part in entity_lower:
                    score += 1

            if score > 0:
                domain, name = (
                    entity_id.split(".", 1)
                    if "." in entity_id
                    else ("unknown", entity_id)
                )
                matches.append(
                    {
                        "entity_id": entity_id,
                        "domain": domain,
                        "name": name,
                        "score": score,
                        "match_level": (
                            "exact" if score == len(search_parts) else "partial"
                        ),
                    }
                )

        # Sort matches by score (highest first)
        matches.sort(key=lambda x: x["score"], reverse=True)

        return {
            "success": True,
            "status": "entities_found" if matches else "no_matches",
            "search_term": search_term,
            "domain_filter": domain_filter,
            "match_count": len(matches),
            "matches": matches[:10],  # Return top 10 matches
        }

    except Exception as e:
        logger.error(f"Error searching Home Assistant entities: {str(e)}")
        return {
            "success": False,
            "status": "search_error",
            "error": str(e),
            "matches": [],
        }
    finally:
        # Clean up resources
        if exit_stack:
            try:
                await exit_stack.aclose()
            except Exception as close_error:
                logger.error(f"Error closing resources: {str(close_error)}")


def find_home_assistant_entities(
    search_term: str, domain_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for Home Assistant entities by name or partial match.

    Synchronous wrapper for the async implementation.

    Args:
        search_term: The term to search for in entity IDs
        domain_filter: Optional domain to filter results (e.g., 'light', 'switch')

    Returns:
        Dictionary with entity information or error details
    """
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            _find_home_assistant_entities_async(search_term, domain_filter)
        )
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error in find_home_assistant_entities: {str(e)}")
        return {
            "success": False,
            "status": "runtime_error",
            "error": str(e),
            "matches": [],
        }


def convert_to_adk_tool(
    function: Callable, name: Optional[str] = None, description: Optional[str] = None
) -> FunctionTool:
    """
    Convert a function to an ADK-compatible FunctionTool.

    This utility helps convert standard functions to ADK-compatible tools
    with appropriate schema information.

    Args:
        function: The function to convert
        name: Optional name for the tool (defaults to function name)
        description: Optional description for the tool

    Returns:
        The converted FunctionTool
    """
    # Get the function name if not provided
    if not name:
        name = function.__name__

    # Get description from docstring if not provided
    if not description and function.__doc__:
        description = function.__doc__.split("\n")[0].strip()
    elif not description:
        description = f"{name} function"

    try:
        # Try to create a tool using ADK 0.3.0+ style
        tool = FunctionTool(
            function=function,
            function_schema={
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        )
        logger.info(f"Created tool {name} using ADK 0.3.0+ style")
    except TypeError:
        # Fall back to older ADK versions
        tool = FunctionTool(
            function,
            {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        )
        logger.info(f"Created tool {name} using legacy FunctionTool style")

    return tool
