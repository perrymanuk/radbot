# MCP-Proxy Integration

This document describes the integration between Radbot and [MCP-Proxy](https://github.com/TBXark/mcp-proxy), a versatile proxy server that aggregates multiple Model Context Protocol (MCP) servers into a single access point.

## Overview

The MCP-Proxy integration allows Radbot to access multiple specialized MCP servers through a single proxy server deployed at `https://mcp-proxy.demonsafe.com`. This integration enables access to a variety of AI tools including:

- Firecrawl (web crawling and content extraction)
- Tavily (search and research)
- Context7 (library documentation tools)
- WebResearch (web browsing and research)
- Nomad integration (if needed)

## Architecture

The integration uses Radbot's standard MCP client architecture:

1. Each proxy-accessible service is configured as a separate MCP server in the config.yaml
2. All connections use the SSE (Server-Sent Events) transport protocol
3. The standard `MCPSSEClient` class from `radbot.tools.mcp.client` is used for all connections
4. The `MCPClientFactory` creates and manages client connections as needed

## Configuration

The proxy integration is configured in the main `config.yaml` file. A template configuration can be found in `config/mcp_proxy.yaml.example`.

Example configuration for a single proxy service:

```yaml
integrations:
  mcp:
    enabled: true
    servers:
      - id: firecrawl-proxy
        enabled: true
        transport: sse
        url: https://mcp-proxy.demonsafe.com/mcp-server-firecrawl/sse
        description: "Firecrawl web crawling and extraction tools"
        # Optional auth token if required
        # auth_token: "your_auth_token_here"
```

### Configuration Parameters

For each proxy service:

- `id`: A unique identifier for the service in Radbot
- `enabled`: Whether this service is active
- `transport`: Always `sse` for proxy services
- `url`: The proxy URL with the pattern `https://mcp-proxy.demonsafe.com/{service-name}/sse`
- `description`: Optional description of the service
- `auth_token`: Optional authentication token if required by the proxy

## Usage

### Accessing Tools

Once configured, tools from each proxy service become available through the standard Radbot tool access mechanisms:

```python
from radbot.tools.mcp.mcp_client_factory import MCPClientFactory

# Get a client for the firecrawl proxy service
firecrawl_client = MCPClientFactory.get_client("firecrawl-proxy")

# Call a tool provided by the service
result = firecrawl_client.call_tool("crawl", {"url": "https://example.com", "depth": 1})
```

### Available Services and Tools

The proxy provides access to the following services and their respective tools:

1. **Firecrawl** (`mcp-server-firecrawl`):
   - `firecrawl_scrape`: Extract content from a web page
   - `firecrawl_map`: Discover URLs from a starting point
   - `firecrawl_crawl`: Crawl multiple pages from a starting URL
   - `firecrawl_search`: Search and retrieve content from web pages
   - And other tools for web content extraction

2. **Context7** (`context7`):
   - `resolve-library-id`: Resolve package names to library IDs
   - `get-library-docs`: Fetch documentation for libraries

4. **WebResearch** (`webresearch`):
   - `search_google`: Perform Google searches
   - `visit_page`: Visit and extract content from web pages
   - `take_screenshot`: Capture screenshots of pages

5. **Nomad** (`mcp_nomad`) (if needed):
   - Various tools for Nomad job management

## Implementation Notes

- No custom client implementation is needed as the standard `MCPSSEClient` fully supports the proxy's connection pattern
- The proxy handles the transport layer between Radbot and the underlying MCP services
- Authentication, if required, is passed via the standard `auth_token` parameter
- Tool capabilities are discovered automatically during client initialization

## Troubleshooting

Common issues:

1. **Connection Failures**: Verify the proxy service is running and accessible from your network
2. **Authentication Errors**: Check if an auth token is required and properly configured
3. **Tool Not Found**: Ensure the tool exists in the proxy service by running a tool discovery
4. **Timeout Issues**: The proxy or underlying service may be experiencing high load

## References

- [TBXark/mcp-proxy GitHub Repository](https://github.com/TBXark/mcp-proxy)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification/2025-03-26)