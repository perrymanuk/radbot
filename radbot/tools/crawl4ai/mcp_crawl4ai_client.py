#!/usr/bin/env python3
"""
MCP Crawl4AI Client

This module provides utilities for connecting to Crawl4AI from
within the radbot framework using the Model Context Protocol (MCP).
"""

import sys
import logging
import asyncio
import requests
import threading
import concurrent.futures
import atexit
from typing import Dict, Any, List, Optional, Tuple
from contextlib import AsyncExitStack

import google.adk.tools as adk_tools
from google.adk.tools import FunctionTool
try:
    # Also try to import newer types
    import google.adk.types as adk_types
except ImportError:
    adk_types = None

from radbot.config.config_loader import config_loader

# Import our own modules
from .utils import get_crawl4ai_config, run_async_safely
from .crawl4ai_query import crawl4ai_query, _call_crawl4ai_query_api
from .crawl4ai_ingest_url import crawl4ai_ingest_url, _call_crawl4ai_ingest_api
from .crawl4ai_ingest_and_read import crawl4ai_ingest_and_read
from .crawl4ai_two_step_crawl import crawl4ai_two_step

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables for thread management
_thread_local = threading.local()
_thread_lock = threading.Lock()

def run_async_in_thread(coro):
    """
    Run an async coroutine in a separate thread with its own event loop.
    
    Args:
        coro: The coroutine to run
        
    Returns:
        The result of the coroutine
    """
    def wrapper():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(wrapper)
        return future.result()

async def create_crawl4ai_toolset_async() -> Tuple[List[Any], Optional[AsyncExitStack]]:
    """
    Async function to create tools for Crawl4AI's API.
    
    Returns:
        Tuple[List[Any], AsyncExitStack]: The list of tools and exit stack
    """
    try:
        # Get connection parameters from environment variables
        api_url, api_token = get_crawl4ai_config()
            
        logger.info(f"Using Crawl4AI API URL: {api_url}")
        
        # Create an AsyncExitStack for resource management (empty for now)
        exit_stack = AsyncExitStack()

        # Skip trying to use decorators - go directly to manually created tools
        # Create simplest possible functions first
        
        # Create super simple functions following the pattern used in web_search_tools.py
        try:
            # Make sure the function names are correctly set
            crawl4ai_ingest_and_read.__name__ = "crawl4ai_ingest_and_read"
            crawl4ai_ingest_url.__name__ = "crawl4ai_ingest_url"
            crawl4ai_query.__name__ = "crawl4ai_query"
            crawl4ai_two_step.__name__ = "crawl4ai_two_step"
            
            # Create function tools (this works in ADK 0.3.0)
            try:
                # First try with explicit schemas for more reliable function calling
                from google.generativeai import types as genai_types
                
                # Define explicit schemas for our functions
                read_url_schema = {
                    "name": "crawl4ai_ingest_and_read",
                    "description": "Fetch a URL using Crawl4AI, show AND store content for future searching. Use this to both read and index web content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL of the webpage to crawl (e.g. 'https://example.com')"
                            },
                            "content_selectors": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "Optional CSS selectors to target specific content"
                            }
                        },
                        "required": ["url"]
                    }
                }
                
                ingest_url_schema = {
                    "name": "crawl4ai_ingest_url",
                    "description": "Ingest URLs with Crawl4AI for later searching (Step 1 of 2). Content will be stored but NOT returned in the response to save context space.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL or comma-separated list of URLs to crawl (e.g. 'https://example.com' or 'https://example.com,https://example.org')"
                            },
                            "content_selectors": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "Optional CSS selectors to target specific content"
                            },
                            "chunk_size": {
                                "type": "integer",
                                "description": "Maximum size of each chunk in characters for vector storage (default: 800)"
                            }
                        },
                        "required": ["url"]
                    }
                }
                
                query_schema = {
                    "name": "crawl4ai_query",
                    "description": "Search the Crawl4AI knowledge base (Step 2 of 2). Use this AFTER ingesting content with crawl4ai_ingest_url to search the stored web content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to look for in the Crawl4AI knowledge base"
                            }
                        },
                        "required": ["query"]
                    }
                }
                
                two_step_schema = {
                    "name": "crawl4ai_two_step",
                    "description": "A two-step crawling process: first reads a URL, then extracts and crawls all links from it. Ideal for documentation sites.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to crawl (e.g. 'https://example.com/docs')"
                            },
                            "max_links": {
                                "type": "integer",
                                "description": "Maximum number of links to crawl (default: 10)"
                            },
                            "include_external": {
                                "type": "boolean",
                                "description": "Whether to include external links (default: false)"
                            },
                            "chunk_size": {
                                "type": "integer",
                                "description": "Maximum size of each content chunk (default: 800)"
                            }
                        },
                        "required": ["url"]
                    }
                }
                
                # Try to create tools with explicit schemas
                try:
                    # Different versions of ADK FunctionTool have different signatures
                    # Try different ways of creating the tools
                    try:
                        # Try newest ADK/MCP signature
                        read_url_tool = FunctionTool(crawl4ai_ingest_and_read, schema=read_url_schema)
                        ingest_url_tool = FunctionTool(crawl4ai_ingest_url, schema=ingest_url_schema)
                        query_tool = FunctionTool(crawl4ai_query, schema=query_schema)
                        two_step_tool = FunctionTool(crawl4ai_two_step, schema=two_step_schema)
                        logger.info("Created all tools using FunctionTool with explicit schemas (new signature)")
                    except TypeError:
                        # Try older signature with function_schema
                        read_url_tool = FunctionTool(crawl4ai_ingest_and_read, function_schema=read_url_schema)
                        ingest_url_tool = FunctionTool(crawl4ai_ingest_url, function_schema=ingest_url_schema)
                        query_tool = FunctionTool(crawl4ai_query, function_schema=query_schema)
                        two_step_tool = FunctionTool(crawl4ai_two_step, function_schema=two_step_schema)
                        logger.info("Created all tools using FunctionTool with explicit schemas (older signature)")
                    logger.info("Created all tools using FunctionTool with explicit schemas")
                except Exception as e:
                    logger.warning(f"FunctionTool with schema failed: {str(e)}, trying automatic schema generation")
                    # Fall back to automatic schema generation
                    try:
                        # Try simple signature first
                        read_url_tool = FunctionTool(crawl4ai_ingest_and_read)
                        ingest_url_tool = FunctionTool(crawl4ai_ingest_url)
                        query_tool = FunctionTool(crawl4ai_query)
                        two_step_tool = FunctionTool(crawl4ai_two_step)
                        logger.info("Created all tools using FunctionTool with automatic schemas (simple signature)")
                    except TypeError:
                        # Try with explicit function parameter as a last resort
                        read_url_tool = adk_tools.Tool(name="crawl4ai_ingest_and_read", function=crawl4ai_ingest_and_read)
                        ingest_url_tool = adk_tools.Tool(name="crawl4ai_ingest_url", function=crawl4ai_ingest_url)
                        query_tool = adk_tools.Tool(name="crawl4ai_query", function=crawl4ai_query)
                        two_step_tool = adk_tools.Tool(name="crawl4ai_two_step", function=crawl4ai_two_step)
                        logger.info("Created all tools using adk_tools.Tool fallback")
                    logger.info("Created all tools using automatic schema generation")
            except Exception as e:
                logger.warning(f"FunctionTool creation failed: {str(e)}, using raw functions")
                # Fall back to raw functions if FunctionTool fails
                read_url_tool = crawl4ai_ingest_and_read
                ingest_url_tool = crawl4ai_ingest_url
                query_tool = crawl4ai_query
                two_step_tool = crawl4ai_two_step
            
            logger.info("Created crawl4ai ingest and query tools")
            
        except Exception as e:
            logger.error(f"Failed to create tools with explicit declarations: {str(e)}")
            
            # Ultimate fallback - create super simple functions with tool wrappers
            def crawl4ai_read_minimal(url):
                """Read a URL with Crawl4AI for immediate use."""
                logger.info(f"Minimal crawl4ai_ingest_and_read function called with URL: {url}")
                return {"message": f"Reading {url} as markdown", "content": f"Unable to fetch content from {url}"}
            
            def crawl4ai_ingest_minimal(url):
                """Ingest a webpage URL into Crawl4AI knowledge base."""
                logger.info(f"Minimal crawl4ai_ingest_url function called with URL: {url}")
                return {"message": f"Ingesting {url} (simulated)"}
            
            def crawl4ai_search_minimal(query):
                """Search the Crawl4AI knowledge base."""
                logger.info(f"Minimal crawl4ai_query function called with query: {query}")
                return {"message": f"Searching for: {query}", "results": []}
                
            def crawl4ai_two_step_minimal(url, max_links=10, include_external=False, chunk_size=800):
                """Two-step crawl process (read and extract links, then crawl them)."""
                logger.info(f"Minimal crawl4ai_two_step function called with URL: {url}")
                return {"message": f"Two-step crawling {url} (simulated)", "content": f"Unable to crawl {url}", "links_found": 0}
            
            # Try to create proper tools even for fallback functions
            try:
                # Try with simple FunctionTool
                read_url_tool = FunctionTool(crawl4ai_read_minimal)
                ingest_url_tool = FunctionTool(crawl4ai_ingest_minimal)
                query_tool = FunctionTool(crawl4ai_search_minimal)
                two_step_tool = FunctionTool(crawl4ai_two_step_minimal)
                logger.info("Created minimal fallback functions with FunctionTool")
            except Exception as e:
                logger.warning(f"FunctionTool failed for fallback functions: {str(e)}, using raw functions")
                # Last resort: raw functions
                read_url_tool = crawl4ai_read_minimal
                ingest_url_tool = crawl4ai_ingest_minimal
                query_tool = crawl4ai_search_minimal
                two_step_tool = crawl4ai_two_step_minimal
                logger.info("Created minimal fallback raw functions")

        # Return the tools and exit stack
        tools = [read_url_tool, ingest_url_tool, query_tool, two_step_tool]
        logger.info(f"Successfully created {len(tools)} Crawl4AI tools")
        return tools, exit_stack
        
    except Exception as e:
        logger.error(f"Failed to create Crawl4AI toolset: {str(e)}")
        return [], None

def create_crawl4ai_toolset() -> List[Any]:
    """
    Create Crawl4AI tools using ADK 0.3.0 API.
    
    Uses environment variables for configuration (CRAWL4AI_API_URL, CRAWL4AI_API_TOKEN).
    
    Returns:
        List[MCPTool]: List of Crawl4AI tools, or empty list if configuration fails
    """
    # Initialize thread local storage if needed
    with _thread_lock:
        if not hasattr(_thread_local, 'crawl4ai_exit_stacks'):
            _thread_local.crawl4ai_exit_stacks = []
    
    # Check if we're running in an event loop
    try:
        # Try to get the running loop - this will raise RuntimeError if none exists
        loop = asyncio.get_running_loop()
        logger.info("Running in existing event loop, using thread-based approach")
        
        # Run in a separate thread with its own event loop
        result = run_async_in_thread(create_crawl4ai_toolset_async())
        
        if result and result[0]:
            tools, exit_stack = result
            # Store the exit stack in thread-local storage
            if exit_stack:
                with _thread_lock:
                    _thread_local.crawl4ai_exit_stacks.append(exit_stack)
            return tools
        return []
    
    except RuntimeError:
        # No event loop is running, we can create our own
        logger.info("No event loop running, creating new one")
        try:
            # Create and set a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the async function directly
            tools, exit_stack = loop.run_until_complete(create_crawl4ai_toolset_async())
            
            # Store the exit stack if we got one
            if exit_stack:
                with _thread_lock:
                    _thread_local.crawl4ai_exit_stacks.append(exit_stack)
            
            # Return the tools
            return tools if tools else []
            
        except Exception as e:
            logger.error(f"Error creating Crawl4AI tools: {str(e)}")
            return []
        finally:
            # Don't close the loop as it might be needed by the caller
            pass

def cleanup_crawl4ai():
    """Clean up Crawl4AI resources on exit."""
    try:
        with _thread_lock:
            if hasattr(_thread_local, 'crawl4ai_exit_stacks'):
                for stack in _thread_local.crawl4ai_exit_stacks:
                    try:
                        # Run cleanup in a separate thread with its own event loop
                        async def close_async(s):
                            if hasattr(s, "aclose"):
                                await s.aclose()
                            elif hasattr(s, "close"):
                                s.close()
                        
                        run_async_in_thread(close_async(stack))
                    except Exception as e:
                        logger.error(f"Error cleaning up Crawl4AI connection: {str(e)}")
                
                # Clear the list
                _thread_local.crawl4ai_exit_stacks = []
    except Exception as e:
        logger.error(f"Error in cleanup_crawl4ai: {str(e)}")

def test_crawl4ai_connection() -> Dict[str, Any]:
    """
    Test the connection to the Crawl4AI API.
    
    Returns:
        Dictionary with test results
    """
    # Get configuration
    api_url, api_token = get_crawl4ai_config()
        
    # Test the connection with a simple request
    try:
        # Build URL for a simple status check - using the root path which returns the status
        test_url = f"{api_url}/"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Add authentication if token is provided
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        
        # Make the request
        response = requests.get(test_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse the response
        result = response.json()
        
        return {
            "success": True,
            "status": "connected",
            "api_url": api_url,
            "api_version": result.get("version", "unknown"),
            "details": result
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "status": "connection_error",
            "error": str(e),
            "api_url": api_url
        }
        
# Register cleanup function
atexit.register(cleanup_crawl4ai)

def main():
    """Command line entry point for testing."""
    print("Crawl4AI MCP Client Test\n")
    
    # Test the connection
    result = test_crawl4ai_connection()
    
    if result["success"]:
        print(f"✅ Connection successful!")
        print(f"API URL: {result.get('api_url')}")
        print(f"API Version: {result.get('api_version', 'unknown')}")
        
        # Get the tools
        tools = create_crawl4ai_toolset()
        if tools and len(tools) > 0:
            print(f"✅ Created {len(tools)} tools:")
            for tool in tools:
                print(f"  - {getattr(tool, 'name', str(tool))}")
        else:
            print("❌ Failed to create tools")
    else:
        print(f"❌ Connection failed!")
        print(f"Status: {result.get('status')}")
        print(f"Error: {result.get('error')}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
