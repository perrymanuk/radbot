"""
Web search tools for radbot agents.

This module provides tools for web search capabilities using various search APIs.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Callable

from dotenv import load_dotenv

# Load environment variables first
load_dotenv()
logger = logging.getLogger(__name__)

# Flag to track if we have the necessary dependencies
HAVE_TAVILY = False
HAVE_LANGCHAIN = False

# Try to import tavily-python directly first
try:
    import tavily
    from tavily import TavilyClient
    logger.info(f"tavily-python found: version {getattr(tavily, '__version__', 'unknown')}")
    HAVE_TAVILY = True
except ImportError:
    logger.warning("tavily-python package not found. Web search capabilities will be limited.")
    logger.warning("Try installing with: pip install 'tavily-python>=0.3.8'")

# Try to import LangChain's Tavily integration
try:
    from langchain_community.tools import TavilySearchResults
    HAVE_LANGCHAIN = True
    logger.info("langchain-community with TavilySearchResults found")
except ImportError:
    logger.warning("langchain-community package or TavilySearchResults not found")
    logger.warning("Try installing with: pip install 'langchain-community>=0.2.16'")

# Check if we can use Tavily through LangChain or directly
if HAVE_LANGCHAIN and HAVE_TAVILY:
    logger.info("Both tavily-python and langchain-community are available - will use LangChain integration")
elif HAVE_TAVILY:
    logger.info("Only tavily-python is available - will use direct API access")
elif HAVE_LANGCHAIN:
    logger.info("Only langchain-community is available - might have issues without tavily-python")
else:
    logger.warning("Neither tavily-python nor langchain-community are available - web search will be disabled")

def create_tavily_search_tool(
    max_results: int = 5, 
    search_depth: str = "advanced", 
    include_answer: bool = True, 
    include_raw_content: bool = True, 
    include_images: bool = False
) -> Optional[Any]:
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
    # Check if we have the necessary imports
    if not (HAVE_TAVILY or HAVE_LANGCHAIN):
        logger.error("Cannot create Tavily search tool - required packages not installed")
        return None
    
    # Check credential store → env var for Tavily API key
    api_key = None
    try:
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        if store.available:
            api_key = store.get("tavily_api_key")
            if api_key:
                os.environ["TAVILY_API_KEY"] = api_key
                logger.info("Using Tavily API key from credential store")
    except Exception as e:
        logger.debug(f"Credential store lookup for tavily_api_key failed: {e}")
    if not api_key:
        api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        logger.warning("TAVILY_API_KEY not found in credential store or environment. Web search will not function correctly.")
    
    try:
        # Import FunctionTool from ADK
        try:
            from google.adk.tools import FunctionTool
            logger.info("Successfully imported FunctionTool from google.adk.tools")
        except ImportError as e:
            logger.error(f"Failed to import FunctionTool: {e}")
            logger.error("Will attempt to continue without FunctionTool wrapper")
            FunctionTool = None
        
        # Define the web_search function that will be used as a tool
        def web_search(query: str, tool_context=None) -> str:
            """
            Search the web for information about the query.
            
            Args:
                query: The search query
                tool_context: Optional tool context for accessing memory
                
            Returns:
                Search results as text
            """
            if not query or not isinstance(query, str):
                return "Please provide a valid search query as a string."
            
            logger.info(f"Running web search for query: {query}")
            
            try:
                # Get API key from various sources, with environment variables taking precedence
                api_key = os.environ.get("TAVILY_API_KEY")
                
                # Try to get from tool context if not in environment
                if not api_key and tool_context:
                    api_key = getattr(tool_context, "tavily_api_key", None)
                
                # If we still don't have an API key, check for a global one
                if not api_key:
                    try:
                        from google.adk.tools.tool_context import ToolContext
                        api_key = getattr(ToolContext, "tavily_api_key", None)
                    except Exception:
                        pass
                
                # Now check if we can use Tavily
                if not api_key:
                    logger.warning("No Tavily API key found in any location")
                    return f"Unable to search for '{query}'. Tavily API key is not available. Please set the TAVILY_API_KEY environment variable."
                
                # Search using the appropriate method
                if HAVE_LANGCHAIN:
                    # Use LangChain's Tavily integration
                    # Set the API key explicitly in environment for LangChain
                    os.environ["TAVILY_API_KEY"] = api_key
                    
                    # Create the TavilySearchResults instance
                    tavily_search = TavilySearchResults(
                        max_results=max_results,
                        search_depth=search_depth,
                        include_answer=include_answer,
                        include_raw_content=include_raw_content,
                        include_images=include_images,
                    )
                    
                    # Use the tool directly
                    results = tavily_search.invoke(query)
                    logger.info(f"LangChain Tavily search successful for query: {query}")
                    return results
                elif HAVE_TAVILY:
                    # Use tavily-python directly
                    client = TavilyClient(api_key=api_key)
                    response = client.search(
                        query=query,
                        search_depth=search_depth,
                        max_results=max_results,
                        include_answer=include_answer,
                        include_raw_content=include_raw_content,
                        include_images=include_images
                    )
                    
                    # Format the response to match LangChain's output format
                    formatted_result = ""
                    if include_answer and "answer" in response:
                        formatted_result += f"Answer: {response['answer']}\n\n"
                    
                    formatted_result += "Search Results:\n\n"
                    for i, result in enumerate(response.get("results", [])):
                        formatted_result += f"{i+1}. {result.get('title', 'No Title')}\n"
                        formatted_result += f"URL: {result.get('url', 'No URL')}\n"
                        formatted_result += f"Content: {result.get('content', 'No Content')}\n\n"
                    
                    logger.info(f"Direct Tavily API search successful for query: {query}")
                    return formatted_result
                else:
                    # This should never happen because we check at the start
                    return f"Unable to search for '{query}'. Tavily search is not available. Required packages not installed."
            except Exception as e:
                logger.error(f"Error in web_search: {str(e)}", exc_info=True)
                return f"Error searching for '{query}': {str(e)}"
        
        # Set the function name explicitly for better LLM understanding
        web_search.__name__ = "web_search"
        web_search.__doc__ = """
        Search the web for information on a topic.
        
        Args:
            query: The search query
            
        Returns:
            Search results as text
        """
        
        # Wrap the function with FunctionTool for ADK compatibility
        if FunctionTool:
            try:
                # ADK 0.3.0+ approach - create the FunctionTool with our function
                search_tool = FunctionTool(web_search)
                
                # For ADK 0.3.0, we need to define a better name/description
                search_tool.name = "web_search"
                search_tool.description = "Search the web for information on a topic."
                
                logger.info("Successfully created FunctionTool for web_search")
                return search_tool
            except Exception as e:
                logger.error(f"Failed to create FunctionTool: {e}", exc_info=True)
                # Fall back to returning the raw function
                logger.warning("Falling back to raw function without FunctionTool wrapper")
                return web_search
        else:
            # Return the raw function if FunctionTool is not available
            logger.warning("Using raw function without FunctionTool wrapper")
            return web_search
    except Exception as e:
        logger.error(f"Failed to create Tavily search tool: {str(e)}", exc_info=True)
        return None


def create_tavily_search_enabled_agent(agent_factory, base_tools=None, max_results=5, search_depth="advanced"):
    """
    Create an agent with Tavily web search capabilities.
    
    Args:
        agent_factory: Function to create an agent (like AgentFactory.create_root_agent or create_memory_enabled_agent)
        base_tools: Optional list of base tools to include
        max_results: Maximum number of search results to return (default: 5)
        search_depth: Search depth, either "basic" or "advanced" (default: "advanced")
        
    Returns:
        Agent: The created agent with Tavily search tool, or None if creation fails
    """
    try:
        # Start with base tools or empty list
        tools = list(base_tools or [])
        
        # Create the Tavily search tool
        tavily_tool = create_tavily_search_tool(
            max_results=max_results,
            search_depth=search_depth,
            include_answer=True,
            include_raw_content=True,
            include_images=False  # Default to no images to save tokens
        )
        
        if tavily_tool:
            # Add the Tavily search tool at the start of the list for higher priority
            tools.insert(0, tavily_tool)
            logger.info("Added Tavily search tool to agent tools")
        else:
            logger.warning("Could not create Tavily search tool for agent")
        
        # Create the agent with the tools
        logger.info(f"Creating agent with {len(tools)} total tools")
        agent = agent_factory(tools=tools)
        
        # Verify tool was added by inspecting the agent's tools
        tool_found = False
        
        # Check for the tool in different places depending on agent structure
        if hasattr(agent, 'tools'):
            # Direct tools list
            for tool in agent.tools:
                tool_name = str(getattr(tool, 'name', '') or getattr(tool, '__name__', '') or str(tool)).lower()
                if 'web_search' in tool_name or 'tavily' in tool_name:
                    tool_found = True
                    logger.info(f"Verified Tavily tool in agent.tools: {tool_name}")
                    break
        elif hasattr(agent, 'root_agent') and hasattr(agent.root_agent, 'tools'):
            # Tools in root_agent
            for tool in agent.root_agent.tools:
                tool_name = str(getattr(tool, 'name', '') or getattr(tool, '__name__', '') or str(tool)).lower()
                if 'web_search' in tool_name or 'tavily' in tool_name:
                    tool_found = True
                    logger.info(f"Verified Tavily tool in agent.root_agent.tools: {tool_name}")
                    break
        
        if not tool_found:
            logger.warning("Could not verify that Tavily tool was added to agent - check agent structure")
        
        return agent
    except Exception as e:
        logger.error(f"Error creating agent with Tavily search tool: {str(e)}", exc_info=True)
        return None