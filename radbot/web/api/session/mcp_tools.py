"""
MCP tools utilities for RadBot web interface.

This module provides utilities for loading MCP tools.
"""

import logging
from typing import Any, List

# Set up logging
logger = logging.getLogger(__name__)


def _try_load_mcp_tools(self):
    """Try to load and add MCP tools to the root agent."""
    try:
        # Import necessary modules
        from google.adk.tools import FunctionTool

        from radbot.config.config_loader import config_loader
        from radbot.tools.mcp.mcp_client_factory import MCPClientFactory

        # Get enabled MCP servers
        servers = config_loader.get_enabled_mcp_servers()
        if not servers:
            logger.debug("No enabled MCP servers found in configuration")
            return

        logger.debug(f"Loading tools from {len(servers)} MCP servers")

        # Initialize clients and collect tools
        tools_to_add = []
        existing_tool_names = set()

        # Get existing tool names
        if hasattr(root_agent, "tools"):
            for tool in root_agent.tools:
                if hasattr(tool, "name"):
                    existing_tool_names.add(tool.name)
                elif hasattr(tool, "__name__"):
                    existing_tool_names.add(tool.__name__)

        # Go through each server and directly initialize the client
        for server in servers:
            server_id = server.get("id")
            server_name = server.get("name", server_id)

            try:
                # Create a client directly instead of using factory
                transport = server.get("transport", "sse")
                url = server.get("url")
                auth_token = server.get("auth_token")

                # Handle different transport types
                if transport == "sse":
                    # Use our custom SSE client implementation
                    from radbot.tools.mcp.client import MCPSSEClient

                    client = MCPSSEClient(url=url, auth_token=auth_token)

                    # Initialize the client (this is synchronous and safe)
                    if client.initialize():
                        # Get tools from the client
                        server_tools = client.tools

                        if server_tools:
                            logger.debug(
                                f"Successfully loaded {len(server_tools)} tools from {server_name}"
                            )

                            # Add unique tools
                            for tool in server_tools:
                                tool_name = getattr(tool, "name", None) or getattr(
                                    tool, "__name__", str(tool)
                                )
                                if tool_name not in existing_tool_names:
                                    tools_to_add.append(tool)
                                    existing_tool_names.add(tool_name)
                                    logger.debug(
                                        f"Added tool: {tool_name} from {server_name}"
                                    )
                    else:
                        logger.warning(
                            f"Failed to initialize MCP client for {server_name}"
                        )

                elif transport == "stdio":
                    # For Claude CLI, use the simplified prompt tool implementation
                    try:
                        from radbot.tools.claude_prompt import (
                            create_claude_prompt_tool,
                        )

                        # Get the Claude prompt tool
                        claude_prompt_tool = create_claude_prompt_tool()

                        if claude_prompt_tool:
                            logger.debug(f"Successfully loaded Claude prompt tool")

                            # Get the tool name - use multiple approaches to be robust
                            tool_name = None
                            # Try to get name attribute
                            if hasattr(claude_prompt_tool, "name"):
                                tool_name = claude_prompt_tool.name
                            # Try to get __name__ attribute
                            elif hasattr(claude_prompt_tool, "__name__"):
                                tool_name = claude_prompt_tool.__name__
                            # Try to get name from _get_declaration().name
                            elif hasattr(claude_prompt_tool, "_get_declaration"):
                                try:
                                    declaration = claude_prompt_tool._get_declaration()
                                    if hasattr(declaration, "name"):
                                        tool_name = declaration.name
                                except:
                                    pass
                            # Fallback to string representation
                            if not tool_name:
                                tool_name = str(claude_prompt_tool)

                            # Add if not already present
                            if tool_name not in existing_tool_names:
                                tools_to_add.append(claude_prompt_tool)
                                existing_tool_names.add(tool_name)
                                logger.info(
                                    f"Added tool: {tool_name} from {server_name}"
                                )

                            # Successfully loaded prompt tool, no need to try other methods
                            continue
                        else:
                            logger.warning(f"Failed to create Claude prompt tool")
                    except Exception as e:
                        logger.warning(f"Error loading Claude prompt tool: {e}")
                else:
                    logger.warning(
                        f"Unsupported transport '{transport}' for MCP server {server_name}"
                    )

            except Exception as e:
                logger.warning(
                    f"Error loading tools from MCP server {server_name}: {str(e)}"
                )

        # Add all collected tools to the agent
        if tools_to_add and hasattr(root_agent, "tools"):
            root_agent.tools = list(root_agent.tools) + tools_to_add
            logger.info(f"Added {len(tools_to_add)} total MCP tools to agent")

    except Exception as e:
        logger.warning(f"Error loading MCP tools: {str(e)}")
