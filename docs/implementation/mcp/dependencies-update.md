# MCP Dependencies Update

To implement the standardized MCP client based on the official MCP Python SDK, we need to update the project dependencies. Here's the proposed change to the `pyproject.toml` file:

```toml
# Current dependency
dependencies = [
    # ... existing dependencies
    "modelcontextprotocol>=0.1.0",
    # ... other dependencies
]

# Updated dependencies
dependencies = [
    # ... existing dependencies
    "mcp>=0.2.0",        # Official MCP Python SDK
    "httpx>=0.27.0",     # Required for MCP client
    # ... other dependencies
]
```

## Changes Explained

1. **Replace `modelcontextprotocol` with `mcp`**: 
   - The `modelcontextprotocol` package is a deprecated name for what is now the `mcp` package
   - The official MCP Python SDK is now published as `mcp` on PyPI

2. **Ensure `httpx` dependency**:
   - The MCP Python SDK requires `httpx` for HTTP client functionality
   - Our project already includes this dependency, but we're emphasizing it here

## Installation

To update the dependencies without disrupting the existing environment, use the following command:

```bash
uv pip install mcp httpx
```

This will install the necessary packages for development and testing purposes. Once the implementation is complete and tested, the `pyproject.toml` file should be updated to reflect these dependencies.

## Compatibility

The MCP Python SDK (`mcp` package) is compatible with our current implementation. It provides:

1. Clean SSE client implementation
2. Standardized client sessions
3. Tool invocation pattern matching the MCP specification

By using the official SDK, we'll benefit from community maintenance, standards compliance, and improved reliability.

## Testing

After installation, run the test scripts to validate the new dependencies:

```bash
# Test the updated client
python tools/test_mcp_standard_client.py
```

These tests will verify that the dependencies are correctly installed and functioning.