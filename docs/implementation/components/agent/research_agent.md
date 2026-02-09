# Research Agent Implementation

<!-- Version: 0.4.0 | Last Updated: 2025-05-07 -->


This document details the implementation of the Technical Research Sub-Agent using Google's Agent Development Kit (ADK).

## Overview

The Research Agent is a specialized sub-agent designed to assist with technical implementation research by interacting with various tools including web scraping utilities, internal Retrieval-Augmented Generation (RAG) systems, and GitHub repositories. Additionally, it facilitates "rubber ducky" design sessions, acting as a sounding board for technical architecture discussions.

The agent is implemented as a sub-agent within the larger multi-agent system, allowing the main coordinator agent to delegate technical research and design discussion tasks to it.

## Implementation Details

### Directory Structure

The Research Agent is implemented in the following directory structure:

```
radbot/
└── agent/
    └── research_agent/
        ├── __init__.py          # Package exports
        ├── agent.py             # Primary agent implementation
        ├── instructions.py      # Agent prompt instructions
        ├── tools.py             # Research-specific tools 
        └── factory.py           # Factory function for easy creation
```

### Components

#### 1. Research Agent (agent.py)

The `ResearchAgent` class is the main implementation of the research agent, wrapping an ADK `LlmAgent` instance. It provides:

- Initialization with default or custom configuration
- Access to the underlying ADK agent for integration

#### 2. Agent Instructions (instructions.py)

The instructions module defines the prompts used to guide the agent's behavior:

- `RESEARCH_AGENT_INSTRUCTION`: Core instruction for the agent's dual role
- `WEB_SCRAPER_INSTRUCTION`: Guidance for web search and crawling
- `INTERNAL_KNOWLEDGE_INSTRUCTION`: Guidance for internal knowledge search
- `GITHUB_SEARCH_INSTRUCTION`: Guidance for code search
- `RUBBER_DUCK_INSTRUCTION`: Guidance for design discussions

These are combined into a comprehensive instruction prompt via the `get_full_research_agent_instruction()` function.

#### 3. Tools Integration

The research agent uses the following tools from the main agent:

- **Web Search Tool**: `web_search` - For searching the web for information
- **File Operation Tools**: `list_files`, `read_file`, `get_file_info`, `write_file`, `copy_file`, `move_file`, `delete_file` - For interacting with the file system
- **Shell Command Tool**: `execute_shell_command` - For executing system commands
- **Memory Tools**: `search_past_conversations`, `store_important_information` - For accessing conversation history and storing important information

#### 4. Factory Function (factory.py)

The `create_research_agent()` factory function simplifies the creation of research agents with:

- Optional custom name, model, and instruction
- Support for additional tools
- Option to return either the `ResearchAgent` wrapper or the underlying ADK agent

### Integration with Main Agent

The research agent is integrated with the main agent as a sub-agent, enabling task delegation using ADK's LLM-driven transfer mechanism. This integration is done in the `create_agent()` function in the root `agent.py` file.

The integration includes:

1. Creating the research agent using the factory function
2. Adding it to the main agent's `sub_agents` list
3. Updating the main agent's instruction to guide it on when to delegate to the research agent

## Usage Scenarios

### Technical Research

When a user asks a technical implementation question, the main agent can transfer to the research agent, which will:

1. Use web_search for retrieving external information from the web
2. Use file tools (list_files, read_file, etc.) to access local documentation and code
3. Use search_past_conversations to reference previous knowledge
4. Use execute_shell_command when local command execution is needed
5. Synthesize the findings and present them to the user

### Design Discussions ("Rubber Ducking")

When a user wants to discuss a technical design, the main agent can transfer to the research agent, which will:

1. Engage in a conversational analysis of the design
2. Ask clarifying questions to understand the design fully
3. Suggest improvements or alternatives when appropriate
4. Use research tools to find relevant examples or patterns
5. Help identify edge cases or potential issues

## Dependencies

- Google ADK (google-adk>=0.3.0)
- BeautifulSoup4 (optional, for enhanced web scraping)
- PyGithub (optional, for GitHub repository search)

## Configuration

The research agent uses the project's configuration manager for default settings such as the model to use. It can also be configured with custom settings through the factory function.

## Future Enhancements

Potential future enhancements include:

1. Adding more specialized research tools (e.g., API documentation search)
2. Implementing specific tools for code generation based on research
3. Adding support for sequential research workflows using ADK's SequentialAgent
4. Implementing A2A (Agent-to-Agent) protocol for more flexible agent interactions
5. Adding evaluation datasets to test research capabilities systematically

## Example Main Agent Integration

```python
from radbot.agent.research_agent import create_research_agent

# Create the main agent
main_agent = Agent(
    name="root_agent",
    model="gemini-1.5-pro-latest",
    instruction="You are the main coordinator agent...",
    tools=[...],
)

# Create and add the research agent as a sub-agent
research_agent = create_research_agent(
    name="technical_research_agent",
    as_subagent=False  # Get the ADK agent directly
)
main_agent.sub_agents.append(research_agent)
```

## Testing

To test the research agent:

1. Directly in code using ADK's Runner:
   ```python
   from google.adk.runners import Runner
   from radbot.agent.research_agent import create_research_agent
   
   agent = create_research_agent(as_subagent=False)
   runner = Runner(agent=agent)
   response = runner.run({"query": "What are best practices for async API design?"})
   print(response)
   ```

2. Using ADK's Development UI for interactive testing
3. As part of the main agent through delegation
