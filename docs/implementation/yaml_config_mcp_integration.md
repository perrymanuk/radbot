# YAML Configuration with MCP Integration

<!-- Version: 1.0.0 | Last Updated: 2025-05-07 -->

## Overview

This document outlines the implementation of a YAML-based configuration system for radbot, with specific focus on supporting Model Context Protocol (MCP) server endpoints. This enhancement transitions the project from environment variables in `.env` files to a more structured, hierarchical configuration using `config.yaml`.

The implementation is now complete and integrated into the codebase. This document serves as both a design reference and implementation guide.

## Goals

1. Create a structured, maintainable configuration system
2. Support dynamic configuration of multiple MCP server endpoints
3. Maintain backward compatibility with existing environment variables
4. Improve security through secrets management
5. Enable validation of configuration values

## Architecture

### Configuration Structure

The configuration system will use a hierarchical YAML structure with the following top-level sections:

```yaml
# config.yaml
---
agent:
  # Core agent configuration
  
cache:
  # Cache system configuration
  
integrations:
  # External service integrations
  
  mcp:
    # MCP server configurations
```

### MCP Server Configuration

The MCP configuration will reside in the `integrations.mcp` section and support multiple server endpoints:

```yaml
integrations:
  mcp:
    servers:
      - id: "example-mcp"         # Unique identifier for this MCP server
        name: "Example Server"   # Human-readable name
        enabled: true            # Whether this server is active
        transport: "sse"         # Transport protocol (sse, websocket, etc.)
        url: "http://localhost:11235/mcp/sse"  # Server endpoint URL
        auth_token: "${MCP_TOKEN}"             # Optional authentication token (from env var)

      - id: "another-mcp"        # Another MCP server configuration
        name: "Another Server"
        enabled: false           # This server is disabled
        transport: "sse"
        url: "http://localhost:11236/mcp/sse"
        auth_token: "${ANOTHER_TOKEN}"
```

### Environment Variable Interpolation

The configuration system will support environment variable interpolation using the `${ENV_VAR}` syntax. This allows sensitive information like authentication tokens to remain in environment variables while referenced in the configuration.

### Configuration Loading

1. Look for `config.yaml` in the following locations (in order):
   - Path specified by `RADBOT_CONFIG` environment variable
   - Current working directory
   - User's config directory (e.g., `~/.config/radbot/`)
   - Project root directory

2. Load the YAML file and perform environment variable interpolation

3. Validate the configuration against a schema

4. Make the configuration available through a singleton `ConfigLoader` class

## Implementation Components

### 1. ConfigLoader Class

```python
class ConfigLoader:
    """
    Loads and manages YAML configuration with environment variable interpolation.
    """
    
    def __init__(self, config_path=None):
        """
        Initialize the configuration loader.
        
        Args:
            config_path: Optional explicit path to config.yaml
        """
        
    def get_mcp_servers(self):
        """
        Get all configured MCP servers.
        
        Returns:
            List of MCPServerConfig objects
        """
    
    def get_mcp_server(self, server_id):
        """
        Get a specific MCP server by ID.
        
        Args:
            server_id: The ID of the MCP server
            
        Returns:
            MCPServerConfig object or None if not found
        """
    
    def is_mcp_server_enabled(self, server_id):
        """
        Check if a specific MCP server is enabled.
        
        Args:
            server_id: The ID of the MCP server
            
        Returns:
            Boolean indicating if the server is enabled
        """
```

### 2. Configuration Models

```python
class MCPServerConfig(BaseModel):
    """
    Configuration for an MCP server endpoint.
    """
    id: str
    name: str
    enabled: bool = True
    transport: str = "sse"
    url: str
    auth_token: Optional[str] = None
    timeout: int = 30
    
    # Validators for URL format and transport types
```

### 3. MCP Client Factory

```python
class MCPClientFactory:
    """
    Factory for creating MCP clients based on configuration.
    """
    
    @classmethod
    def create_client(cls, server_config):
        """
        Create an MCP client for the given server configuration.
        
        Args:
            server_config: MCPServerConfig object
            
        Returns:
            MCPClient instance
        """
```

## Security Considerations

1. **Sensitive Data**: Authentication tokens, passwords, and other sensitive information should use environment variable interpolation (`${ENV_VAR}`) rather than being directly included in the YAML file.

2. **Config File Permissions**: The configuration file should have restricted permissions (600 or similar) to prevent unauthorized access.

3. **Validation**: All configuration values should be validated to prevent injection attacks and ensure correct operation.

## Migration Path

To support a smooth transition from the current environment-based configuration to YAML:

1. Create a migration script that converts `.env` files to `config.yaml`

2. Update existing code to use the new ConfigLoader, but maintain backward compatibility by falling back to environment variables when specific config sections are missing

3. Add examples and documentation to help users update their configurations

## Examples

### Basic Configuration File

```yaml
# config.yaml
---
agent:
  main_model: "gemini-2.5-pro"
  sub_agent_model: "gemini-2.0-flash"
  use_vertex_ai: false
  
cache:
  enabled: true
  ttl: 3600
  
integrations:
  home_assistant:
    enabled: true
    url: "https://home-assistant.local:8123"
    token: "${HA_TOKEN}"
    
  mcp:
    servers:
      - id: "example-mcp"
        name: "Example MCP Server"
        enabled: true
        transport: "sse"
        url: "http://localhost:11235/mcp/sse"
```

### Accessing MCP Configuration in Code

```python
from radbot.config import config_loader

# Get all enabled MCP servers
mcp_servers = [s for s in config_loader.get_mcp_servers() if s.enabled]

# Initialize each MCP client
for server in mcp_servers:
    try:
        client = MCPClientFactory.create_client(server)
        print(f"Initialized MCP client for {server.name}")
    except Exception as e:
        print(f"Failed to initialize MCP client for {server.name}: {e}")
```

## Future Enhancements

1. **Schema Validation**: Add JSON Schema validation for the configuration file

2. **Dynamic Reloading**: Support dynamic reloading of configuration without restarting the application

3. **Web Interface**: Provide a web interface for editing configuration settings

4. **Profiles**: Support different configuration profiles for development, testing, and production

## Implementation Status

The YAML configuration system has been fully implemented and integrated into the codebase. The following components have been created:

1. **ConfigLoader**: Implemented in `radbot/config/config_loader.py`
2. **JSON Schema**: Created in `radbot/config/schema/config_schema.json`
3. **Example Configuration**: Added in `examples/config.yaml.example`
4. **Migration Script**: Created in `tools/migrate_env_to_yaml.py`
5. **MCP Client Factory**: Implemented in `radbot/tools/mcp/mcp_client_factory.py`
6. **MCP Tools Integration**: Updated in `radbot/tools/mcp/mcp_tools.py`
7. **MCP Integrations**: Updated to use the new configuration system

### Implementation Details

#### 1. ConfigLoader

The `ConfigLoader` class is implemented as a singleton that handles:
- Finding the configuration file in various locations
- Loading and parsing the YAML
- Interpolating environment variables
- Validating against a JSON schema
- Providing access to various configuration sections

The ConfigLoader also handles Vertex AI settings for Google's GenAI client:
- `use_vertex_ai` - Boolean to enable Vertex AI mode
- `vertex_project` - Google Cloud project ID for Vertex AI
- `vertex_location` - Google Cloud location for Vertex AI (defaults to "us-central1")

#### 2. MCP Client Factory

The `MCPClientFactory` class provides:
- A factory pattern for creating MCP clients based on configuration
- Client caching to avoid redundant client creation
- Support for different transport types (SSE, WebSocket)
- Error handling for client creation failures

#### 3. MCP Tools Integration

The MCP tools system has been updated to:
- Use the new `ConfigLoader` for configuration
- Use the `MCPClientFactory` to create clients
- Fall back to environment variables when needed
- Provide backward compatibility with existing code

### Testing

A test script has been created at `tools/test_mcp_config.py` to verify the implementation. This script tests:
- Loading the configuration
- Creating MCP clients using the factory
- Getting available MCP tools

## Future Enhancements

1. **Schema Validation**: ✅ Implemented with JSON Schema
2. **Vertex AI Configuration**: ✅ Added support for Vertex AI configuration
3. **Dynamic Reloading**: Support dynamic reloading of configuration without restarting the application
4. **Web Interface**: Provide a web interface for editing configuration settings
5. **Profiles**: Support different configuration profiles for development, testing, and production