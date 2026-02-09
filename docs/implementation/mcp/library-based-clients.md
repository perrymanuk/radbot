# MCP Client Migration Plan

## Current State Analysis

The current MCP client implementation in Radbot (`radbot/tools/mcp/client.py`) is a custom client that attempts to handle various MCP server implementations with different transport methods, endpoint patterns, and response formats. While it includes many resilience features, it has been experiencing connection issues with certain MCP servers.

### Key Challenges with Current Implementation

1. **Complex Error Handling**: The current implementation has numerous fallback mechanisms and error handling paths, making it difficult to maintain and debug.
2. **Custom SSE Handling**: It uses a custom approach to handle SSE connections rather than leveraging established libraries.
3. **Endpoint Discovery Complexity**: Multiple approaches to discover endpoints and parse SSE events add complexity.
4. **Tool Name Mapping**: The tool name mapping is complex and sometimes fails to match the correct tool names.
5. **Session Management**: Session management is inconsistent, especially for SSE connections.
6. **Lack of Standardization**: The implementation tries to accommodate various non-standard behaviors from different MCP servers.

### Current Architecture Overview

The current MCP client architecture consists of:

1. `MCPSSEClient` in `client.py` - Main client implementation with custom SSE handling
2. `MCPClientFactory` in `mcp_client_factory.py` - Factory to create and cache client instances
3. MCP core utilities in `mcp_core.py` for tool creation
4. MCP core utilities in `mcp_core.py` for tool creation and integration with ADK

## Target State: MCP Python SDK Based Client

The example MCP client provided at `/Users/perry.manuk/git/perrymanuk/mcp-client` uses the official MCP Python SDK (`mcp`) and provides a cleaner, more standardized approach to MCP server connections. It offers:

1. **Standard Compliance**: Uses the official MCP Python SDK for SSE connections
2. **Simplified Error Handling**: More straightforward error handling patterns
3. **Clean Session Management**: Proper context management for SSE connections
4. **Robust Tool Handling**: Correctly handles different tool formats from servers
5. **Interactive Mode**: Includes an interactive mode for testing and diagnostics
6. **Authentication Support**: Proper handling of authentication tokens and headers

### Target Architecture Overview

The new architecture will consist of:

1. `MCPSSEClient` in `client.py` - Based on the example implementation
2. `MCPClientFactory` in `mcp_client_factory.py` - Updated to use the new client
3. Unified approach to tool creation and integration in `mcp_core.py`
4. Removal of deprecated server-specific implementations

## Migration Strategy

### Phase 1: Preparation and Infrastructure

1. **Add MCP SDK Dependencies**:
   - Add `mcp` and `httpx` to project dependencies in `pyproject.toml`
   - Update the Makefile to include these dependencies
   
2. **Create Test Environment**:
   - Create minimal test scripts to validate the new client
   - Set up test cases for MCP servers
   - Document test procedures and expected outcomes

3. **Analysis of Integration Points**:
   - Identify all code that depends on the current MCP client implementation
   - Map the current client methods to the new client methods
   - Document the API differences for reference during migration

### Phase 2: Implementation

1. **Replace Core MCP Client** (`client.py`):
   - Replace the current `MCPSSEClient` with the new implementation
   - Adapt the interface to ensure compatibility with existing code
   - Implement any missing methods required for backward compatibility
   
2. **Update Factory** (`mcp_client_factory.py`):
   - Update the `MCPClientFactory` to work with the new client implementation
   - Ensure proper initialization and parameter handling
   - Maintain caching behavior for consistent performance
   
3. **Update Core Integration** (`mcp_core.py`):
   - Update the tool creation logic to work with the new client
   - Ensure compatibility with ADK tool creation
   - Maintain existing pattern for retrieving and using tools

4. **Clean Up Server-Specific Implementations**:
   - Remove or update server-specific implementations if needed
   - Ensure proper deprecation notices for removed functionality
   - Update documentation to reflect changes

### Phase 3: Testing and Validation

1. **Unit Tests**:
   - Update existing unit tests for MCP tools and utilities
   - Add new tests for the new client implementation
   - Ensure test coverage for error cases and edge conditions
   
2. **Integration Tests**:
   - Test with all configured MCP servers
   - Validate tool discovery and invocation
   - Ensure proper error handling and resilience
   
3. **End-to-End Tests**:
   - Test with full agent interactions
   - Validate proper integration with ADK
   - Ensure seamless user experience

### Phase 4: Documentation and Cleanup

1. **Update Documentation**:
   - Document the new MCP client architecture
   - Provide examples for common use cases
   - Update any references to the old implementation
   
2. **Code Cleanup**:
   - Remove deprecated code and commented-out sections
   - Ensure consistent style and naming conventions
   - Add type hints and docstrings for better maintainability
   
3. **Performance Analysis**:
   - Analyze and document performance improvements
   - Identify any potential bottlenecks
   - Recommend further optimizations if needed

## Implementation Details

### Key Files to Update

1. `/radbot/tools/mcp/client.py` - Replace with new implementation
2. `/radbot/tools/mcp/mcp_client_factory.py` - Update to use new client
3. `/radbot/tools/mcp/mcp_core.py` - Update tool creation logic
4. `/radbot/tools/mcp/mcp_tools.py` - Update tool integration

### Dependencies

- MCP Python SDK (`mcp`): Used for SSE connections and client sessions
- HTTPX: Used for improved HTTP interactions over requests
- ADK Tools: Integration with Google ADK for tool creation

### Backward Compatibility Considerations

1. **Method Signatures**: Maintain compatibility with current method signatures
2. **Error Handling**: Ensure consistent error reporting format
3. **Tool Discovery**: Maintain the same approach for tool discovery
4. **Session Management**: Ensure proper session lifecycle management

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Dependency conflicts | Medium | Test in isolated environment before deployment |
| API compatibility issues | High | Implement adapter methods for backward compatibility |
| Performance regression | Medium | Benchmark before and after migration |
| MCP server compatibility | High | Test with all supported MCP servers |
| Integration test failures | Medium | Create detailed test plan with validation steps |

## Timeline

1. **Phase 1 (Preparation)**: 1-2 days
2. **Phase 2 (Implementation)**: 2-3 days
3. **Phase 3 (Testing)**: 2-3 days
4. **Phase 4 (Documentation)**: 1-2 days

Total estimated time: 6-10 days

## Success Criteria

1. All MCP servers successfully connect and discover tools
2. All tool invocations work as expected
3. No performance regression compared to the current implementation
4. Unit and integration tests pass
5. Documentation is updated and accurate
6. Code is clean, well-structured, and maintainable