"""
Utility functions for agent creation and configuration.

This module provides utility functions for creating and configuring agents,
runners, and handling agent creation with specific capabilities.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union
from google.protobuf.json_format import MessageToDict

# Import ADK components
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.transfer_to_agent_tool import transfer_to_agent

# Configure logging
logger = logging.getLogger(__name__)

# Type alias for backward compatibility
SessionService = InMemorySessionService

# Import our configuration modules
from radbot.config import config_manager
from radbot.config.settings import ConfigManager

# Import agent factory and base components
from radbot.agent.agent_base import RadBotAgent
from radbot.agent.agent_factory import AgentFactory


def create_runner(
    agent: Agent, 
    app_name: str = "beto",
    session_service: Optional[SessionService] = None
) -> Runner:
    """Create an ADK Runner with the specified agent.

    Args:
        agent: The agent to run
        app_name: Name of the application
        session_service: Optional custom session service

    Returns:
        Configured runner
    """
    # Use provided session service or create an in-memory one
    sess_service = session_service or InMemorySessionService()
    
    # Create and return the runner
    return Runner(
        agent=agent,
        app_name=app_name,
        session_service=sess_service
    )


def create_agent(
    session_service: Optional[SessionService] = None,
    tools: Optional[List[Any]] = None,
    model: Optional[str] = None,
    instruction_name: str = "main_agent",
    name: str = "beto",
    config: Optional[ConfigManager] = None,
    include_memory_tools: bool = True,
    include_google_search: bool = False,
    include_code_execution: bool = False,
    for_web: bool = False,
    register_tools: bool = True,
    app_name: str = "beto"
) -> Union[RadBotAgent, Agent]:
    """
    Create a configured RadBot agent.
    
    Args:
        session_service: Optional session service for conversation state
        tools: Optional list of tools for the agent
        model: Optional model to use (defaults to config's main_model)
        instruction_name: Name of instruction to load from config
        name: Name for the agent
        config: Optional ConfigManager instance (uses global if not provided)
        include_memory_tools: If True, includes memory tools automatically
        include_google_search: If True, register a google_search sub-agent
        include_code_execution: If True, register a code_execution sub-agent
        for_web: If True, returns an ADK Agent for web interface
        register_tools: Whether to register common tool handlers
        app_name: Application name for session management
        
    Returns:
        A configured RadBotAgent instance or ADK Agent for web interface
    """
    logger.info(f"Creating agent (for_web={for_web}, name={name})")
    
    # Start with the given tools or empty list
    all_tools = list(tools or [])
    
    # Include memory tools if requested
    if include_memory_tools:
        try:
            from radbot.tools.memory.memory_tools import search_past_conversations, store_important_information
            memory_tools = [search_past_conversations, store_important_information]
            
            # Add memory tools if they're not already included
            memory_tool_names = set([tool.__name__ for tool in memory_tools])
            existing_tool_names = set()
            for tool in all_tools:
                if hasattr(tool, '__name__'):
                    existing_tool_names.add(tool.__name__)
                elif hasattr(tool, 'name'):
                    existing_tool_names.add(tool.name)
            
            # Add any missing memory tools
            for tool in memory_tools:
                if tool.__name__ not in existing_tool_names:
                    all_tools.append(tool)
                    logger.info(f"Explicitly adding memory tool: {tool.__name__}")
        except Exception as e:
            logger.warning(f"Failed to add memory tools: {str(e)}")
    
    # For web interface, use AgentFactory to create an ADK Agent directly
    if for_web:
        agent = AgentFactory.create_web_agent(
            name=name,
            model=model,
            tools=all_tools,
            instruction_name=instruction_name,
            config=config,
            register_tools=register_tools
        )
        logger.info(f"Created web agent with {len(all_tools)} tools")
        
        # Add built-in tool agents as sub-agents if requested
        if include_google_search or include_code_execution:
            try:
                from radbot.tools.adk_builtin import create_search_agent, create_code_execution_agent
                sub_agents = list(agent.sub_agents) if hasattr(agent, 'sub_agents') and agent.sub_agents else []

                if include_google_search:
                    try:
                        search_sub = create_search_agent(name="search_agent")
                        sub_agents.append(search_sub)
                        logger.info(f"Added search_agent as sub-agent of {name}")
                    except Exception as e:
                        logger.warning(f"Failed to create search agent: {str(e)}")

                if include_code_execution:
                    try:
                        code_sub = create_code_execution_agent(name="code_execution_agent")
                        sub_agents.append(code_sub)
                        logger.info(f"Added code_execution_agent as sub-agent of {name}")
                    except Exception as e:
                        logger.warning(f"Failed to create code execution agent: {str(e)}")

                agent.sub_agents = sub_agents
            except Exception as e:
                logger.warning(f"Failed to import built-in tool factories: {str(e)}")

        return agent
    
    # Otherwise, create a RadBotAgent instance
    agent = RadBotAgent(
        session_service=session_service,
        tools=all_tools,
        model=model,
        name=name,
        instruction_name=instruction_name,
        config=config,
        app_name=app_name
    )
    
    # Register tool handlers if requested
    if register_tools:
        agent.register_tool_handlers()
    
    # Add built-in tool agents as sub-agents if requested
    if include_google_search or include_code_execution:
        try:
            from radbot.tools.adk_builtin import create_search_agent, create_code_execution_agent

            sub_agents = list(agent.root_agent.sub_agents) if hasattr(agent.root_agent, 'sub_agents') and agent.root_agent.sub_agents else []

            if include_google_search:
                try:
                    search_sub = create_search_agent(name="search_agent", model=model, config=config)
                    if not any(sa.name == "search_agent" for sa in sub_agents if hasattr(sa, 'name')):
                        sub_agents.append(search_sub)
                        logger.info(f"Added search_agent to root_agent.sub_agents list")
                except Exception as e:
                    logger.warning(f"Failed to create search agent: {str(e)}")

            if include_code_execution:
                try:
                    code_sub = create_code_execution_agent(name="code_execution_agent", model=model, config=config)
                    if not any(sa.name == "code_execution_agent" for sa in sub_agents if hasattr(sa, 'name')):
                        sub_agents.append(code_sub)
                        logger.info(f"Added code_execution_agent to root_agent.sub_agents list")
                except Exception as e:
                    logger.warning(f"Failed to create code execution agent: {str(e)}")

            agent.root_agent.sub_agents = sub_agents
        except Exception as e:
            logger.warning(f"Failed to import built-in tool factories: {str(e)}")
    
    # Log the tools included in the agent
    if agent.root_agent and agent.root_agent.tools:
        tool_names = []
        for tool in agent.root_agent.tools:
            if hasattr(tool, '__name__'):
                tool_names.append(tool.__name__)
            elif hasattr(tool, 'name'):
                tool_names.append(tool.name)
            else:
                tool_names.append(str(type(tool)))
        logger.info(f"Created RadBotAgent with tools: {', '.join(tool_names)}")
    
    return agent


def create_core_agent_for_web(
    tools: Optional[List[Any]] = None, 
    name: str = "beto", 
    app_name: str = "beto",
    include_google_search: bool = False,
    include_code_execution: bool = False
) -> Agent:
    """
    Create an ADK Agent for web interface with all necessary configurations.
    
    Args:
        tools: Optional list of tools to include
        name: Name for the agent (must be "beto" for consistent transfers)
        app_name: Application name (must match agent name for ADK 0.4.0+)
        include_google_search: If True, register a google_search sub-agent
        include_code_execution: If True, register a code_execution sub-agent
        
    Returns:
        Configured ADK Agent for web interface
    """
    # Ensure agent name is always "beto" for consistent transfers
    if name != "beto":
        logger.warning(f"Agent name '{name}' changed to 'beto' for consistent transfers")
        name = "beto"
        
    # Ensure app_name matches agent name for ADK 0.4.0+
    if app_name != name:
        logger.warning(f"app_name '{app_name}' changed to '{name}' for ADK 0.4.0+ compatibility")
        app_name = name
        
    # Create the base agent with proper name and app_name
    agent = AgentFactory.create_web_agent(
        name=name,
        model=None,  # Will use config default
        tools=tools,
        instruction_name="main_agent",
        config=None,  # Will use global config
        register_tools=True
    )
    
    # Import required components for agent transfers
    from google.adk.tools.transfer_to_agent_tool import transfer_to_agent
    
    # Ensure agent has transfer_to_agent tool
    if hasattr(agent, 'tools'):
        # Check if tool already exists
        has_transfer_tool = False
        for tool in agent.tools:
            tool_name = getattr(tool, 'name', None) or getattr(tool, '__name__', None)
            if tool_name == 'transfer_to_agent':
                has_transfer_tool = True
                break
                
        if not has_transfer_tool:
            agent.tools.append(transfer_to_agent)
            logger.info("Added transfer_to_agent tool to root agent")
    
    # Create sub-agents if requested
    sub_agents = []
    
    # Add built-in tool agents if requested
    if include_google_search or include_code_execution:
        try:
            from radbot.tools.adk_builtin import create_search_agent, create_code_execution_agent
            
            if include_google_search:
                try:
                    search_agent = create_search_agent(name="search_agent")
                    # transfer_to_agent is now included in agent's tools by the factory
                    
                    sub_agents.append(search_agent)
                    logger.info("Created search_agent as sub-agent")
                except Exception as e:
                    logger.warning(f"Failed to create search agent: {str(e)}")
            
            if include_code_execution:
                try:
                    code_agent = create_code_execution_agent(name="code_execution_agent")
                    # transfer_to_agent is now included in agent's tools by the factory
                            
                    sub_agents.append(code_agent)
                    logger.info("Created code_execution_agent as sub-agent")
                except Exception as e:
                    logger.warning(f"Failed to create code execution agent: {str(e)}")
        except Exception as e:
            logger.warning(f"Failed to import built-in tool factories: {str(e)}")
    
    # Create scout agent if needed
    try:
        from radbot.agent.research_agent import create_research_agent
        
        # Pass the same settings to create consistent behavior
        scout_agent = create_research_agent(
            name="scout",  # MUST be "scout" for consistent transfers
            model=None,  # Will use config default
            tools=tools,  # Pass the same tools as the root agent
            as_subagent=False,  # Get the ADK agent directly
            enable_google_search=include_google_search,
            enable_code_execution=include_code_execution,
            app_name=app_name  # Same app_name for consistency
        )
        
        # Add to sub-agents
        sub_agents.append(scout_agent)
        logger.info("Added scout agent as sub-agent")
    except Exception as e:
        logger.warning(f"Failed to create scout agent: {str(e)}")
    
    # Set sub-agents list on the agent
    if sub_agents:
        agent.sub_agents = sub_agents
        logger.info(f"Added {len(sub_agents)} sub-agents to root agent")
        
        # Log the agent tree for debugging
        sub_agent_names = [sa.name for sa in agent.sub_agents if hasattr(sa, 'name')]
        logger.info(f"Agent tree: root='{agent.name}', sub_agents={sub_agent_names}")
    
    return agent