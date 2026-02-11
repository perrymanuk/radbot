"""
Factory for creating MCP clients based on configuration.
"""

import importlib
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from radbot.config.config_loader import config_loader

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Exception raised for MCP client initialization errors."""

    pass


class MCPClientFactory:
    """
    Factory for creating MCP clients based on configuration.
    """

    _client_cache: Dict[str, Any] = {}

    @classmethod
    def get_client(cls, server_id: str) -> Any:
        """
        Get or create an MCP client for the given server ID.

        Args:
            server_id: The ID of the MCP server

        Returns:
            MCP client instance

        Raises:
            MCPClientError: If the server is not configured or client creation fails
        """
        # Check if client is already cached
        if server_id in cls._client_cache:
            return cls._client_cache[server_id]

        # Get server configuration
        server_config = config_loader.get_mcp_server(server_id)
        if not server_config:
            raise MCPClientError(f"MCP server '{server_id}' not found in configuration")

        # Check if server is enabled
        if not server_config.get("enabled", True):
            raise MCPClientError(f"MCP server '{server_id}' is disabled")

        # Create and cache the client
        client = cls.create_client(server_config)
        cls._client_cache[server_id] = client
        return client

    @classmethod
    def create_client(cls, server_config: Dict[str, Any]) -> Any:
        """
        Create an MCP client for the given server configuration.

        Args:
            server_config: Dictionary containing the MCP server configuration

        Returns:
            MCP client instance

        Raises:
            MCPClientError: If client creation fails
        """
        try:
            # Get required configuration values
            server_id = server_config.get("id")
            transport = server_config.get("transport", "sse")

            # Handle different transport types
            if transport == "stdio":
                # Special handling for stdio transport (e.g., Claude CLI)
                command = server_config.get("command")
                if not command:
                    raise MCPClientError(
                        f"No command specified for stdio transport in server {server_id}"
                    )

                # Use direct Claude CLI client instead of stdio client
                try:
                    # First try to import our direct implementation
                    from radbot.tools.mcp.direct_claude_cli import DirectClaudeCLIClient

                    client_class = DirectClaudeCLIClient
                    logger.info(f"Using DirectClaudeCLIClient for server: {server_id}")
                except ImportError:
                    # Fall back to the stdio client
                    from radbot.tools.mcp.mcp_stdio_client import MCPStdioClient

                    client_class = MCPStdioClient
                    logger.warning(
                        f"DirectClaudeCLIClient not available, falling back to MCPStdioClient for server: {server_id}"
                    )

                # Prepare client initialization arguments for stdio
                client_args = {
                    "command": command,
                    "args": server_config.get("args"),
                    "working_directory": server_config.get("working_directory"),
                }

                # Add timeout if specified
                if server_config.get("timeout"):
                    client_args["timeout"] = server_config.get("timeout")

                # Add environment variables if specified
                if server_config.get("env"):
                    client_args["env"] = server_config.get("env")

            elif transport in ["sse", "http"]:
                # Our standard client supports both SSE and HTTP
                url = server_config.get("url")
                if not url:
                    raise MCPClientError(
                        f"No URL specified for {transport} transport in server {server_id}"
                    )

                from radbot.tools.mcp.client import MCPSSEClient

                client_class = MCPSSEClient
                logger.info(
                    f"Using standard MCP client for server: {server_id} with transport: {transport}"
                )

                # Prepare client initialization arguments for HTTP/SSE
                client_args = {"url": url}

                # Add message_endpoint if specified
                if server_config.get("message_endpoint"):
                    client_args["message_endpoint"] = server_config.get(
                        "message_endpoint"
                    )

                # Add initialization_delay if specified
                if server_config.get("initialization_delay"):
                    client_args["initialization_delay"] = server_config.get(
                        "initialization_delay"
                    )

                # Handle authentication
                auth_type = server_config.get("auth_type", "token")
                if auth_type == "token" and server_config.get("auth_token"):
                    client_args["auth_token"] = server_config.get("auth_token")
                elif auth_type == "basic":
                    if server_config.get("username") and server_config.get("password"):
                        client_args["username"] = server_config.get("username")
                        client_args["password"] = server_config.get("password")
                    else:
                        logger.warning(
                            f"Basic auth configured for {server_id} but username/password not provided"
                        )

                # Add custom headers if specified
                if server_config.get("headers"):
                    client_args["headers"] = server_config.get("headers")

            elif transport == "websocket":
                # WebSocket transport requires a different client
                url = server_config.get("url")
                if not url:
                    raise MCPClientError(
                        f"No URL specified for websocket transport in server {server_id}"
                    )

                try:
                    from mcp.client import WebSocketClient

                    client_class = WebSocketClient
                    logger.info(
                        f"Using MCP SDK WebSocketClient for server: {server_id}"
                    )
                except ImportError:
                    # Fall back to our standard client if MCP SDK not available
                    from radbot.tools.mcp.client import MCPSSEClient

                    client_class = MCPSSEClient
                    logger.warning(
                        f"MCP SDK WebSocketClient not available, falling back to standard client for server: {server_id}"
                    )

                client_args = {"url": url}
            else:
                raise MCPClientError(f"Unsupported transport: {transport}")

            # Add timeout if specified (common for all transports)
            if server_config.get("timeout") and "timeout" not in client_args:
                client_args["timeout"] = server_config.get("timeout")

            # Handle special flags for specific client types
            is_async_client = client_args.pop("is_async_client", False)

            # Create the client
            client = client_class(**client_args)
            logger.info(f"Created MCP client for server: {server_id}")

            # Initialize the client if it has an initialize method
            if hasattr(client, "initialize") and callable(client.initialize):
                if is_async_client:
                    # For async clients, we won't call initialize() here
                    # Instead we'll return an "uninitialized" client that will be initialized on first use
                    logger.info(
                        f"Async client for server {server_id} will be initialized on first use"
                    )
                    # Mark the client as uninitialized so consumers know to initialize it
                    client._initialized = False
                else:
                    # For standard clients, initialize normally
                    success = client.initialize()
                    if success:
                        logger.info(f"Initialized MCP client for server: {server_id}")
                    else:
                        logger.warning(
                            f"Failed to initialize MCP client for server: {server_id}"
                        )

            return client

        except Exception as e:
            error_msg = f"Failed to create MCP client: {str(e)}"
            logger.error(error_msg)
            raise MCPClientError(error_msg) from e

    @classmethod
    def clear_cache(cls) -> None:
        """
        Clear the client cache.
        """
        # Stop each client before clearing the cache
        for client_id, client in cls._client_cache.items():
            try:
                if hasattr(client, "stop") and callable(client.stop):
                    client.stop()
            except Exception as e:
                logger.warning(f"Error stopping client {client_id}: {e}")

        cls._client_cache.clear()

    @classmethod
    def get_all_enabled_clients(cls) -> Dict[str, Any]:
        """
        Get all enabled MCP clients.

        Returns:
            Dictionary mapping server IDs to client instances
        """
        clients = {}
        for server in config_loader.get_enabled_mcp_servers():
            server_id = server.get("id")
            try:
                clients[server_id] = cls.get_client(server_id)
            except MCPClientError as e:
                logger.warning(f"Failed to initialize MCP client for {server_id}: {e}")
        return clients
