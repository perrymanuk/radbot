# Library-Based MCP Client Implementation

This document describes the implementation of the MCP client using the official MCP Python SDK.

## Overview

The MCP (Model Context Protocol) client is responsible for connecting to MCP servers, discovering available tools, and invoking those tools on behalf of agents. Our implementation is based on the official MCP Python SDK with specific adaptations for Radbot's needs.

## Key Components

### `MCPSSEClient` Class

Located in `radbot/tools/mcp/client.py`, this class is the primary implementation of the MCP client. It handles:

- Connection establishment with MCP servers
- Session management
- Tool discovery and registration
- Tool invocation
- Server-Sent Events (SSE) handling
- Error management and fallback mechanisms

## Implementation Details

### Initialization Flow

The client initialization follows these steps:

1. Connection to the MCP server's SSE endpoint
2. Extraction of session ID and message endpoint from SSE events
3. Sending a proper initialization request with protocol version, capabilities, and client info
4. Requesting the list of available tools
5. Creating tool objects based on the server's response

### Tool Invocation Process

When a tool is invoked, the following happens:

1. The client formats a proper MCP request with the tool name and arguments
2. The request is sent to the message endpoint with appropriate headers
3. For synchronous responses (200 OK), the result is processed immediately
4. For asynchronous responses (202 Accepted), the client returns an accepted status
5. Results are extracted from the JSON-RPC format and returned

### Tool Discovery and Creation

The client supports several methods of tool discovery:

1. Retrieving tools via the MCP SDK's list_tools method
2. Fetching schema information from various common endpoints
3. Falling back to creating standard tools based on server URL patterns

### Error Handling and Fallbacks

To ensure robustness, the client implements multiple fallback mechanisms:

- If async initialization fails, it falls back to direct HTTP initialization
- If no session ID is provided by the server, it generates a UUID as fallback
- If no message endpoint is discovered, it constructs one based on common patterns
- If tool discovery fails, it can create standard tools for known server types

## Integration with Google ADK

Tools discovered from MCP servers are wrapped as Google ADK `FunctionTool` objects to make them compatible with the ADK framework. The client handles multiple versions of the ADK by adapting to different constructor signatures.

## Memory and Resource Management

The client properly cleans up resources when it's destroyed:

1. Closing the SSE connection by setting an active flag to false
2. Waiting for background threads to finish
3. Closing HTTP sessions
4. Cleaning up async context managers

## Common Challenges and Solutions

### Server-Sent Events Connection

**Challenge**: Some MCP servers would close SSE connections with "BrokenResourceError" when trying to send responses.

**Solution**: Maintain a persistent SSE connection in a background thread, properly parsing and handling all events, and using thread synchronization to wait for responses.

### Protocol Version Compliance

**Challenge**: Different MCP servers expect different initialization sequences.

**Solution**: Implement a standard initialization process using the 2025-03-26 protocol version with full compliant capabilities declaration.

### Tool Response Formats

**Challenge**: Different servers return results in different formats.

**Solution**: Handle multiple response formats including JSON-RPC result objects, custom output fields, and plain text responses.

### Session Management

**Challenge**: Maintaining the session across requests is critical for some MCP servers.

**Solution**: Extract and store session IDs from SSE events, and include them in all requests to maintain session continuity.

## Usage Example

```python
# Create a client
client = MCPSSEClient(url="https://example.com/mcp/sse")

# Initialize the connection
client.initialize()

# Get available tools
tools = client.get_tools()

# Call a tool
result = client._call_tool("search", {"query": "What is the capital of France?"})
```

## Future Improvements

- Add support for authentication tokens and custom headers
- Implement caching of tool responses for better performance
- Add retry mechanisms for failed requests
- Support more complex tool schemas and parameter validation
- Add telemetry for monitoring and debugging
EOF < /dev/null