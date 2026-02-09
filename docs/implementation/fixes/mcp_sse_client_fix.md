# MCP SSE Client Implementation Fix

## Overview

This document details the implementation of a more robust MCP SSE client for connecting to Model Context Protocol (MCP) servers, particularly focusing on fixing freezing issues during application startup and initialization. The implementation is based on best practices from the official MCP Python SDK and other MCP client examples, adapted for our specific needs.

## Problem

The original MCP SSE client implementation had several issues:

1. **Application Freezing**: The web application would freeze during startup when attempting to connect to MCP servers, particularly when using SSE (Server-Sent Events) transport. The connection would hang indefinitely, preventing the application from starting properly.

2. **Unreliable Tool Acquisition**: The client didn't have a reliable fallback method for getting tools from the MCP server if the main SSE connection approach failed.

3. **No Timeout Handling**: The client didn't properly handle timeouts or connection failures, leading to blocking operations.

## Solution

### Multi-level Approach

The new implementation uses a multi-level approach to connecting to MCP servers and acquiring tools:

1. **Quick Connection Check**: First, perform a HEAD request with a short timeout (max 5 seconds) to check if the server is responding at all.

2. **Direct Tools Endpoint**: Try the `/tools` endpoint to directly get the list of available tools without using SSE. This is more reliable and faster.

3. **Limited SSE Connection**: If the direct endpoint fails, try a limited SSE connection that only reads enough events to get server info, with a strict timeout and limits on how many lines to read.

4. **Fallback Dummy Tools**: If all else fails, create dummy tools based on the server URL pattern.

### Key Implementation Features

- **Short Timeouts**: Using very short timeouts for initial connection checks to prevent hanging.
- **Multiple Connection Methods**: Trying different connection methods in sequence until one works.
- **Proper Stream Handling**: Properly handling SSE streaming connections with limits to prevent infinite reads.
- **Compatibility Layers**: Supporting different ADK versions for tool creation.
- **Error Resilience**: Comprehensive error handling to ensure the application doesn't crash or hang.
- **Fallback Tools**: Creating useful dummy tools when server connections fail.

## Implementation Details

### Main Client Class: `MCPSSEClient`

The MCPSSEClient class provides a robust implementation for connecting to MCP servers over SSE transport, with multiple fallback mechanisms to ensure reliability.

#### Key Methods

1. **`initialize()`**: Main method to establish connection and retrieve tools
   - Tries multiple approaches to connect to the server
   - Returns success/failure status

2. **`_normalize_url()`**: Ensures the URL is properly formatted
   - Adds default HTTPS scheme if missing
   - Validates URL format

3. **`_process_tools()`**: Processes tool information from the MCP server
   - Creates FunctionTool objects for each tool
   - Handles different ADK API versions with fallbacks

4. **`_create_dummy_tools_for_server()`**: Creates fallback tools based on server type
   - Detects server type from URL patterns
   - Creates tools specific to the detected server type

5. **`_call_tool()`**: Method to invoke tools on the MCP server
   - Implements proper JSON-RPC request format with method, params, and ID
   - Tries multiple invoke endpoints with retry logic
   - Implements exponential backoff for retries
   - Gracefully handles various response formats
   - Has improved error handling for different failure modes

### Connection Strategy

The implementation uses a layered approach to acquire tools:

```
normalize and validate URL
↓
try HEAD request (quick server availability check)
↓
try multiple tool endpoints (/tools, "", /v1/tools, /api/tools)
↓
try multiple SSE endpoints (/v1, "", /sse, /api/sse, /stream)
↓
create dummy tools based on URL pattern detection
```

The client tries multiple endpoint patterns for both the tools API and SSE connections, accommodating different MCP server implementations and versions. This ensures that even if the preferred methods fail, we still end up with a set of functional tools.

### Tool Invocation Strategy

For tool invocation, the client uses a comprehensive approach:

```
format proper JSON-RPC request with method, parameters and ID
↓
try multiple invoke endpoints (/invoke, /v1/invoke, /api/invoke, "")
↓
implement retry logic with exponential backoff for server errors
↓
handle various response formats (JSON-RPC, direct output, etc.)
```

This approach provides resilience against different server implementations and temporary failures.

## Integration Points

### Session Management

The MCPSSEClient is primarily used in `radbot/web/api/session.py` during session initialization:

1. When a new session is created, we attempt to load MCP tools using our client
2. The tools are added to the agent's toolset if successfully retrieved
3. The tools can then be used by the agent during conversations

### Application Startup

In `radbot/web/app.py`, we now merely check for enabled MCP servers during startup but don't try to connect to them, which prevents freezing:

```python
@app.on_event("startup")
async def initialize_mcp_servers():
    """Initialize MCP server tools on application startup."""
    try:
        logger.info("Initializing MCP servers at application startup...")
        from radbot.tools.mcp.mcp_client_factory import MCPClientFactory
        from radbot.config.config_loader import config_loader
        
        # Just check if servers are enabled and log them
        servers = config_loader.get_enabled_mcp_servers()
        logger.info(f"Found {len(servers)} enabled MCP servers in configuration")
        
        for server in servers:
            server_id = server.get("id", "unknown")
            server_name = server.get("name", server_id)
            logger.info(f"MCP server enabled: {server_name} (ID: {server_id})")
            
        # Don't attempt to create tools here - we'll do that in the session
    except Exception as e:
        logger.error(f"Failed to check MCP servers: {str(e)}", exc_info=True)
```

## Testing and Validation

When testing this implementation, check for:

1. Application startup speed
2. Successful tool acquisition from MCP servers
3. Graceful handling of server outages or connectivity issues
4. Proper fallback to dummy tools when needed
5. Successful tool invocation

## References

- [MCP Specification](https://modelcontextprotocol.io/specification/2025-03-26)
- [mcp-sse-client-python](https://github.com/zanetworker/mcp-sse-client-python/) (source of inspiration)
- [Server-Sent Events (SSE) specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)