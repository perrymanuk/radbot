"""
Factory functions for creating MCP-enabled agents.

This module provides factory functions for creating agents with MCP capabilities
including tools from Home Assistant, FileServer, and other MCP integrations.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)

# Import necessary modules
from radbot.config.config_loader import config_loader
from radbot.tools.mcp.mcp_core import get_available_mcp_tools, HAVE_TAVILY

def create_mcp_enabled_agent(agent_factory: Callable, base_tools: Optional[List[Any]] = None, **kwargs) -> Any:
    """
    Create an agent with all MCP tools enabled.
    
    This function creates an agent with all MCP tools from config.yaml.
    
    Args:
        agent_factory: Function to create an agent (like create_agent)
        base_tools: Optional list of base tools to include
        **kwargs: Additional arguments to pass to agent_factory
        
    Returns:
        Agent: The created agent with MCP tools
    """
    try:
        # Start with base tools or empty list
        tools = list(base_tools or [])
        
        # Create MCP tools
        mcp_tools = get_available_mcp_tools()
        
        if mcp_tools:
            # Add the tools to our list
            tools.extend(mcp_tools)
            logger.info(f"Added {len(mcp_tools)} MCP tools to agent")
        else:
            logger.warning("No MCP tools were created")
            
        # Create the agent with the tools
        agent = agent_factory(tools=tools, **kwargs)
        return agent
    except Exception as e:
        logger.error(f"Error creating agent with MCP tools: {str(e)}")
        # Create agent without MCP tools as fallback
        return agent_factory(tools=base_tools, **kwargs)

def create_tavily_search_tool(max_results=5, search_depth="advanced", include_answer=True, include_raw_content=True, include_images=False):
    """
    Create a Tavily search tool that can be used by the agent.
    
    This tool allows the agent to search the web via Tavily's search API.
    
    Args:
        max_results: Maximum number of search results to return (default: 5)
        search_depth: Search depth, either "basic" or "advanced" (default: "advanced")
        include_answer: Whether to include an AI-generated answer (default: True) 
        include_raw_content: Whether to include the raw content of search results (default: True)
        include_images: Whether to include images in search results (default: False)
        
    Returns:
        The created Tavily search tool wrapped for ADK, or None if creation fails
    """
    if not HAVE_TAVILY:
        logger.error("Tavily search tool requires langchain-community package with TavilySearchResults")
        return None
    
    # Get Tavily API key: credential store → config.yaml → env var
    api_key = None
    try:
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        if store.available:
            api_key = store.get("tavily_api_key")
            if api_key:
                logger.info("Using Tavily API key from credential store")
    except Exception as e:
        logger.debug(f"Credential store lookup for tavily_api_key failed: {e}")
    if not api_key:
        api_key = config_loader.get_config().get("api_keys", {}).get("tavily")
    if not api_key:
        api_key = os.environ.get("TAVILY_API_KEY")
    
    if not api_key:
        logger.error("Tavily API key not found in config.yaml or TAVILY_API_KEY environment variable. "
                     "The Tavily search tool will not function correctly.")
        # We don't return None here to allow for testing/development without credentials
    else:
        # Set the environment variable for the LangChain tool
        os.environ["TAVILY_API_KEY"] = api_key
    
    try:
        from langchain_community.tools import TavilySearchResults
        from google.adk.tools.langchain import LangchainTool
        
        # Instantiate LangChain's Tavily search tool
        tavily_search = TavilySearchResults(
            max_results=max_results,
            search_depth=search_depth,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            include_images=include_images,
        )
        
        # Wrap with LangchainTool for ADK compatibility
        adk_tavily_tool = LangchainTool(tool=tavily_search)
        logger.info(f"Successfully created Tavily search tool with max_results={max_results}, search_depth={search_depth}")
        return adk_tavily_tool
        
    except Exception as e:
        logger.error(f"Failed to create Tavily search tool: {str(e)}")
        return None