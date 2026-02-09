# Agent Framework Architecture

<!-- Version: 0.4.0 | Last Updated: 2025-05-07 -->


This document provides a comprehensive overview of the agent framework architecture in the RadBot system, including the consolidation process, component design, and key implementation details.

## Overview

The RadBot agent framework provides a structured approach for building, configuring, and managing AI agents using Google's Agent Development Kit (ADK). The framework supports multiple agent types, tool integration, memory services, and agent-to-agent transfers.

## Agent Framework Consolidation

The agent framework underwent a significant consolidation to provide a more maintainable and consistent architecture. The consolidation involved centralizing agent-related code spread across multiple files into a cohesive layered architecture.

### Pre-Consolidation Architecture

Previously, there were three separate agent.py files with overlapping functionality:

1. **/agent.py** (root) - Entry point for ADK web interface
2. **/radbot/agent.py** - Module-level implementation with caching
3. **/radbot/agent/agent.py** - Core implementation with class structure

This structure caused several issues:
- Code duplication across files
- Inconsistent implementation of features
- Difficulty maintaining compatibility
- Confusion about which file to modify for changes

### Consolidated Architecture

The consolidated architecture follows a clear layered approach:

#### 1. Core Implementation (`/radbot/agent/agent.py`)

This file contains the fundamental agent implementation:
- `RadBotAgent` class - Complete OOP implementation including:
  - Session management
  - Tool registration
  - Message processing
  - Memory integration
  - Sub-agent management
- `AgentFactory` class - Factory methods for different agent types
- Helper functions - Simplified creation and configuration

#### 2. Module Interface (`/radbot/agent.py`)

This file serves as a wrapper around the core implementation:
- Imports core functionality from `/radbot/agent/agent.py`
- Re-exports necessary components for backward compatibility
- Provides module-specific functionality (like caching)
- Offers simplified interface through a `create_agent()` function

#### 3. Web Entry Point (`/agent.py`)

This file remains as the ADK web entry point:
- Imports the core functionality from `/radbot/agent/agent.py`
- Configures web-specific tools and settings
- Exposes the `create_agent()` function for ADK web compatibility
- Creates and exposes the `root_agent` variable used by the web API

## Key Components

### RadBotAgent Class

The `RadBotAgent` class is the central component of the framework:

```python
class RadBotAgent:
    """Main agent class for the RadBot framework."""
    
    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        tools: Optional[List[Any]] = None,
        model: Optional[str] = None,
        name: str = "beto",
        instruction: Optional[str] = None,
        instruction_name: Optional[str] = "main_agent",
        config: Optional[ConfigManager] = None,
        memory_service: Optional[Any] = None,
        app_name: str = "beto"
    ):
        # Initialize agent components
        ...
```

Key features of RadBotAgent:

1. **Flexible Configuration**
   - Supports both direct instruction strings and named instructions
   - Configurable model selection
   - Custom session and memory services

2. **Tool Management**
   - Methods to add individual tools or batches of tools
   - Support for tool handlers with ADK 0.4.0
   - Automatic registration of common tools

3. **Message Processing**
   - Handles conversation state through session management
   - Processes user messages and extracts appropriate responses
   - Error handling and recovery

4. **Sub-Agent Management**
   - Addition and registration of specialized sub-agents
   - Bidirectional parent-child relationships
   - Transfer support between agents

### AgentFactory Class

The `AgentFactory` class provides factory methods for creating different types of agents:

```python
class AgentFactory:
    """Factory class for creating and configuring agents."""

    @staticmethod
    def create_root_agent(
        name: str = "beto",
        model: Optional[str] = None,
        tools: Optional[List] = None,
        instruction_name: str = "main_agent",
        config: Optional[ConfigManager] = None
    ) -> Agent:
        """Create the main root agent."""
        ...

    @staticmethod
    def create_sub_agent(
        name: str,
        description: str,
        instruction_name: str,
        tools: Optional[List] = None,
        model: Optional[str] = None,
        config: Optional[ConfigManager] = None
    ) -> Agent:
        """Create a sub-agent with appropriate model and configuration."""
        ...

    @staticmethod
    def create_web_agent(
        name: str = "beto",
        model: Optional[str] = None,
        tools: Optional[List] = None,
        instruction_name: str = "main_agent",
        config: Optional[ConfigManager] = None,
        register_tools: bool = True
    ) -> Agent:
        """Create an agent specifically for the ADK web interface."""
        ...
```

The factory pattern allows for consistent creation of agents with appropriate configurations for different contexts.

### Agent Creation Helpers

Several helper functions simplify the agent creation process:

```python
def create_agent(
    session_service: Optional[SessionService] = None,
    tools: Optional[List[Any]] = None,
    model: Optional[str] = None,
    instruction_name: str = "main_agent",
    name: str = "beto",
    config: Optional[ConfigManager] = None,
    include_memory_tools: bool = True,
    for_web: bool = False,
    register_tools: bool = True,
    app_name: str = "beto"
) -> Union[RadBotAgent, Agent]:
    """Create a configured RadBot agent."""
    ...
```

This function serves as the main entry point for creating agents throughout the application.

## Tool Integration

The agent framework supports multiple tool types:

1. **Basic Tools**
   - get_current_time - Provides current time information
   - get_weather - Retrieves weather information

2. **Memory Tools**
   - search_past_conversations - Searches conversation history
   - store_important_information - Stores significant information

3. **Integration Tools**
   - Home Assistant tools - Control smart home devices
   - Filesystem tools - Access and manipulate files
   - Calendar tools - Manage calendar events

4. **Research Tools**
   - Web search tools - Search the internet for information

5. **Task Management Tools**
   - Todo tools - Manage tasks and projects

Tools are registered with agents through:
- Direct addition with `add_tool()` method
- Batch addition with `add_tools()` method
- Factory methods that include appropriate tools

## Agent Transfers

The framework supports transferring control between agents:

1. **Transfer Mechanism**
   - Uses ADK's `transfer_to_agent` tool
   - Requires consistent agent naming
   - Bidirectional parent-child relationships

2. **Agent Tree Structure**
   - Main agent ("beto") as the root
   - Research agent ("scout") as a sub-agent
   - Other specialized agents as needed

3. **Transfer Implementation**
   - Main to Scout: `transfer_to_agent(agent_name='scout')`
   - Scout to Main: `transfer_to_agent(agent_name='beto')`

A comprehensive verification system ensures the agent tree is properly structured for transfers:

```python
def _verify_agent_structure(self):
    """Verify and fix agent tree structure issues for ADK compatibility."""
    # Verify root agent name
    # Verify sub-agent registration
    # Establish bidirectional relationships
    # Check transfer tool availability
    # Register tool handlers
    ...
```

## Memory System Integration

The agent framework integrates with the memory system:

1. **Memory Service Creation**
   - Automatic creation if memory tools are requested
   - Support for custom memory service injection

2. **Memory Tools Integration**
   - Tool registration in the agent
   - Tool handler configuration

3. **Memory Configuration**
   - Storage in ToolContext for access by tools
   - Configuration options through environment variables

## Usage Guidelines

### For General Usage

Import from the module-level package:

```python
from radbot.agent import create_agent

agent = create_agent(
    name="my_agent",
    tools=[my_tool1, my_tool2],
    instruction_name="custom_instruction"
)

# Process messages
response = agent.process_message(user_id="user123", message="Hello")
```

### For Direct ADK Web Interface

The root agent.py file is used automatically by the ADK web interface through adk.config.json. No changes to import patterns are needed.

### For Advanced Usage

Import specific components from the core package:

```python
from radbot.agent.agent import RadBotAgent, AgentFactory

# Create a specialized agent with the factory
agent = AgentFactory.create_sub_agent(
    name="specialized_agent",
    description="A specialized agent for specific tasks",
    instruction_name="specialized_instruction",
    tools=[specialized_tool1, specialized_tool2]
)
```

## ADK Compatibility Considerations

The agent framework is designed to work with Google's ADK 0.4.0 and later versions. Key compatibility features:

1. **Agent Tree Registration**
   - Proper parent-child relationships
   - Consistent naming across the application
   - Tool handler registration

2. **Session Management**
   - Matching app_name and agent.name values
   - Consistent session creation and retrieval

3. **Tool Registration**
   - Direct tool function registration
   - Support for ADK tool constants
   - Tool handler registration

## Future Improvements

1. **Enhanced Agent Types**
   - More specialized agent types
   - Richer factory methods

2. **Improved Tool Organization**
   - Tool categories and namespaces
   - Dynamic tool loading

3. **Better Agent Tree Management**
   - Dedicated agent tree class
   - Visualization tools

4. **Enhanced Error Handling**
   - More robust error recovery
   - Graceful degradation

5. **Performance Optimizations**
   - Lazy tool loading
   - Selective memory integration