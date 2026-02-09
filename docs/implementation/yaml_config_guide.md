# YAML Configuration Guide

<!-- Version: 1.0.0 | Last Updated: 2025-05-07 -->

This guide provides instructions for using the YAML-based configuration system in RadBot.

## Overview

RadBot now uses a YAML-based configuration system that replaces environment variables in `.env` files. This provides several advantages:

1. Structured, hierarchical configuration
2. Support for multiple integrations and services
3. Validation of configuration values
4. Better security through environment variable interpolation
5. Centralized configuration management

## Configuration File Location

The `config.yaml` file is searched for in the following locations (in order):

1. Path specified by the `RADBOT_CONFIG` environment variable
2. Current working directory
3. User's config directory (`~/.config/radbot/`)
4. Project root directory

## Basic Configuration Structure

```yaml
# config.yaml
agent:
  main_model: "gemini-2.5-pro"
  sub_agent_model: "gemini-2.0-flash"
  use_vertex_ai: false
  
cache:
  enabled: true
  ttl: 3600
  
api_keys:
  google: "${GOOGLE_API_KEY}"

integrations:
  home_assistant:
    enabled: true
    url: "http://192.168.1.100:8123"
    token: "${HA_TOKEN}"

  calendar:
    enabled: true
    service_account_file: "radbot/tools/calendar/credentials/service-account.json"
    calendar_id: "your-calendar-id@gmail.com"

  mcp:
    servers:
      - id: "example-mcp"
        name: "Example MCP Server"
        enabled: true
        transport: "sse"
        url: "https://example.com/mcp/sse"
        auth_token: "${MCP_TOKEN}"
```

## Environment Variable Interpolation

For sensitive information like API keys and tokens, you can use environment variable interpolation with the `${ENV_VAR}` syntax. This allows you to keep sensitive data in environment variables while referencing them in the configuration file.

Example:
```yaml
api_keys:
  google: "${GOOGLE_API_KEY}"
  
integrations:
  home_assistant:
    token: "${HA_TOKEN}"
```

## Google API Configuration

The configuration system supports both Vertex AI and API key authentication for Google's GenAI:

```yaml
agent:
  use_vertex_ai: true  # Set to false to use API key authentication
  vertex_project: "your-google-cloud-project-id"
  vertex_location: "us-central1"
  service_account_file: "/path/to/service-account.json"  # Optional path to service account JSON file
  
api_keys:
  google: "${GOOGLE_API_KEY}"  # Used if use_vertex_ai is false
```

For Vertex AI authentication, you can either:
1. Rely on application default credentials (the default)
2. Specify a service account file path using the `service_account_file` setting
3. Use the `GOOGLE_APPLICATION_CREDENTIALS` environment variable

If `use_vertex_ai` is set to `false`, the system will fall back to API key authentication using the Google API key.

## MCP Server Configuration

Multiple MCP servers can be configured in the `integrations.mcp.servers` section:

```yaml
integrations:
  mcp:
    servers:
      - id: "example-mcp"
        name: "Example MCP Server"
        enabled: true
        transport: "sse"
        url: "https://example.com/mcp/sse"
        auth_token: "${MCP_TOKEN}"

      - id: "another-mcp"
        name: "Another MCP Server"
        enabled: false  # Disabled server
        transport: "sse"
        url: "https://another.example.com/mcp/sse"
        auth_token: "${ANOTHER_TOKEN}"
```

## Testing Your Configuration

You can run the test scripts to verify your configuration:

```bash
# Test the general configuration
python tools/test_config_env.py

# Test MCP server configuration
python tools/test_mcp_config.py

# Test all integrations with YAML configuration
python tools/test_yaml_integrations.py
```

## Migrating from Environment Variables

If you previously used environment variables in a `.env` file, you can convert them to a `config.yaml` file using the migration script:

```bash
python tools/migrate_env_to_yaml.py
```

This script will:
1. Read your existing `.env` file
2. Convert the variables to a structured YAML format
3. Create a new `config.yaml` file in the project root
4. Use environment variable interpolation for sensitive data

## Best Practices

1. Keep sensitive information in environment variables and reference them in config.yaml
2. Use appropriate file permissions (e.g., chmod 600) for the config.yaml file
3. Always validate your configuration after making changes
4. Keep backup copies of your configuration before major changes
5. Use version control for tracking configuration changes (but exclude sensitive data)