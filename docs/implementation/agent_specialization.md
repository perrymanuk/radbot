# Agent Specialization Plan

## Overview

This implementation plan outlines a strategy to break up the current monolithic agent approach, where all tools are attached to every agent, into a more specialized system. This will significantly reduce token usage by only sending relevant tool descriptions with each message.

## Problem

Currently, we have a very large token usage with every message from agents because of the large number of functions and their descriptions that are sent with every call. This creates several issues:

1. Higher API costs due to excessive token usage
2. Reduced context available for actual user queries and responses
3. Slower response times due to processing larger messages
4. Potential for reaching token limits with complex interactions

## Solution

Create specialized agents that focus on specific domains, with each agent only having access to the tools relevant to its domain. A main orchestrator agent will route requests to the appropriate specialized agent based on the user's intent.

## Specialized Agent Categories

### 1. File System Agent

**Purpose**: Handle all file-related operations and searches
**Tools**:
- `read_file_func`
- `list_directory_func`
- `get_info_func`
- `search_func`
- `write_file_func`
- `edit_file_func`
- `copy_func`
- `delete_func`
- Glob, Grep, LS, Read, Edit, Write, etc.

### 2. Web Research Agent

**Purpose**: Search and retrieve information from the web
**Tools**:
- `web_search`
- WebSearch, WebFetch

### 3. Memory Agent

**Purpose**: Manage conversation history and knowledge base
**Tools**:
- `search_past_conversations`
- `store_important_information`
- Memory-related MCP functions

### 4. Todo Management Agent

**Purpose**: Manage task lists and projects
**Tools**:
- `add_task`
- `complete_task`
- `remove_task`
- `list_projects`
- `list_project_tasks`
- `list_all_tasks`
- `update_task`
- `update_project`
- TodoRead, TodoWrite

### 5. Calendar Agent

**Purpose**: Manage calendar events and scheduling
**Tools**:
- `list_calendar_events_wrapper`
- `create_calendar_event_wrapper`
- `update_calendar_event_wrapper`
- `delete_calendar_event_wrapper`
- `check_calendar_availability_wrapper`

### 6. Home Assistant Agent

**Purpose**: Control and monitor smart home devices
**Tools**:
- `search_ha_entities`
- `list_ha_entities`
- `get_ha_entity_state`
- `turn_on_ha_entity`
- `turn_off_ha_entity`
- `toggle_ha_entity`

### 7. Code Execution Agent

**Purpose**: Execute and manage code operations
**Tools**:
- `execute_shell_command`
- `call_code_execution_agent`
- Bash, Task, etc.

### 8. Agentic Coder Agent

**Purpose**: Handle agent-to-agent communication and delegated model operations
**Tools**:
- `prompt_claude` - Allows delegating prompts to Claude model
- Future tools for delegating to other models/agents
- Tools for processing and transforming agent responses
- Support for agent-to-agent templated communications

### 9. Core Utility Agent

**Purpose**: Provide common utilities needed by multiple agents
**Tools**:
- `get_current_time`
- `get_weather`
- Common utility MCP functions

## Main Agent (Orchestrator)

**Purpose**: Route requests to specialized agents and maintain conversation context
**Tools**:
- `transfer_to_agent` (present in all agents)
- Basic context extraction tools

## Implementation Approach

### 1. Agent Factory Modifications

Extend the current `AgentFactory` class to support creating specialized agents:

```python
@staticmethod
def create_specialized_agent(
    specialization: str,
    name: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[ConfigManager] = None
) -> Agent:
    """Create a specialized agent with domain-specific tools.
    
    Args:
        specialization: Type of specialized agent ('filesystem', 'web', 'calendar', etc.)
        name: Optional custom name for the agent
        model: Optional model override
        config: Optional ConfigManager instance
        
    Returns:
        Configured specialized agent
    """
    # Select appropriate tools based on specialization
    tools = []
    instruction_name = f"{specialization}_agent"
    agent_name = name or f"{specialization}_agent"
    
    if specialization == "filesystem":
        tools = create_filesystem_toolset()
        description = "Agent specialized in filesystem operations"
    elif specialization == "web_research":
        tools = create_web_research_toolset()
        description = "Agent specialized in web research and information retrieval"
    elif specialization == "memory":
        tools = create_memory_toolset()
        description = "Agent specialized in memory management and information retrieval"
    elif specialization == "todo":
        tools = create_todo_toolset()
        description = "Agent specialized in task and project management"
    elif specialization == "calendar":
        tools = create_calendar_toolset()
        description = "Agent specialized in calendar operations and scheduling"
    elif specialization == "homeassistant":
        tools = create_homeassistant_toolset()
        description = "Agent specialized in controlling smart home devices"
    elif specialization == "code_execution":
        tools = create_code_execution_toolset()
        description = "Agent specialized in executing code and shell commands"
    elif specialization == "agentic_coder":
        tools = create_agentic_coder_toolset()
        description = "Agent specialized in delegating to other models and processing responses"
    elif specialization == "utility":
        tools = create_utility_toolset()
        description = "Agent providing common utility functions"
    else:
        raise ValueError(f"Unknown specialization: {specialization}")
    
    # Always add the transfer_to_agent tool
    tools.append(transfer_to_agent)
    
    # Create and return the specialized agent
    return AgentFactory.create_sub_agent(
        name=agent_name,
        description=description,
        instruction_name=instruction_name,
        tools=tools,
        model=model,
        config=config
    )
```

### 2. Tool Organization

Create separate modules for each specialization to organize the tools:

```
radbot/tools/
  ├── specialized/
  │   ├── filesystem_toolset.py
  │   ├── web_research_toolset.py
  │   ├── calendar_toolset.py
  │   ├── homeassistant_toolset.py
  │   ├── memory_toolset.py
  │   ├── todo_toolset.py
  │   ├── code_execution_toolset.py
  │   ├── agentic_coder_toolset.py
  │   └── utility_toolset.py
```

Each module will export a function that returns the complete set of tools for that specialization.

Example for the Agentic Coder toolset:

```python
# radbot/tools/specialized/agentic_coder_toolset.py

import logging
from typing import List, Any, Optional
from google.adk.tools.function_tool import FunctionTool

from radbot.tools.mcp.claude_cli import prompt_claude
# Import future model/agent delegation tools as they are developed

logger = logging.getLogger(__name__)

def create_agentic_coder_toolset() -> List[Any]:
    """Create the set of tools for the Agentic Coder agent.
    
    Returns:
        List of tools for delegating to models and processing responses
    """
    tools = []
    
    # Add Claude prompt tool
    try:
        tools.append(prompt_claude)
        logger.info("Added prompt_claude tool to agentic coder toolset")
    except Exception as e:
        logger.error(f"Failed to add prompt_claude tool: {e}")
    
    # Add future tools for other models/agents as they are developed
    
    return tools
```

### 3. Agent Transfer Mechanism

Enhance the `transfer_to_agent` function to support specialized agents:

```python
def transfer_to_agent(params: Dict[str, Any]) -> None:
    """Transfer control to another agent, specialized or not.
    
    Args:
        params: Dictionary with 'agent_name' key
    """
    agent_name = params.get("agent_name")
    
    # Check if this is a known specialized agent type
    if agent_name in SPECIALIZED_AGENT_TYPES:
        # Create the specialized agent on demand
        agent = AgentFactory.create_specialized_agent(specialization=agent_name)
    elif agent_name in KNOWN_AGENTS:
        # Use a predefined agent
        agent = KNOWN_AGENTS[agent_name]
    else:
        # Create a generic sub-agent
        agent = AgentFactory.create_sub_agent(name=agent_name)
    
    # Transfer control
    response = agent(params.get("message", ""))
    return response
```

### 4. Main Orchestrator Logic

Enhance the main agent to detect intents and route to specialized agents:

```python
def detect_specialization_need(user_message: str) -> Optional[str]:
    """Detect if a user message requires a specialized agent.
    
    Args:
        user_message: The user's input message
        
    Returns:
        Specialization name or None if no specialization is needed
    """
    keywords = {
        "filesystem": ["file", "directory", "read", "write", "edit", "search files"],
        "web_research": ["search", "lookup", "find information", "research"],
        "calendar": ["calendar", "schedule", "event", "appointment", "meeting"],
        "homeassistant": ["turn on", "turn off", "lights", "thermostat", "home assistant"],
        "todo": ["task", "todo", "reminder", "list tasks", "project"],
        # Add more patterns for other specializations
    }
    
    for specialization, patterns in keywords.items():
        if any(pattern in user_message.lower() for pattern in patterns):
            return specialization
            
    return None
```

This function would be used in the main agent's handler to decide whether to transfer to a specialized agent.

### 5. Configuration System

Extend the YAML configuration to support specialized agents:

```yaml
agent:
  main_model: "google/gemini-1.5-pro-latest"
  sub_agent_model: "google/gemini-1.5-flash-latest"
  specialized_agents:
    enabled: true  # Master switch for specialized agents
    filesystem:
      enabled: true
      model: "google/gemini-1.5-flash-latest"
    web_research:
      enabled: true
      model: "google/gemini-1.5-pro-latest"
    calendar:
      enabled: true
    homeassistant:
      enabled: true
    # Add more specialized agents
```

## Benefits

1. **Reduced Token Usage**: Only relevant tool descriptions are sent with each message
2. **Improved Performance**: Faster response times due to smaller message sizes
3. **Better Specialization**: Agents can be fine-tuned for specific domains
4. **Scalability**: Easier to add new tool categories without impacting existing functionality
5. **Flexibility**: Different models can be used for different specializations based on requirements

## Implementation Plan

1. Create specialized tool modules and tool creation functions
2. Update the AgentFactory to support specialized agent creation
3. Implement enhanced agent transfer mechanism
4. Update configuration system to support specialized agents
5. Modify main agent to detect specialization needs and perform transfers
6. Create specialized instructions for each agent type
7. Test and optimize the system

## Conclusion

By implementing this specialized agent architecture, we can significantly reduce token usage while maintaining or even improving the system's capabilities. The modularity also allows for easier future extensions and maintenance.