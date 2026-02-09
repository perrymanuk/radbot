# Claude CLI MCP Server Integration Design

## Overview

This document outlines the design for integrating the Claude CLI's MCP server capabilities with the Radbot framework, following our established MCP client infrastructure pattern.

## Architecture

The integration will leverage our existing MCP client infrastructure, particularly the `MCPSSEClient` class that already handles:

1. Multiple transport methods (SSE, HTTP)
2. Dynamic endpoint discovery
3. Robust error handling
4. Session management for persistent connections

### Key Components

1. **Configuration in config.yaml**
   - Define a new MCP server entry for Claude CLI
   - Specify connection parameters 

2. **MCP Client Factory Integration**
   - Add the Claude CLI server to the available MCP servers
   - Use our existing `MCPClientFactory` for client instance management

3. **Claude-specific Tools**
   - Create a dedicated set of ADK tools that encapsulate Claude CLI capabilities
   - Focus on the Bash/command execution capabilities initially
   - Structure similar to other MCP tool integrations

4. **Command Execution Security**
   - Implement request validation and sanitization
   - Add robust error handling for command execution

### Implementation Strategy

Rather than creating a completely new client, we'll:

1. Add a configuration entry for the Claude CLI MCP server
2. Register it in the MCP client factory
3. Create a specialized tool set for Claude CLI capabilities
4. Focus primarily on the command execution functionality

This approach maximizes code reuse and maintains consistency with our other MCP integrations.

## Configuration Schema

```yaml
integrations:
  mcp:
    servers:
      - id: claude-cli
        enabled: true
        transport: stdio
        command: claude
        args: ["mcp", "serve"]
        working_directory: /path/to/working/dir
        timeout: 30
```

## Usage Examples

```python
# Example 1: Direct command execution
result = agent.execute_tool("claude_execute_command", command="ls -la")

# Example 2: Integration with shell tools
shell_command = ShellCommand(
    command="git status",
    executor="claude-cli"  # Use Claude CLI as the executor
)
result = shell_command.execute()
```

## Security Considerations

1. Input validation for all commands
2. Working directory restrictions
3. Command allowlisting/denylisting
4. Proper error handling and reporting
5. Timeout enforcement

## Implementation Phases

1. Server configuration and client factory integration
2. Basic command execution tool
3. File operation tools (Read, Write)
4. Advanced tools (WebFetch, etc.)
5. Security enhancements and validation