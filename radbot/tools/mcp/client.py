"""
Standard MCP client implementation for Radbot.

This module provides an MCP client implementation for connecting to MCP servers
from Radbot, based on the official MCP Python SDK with adaptations for the
Radbot framework.
"""

import logging
import json
import uuid
import asyncio
import inspect
import contextlib
from typing import Dict, Any, List, Optional, Union, Tuple, Callable

# Import from MCP SDK
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.types import Tool
    import httpx
except ImportError:
    raise ImportError(
        "MCP Python SDK not installed. "
        "Please install required dependencies with: uv pip install mcp httpx"
    )

logger = logging.getLogger(__name__)

class MCPSSEClient:
    """
    Standard MCP client for Radbot based on the MCP Python SDK.
    
    This implementation provides a reliable interface to MCP servers over
    Server-Sent Events (SSE) transport, with support for tool discovery
    and invocation.
    """
    
    # Protocol and version constants
    PROTOCOL_VERSION = "2025-03-26"
    SUPPORTED_VERSIONS = ["2025-03-26", "2024-04-18", "2024-02-15"]
    
    def __init__(self, url: str, auth_token: Optional[str] = None,
                 timeout: int = 30, headers: Optional[Dict[str, str]] = None,
                 message_endpoint: Optional[str] = None, 
                 initialization_delay: Optional[int] = None):
        """
        Initialize the MCP SSE client.
        
        Args:
            url: The URL of the MCP server
            auth_token: Optional authentication token
            timeout: Request timeout in seconds
            headers: Optional additional headers
            message_endpoint: Optional URL for sending tool invocation messages
                            (used with SSE transport)
            initialization_delay: Optional delay in milliseconds to wait after
                                connecting before sending the first request
        """
        # Normalize the URL
        self.url = self._normalize_url(url)
        self.auth_token = auth_token
        self.timeout = timeout
        self.headers = headers or {}
        self.message_endpoint = message_endpoint
        self.initialization_delay = initialization_delay
        
        # Add authorization header if token is provided
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
        
        # Add required headers for SSE
        self.headers.update({
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json"
        })
        
        # Initialize state
        self.tools = []
        self.session: Optional[ClientSession] = None
        self._session_context = None
        self._streams_context = None
        self.session_id = None
        self.server_info = {}
        self.server_version = None
        
        # For async event loop handling
        self._loop = None
        self.initialized = False
        
        logger.info(f"Initialized MCPSSEClient for {url}")
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize the URL by ensuring it has the correct scheme and no trailing slashes.
        
        Args:
            url: The URL to normalize
            
        Returns:
            Normalized URL
        """
        # Remove trailing slashes
        url = url.rstrip("/")
        
        # Ensure URL has a scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            logger.info(f"Added HTTPS scheme to URL: {url}")
        
        return url
        
    def initialize(self) -> bool:
        """
        Initialize the connection to the MCP server and retrieve tools.
        
        This method establishes a connection to the MCP server, sets up the
        client session, and discovers available tools.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        if self.initialized:
            logger.info("Client already initialized")
            return True
            
        # Use asyncio to run the async initialization
        try:
            if asyncio.get_event_loop().is_running():
                # We're already in an event loop, use create_task
                import nest_asyncio
                nest_asyncio.apply()
                
            # Create a new event loop if needed
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(self._initialize_async())
            
            # If the async initialization failed, try direct HTTP initialization as fallback
            if not result and not self.message_endpoint:
                logger.info("Async initialization failed, constructing default message endpoint")
                self.message_endpoint = f"{self.url.replace('/sse', '/messages/')}"
                if "session_id=" not in self.message_endpoint:
                    self.session_id = str(uuid.uuid4())
                    separator = '?' if '?' not in self.message_endpoint else '&'
                    self.message_endpoint = f"{self.message_endpoint}{separator}session_id={self.session_id}"
                logger.info(f"Using fallback message endpoint: {self.message_endpoint}")
                
                # Send initialization request
                logger.info("Attempting direct HTTP initialization")
                init_success = self._send_initialization_request()
                if init_success:
                    logger.info("Direct HTTP initialization succeeded")
                    self.initialized = True
                    return True
            
            self.initialized = result
            return result
        except Exception as e:
            logger.error(f"Error initializing MCP client: {e}")
            return False
            
    async def _initialize_async(self) -> bool:
        """
        Asynchronous initialization method for the MCP client.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            logger.info(f"Connecting to MCP server at {self.url}")
            
            # Create and enter the SSE client context manager
            self._streams_context = sse_client(url=self.url, headers=self.headers)
            streams = await self._streams_context.__aenter__()
            
            # Create and enter the client session context manager with proper client info
            client_info = {
                "name": "RadbotMCPClient",
                "version": "1.0.0",
                "protocol_version": self.PROTOCOL_VERSION
            }
            
            self._session_context = ClientSession(
                streams[0], 
                streams[1], 
                client_info=client_info, 
                protocol_version=self.PROTOCOL_VERSION
            )
            self.session = await self._session_context.__aenter__()
            
            # Initialize the connection with proper capabilities
            capabilities = {
                "completions": False,  # We don't need completion capabilities
                "prompts": False,      # We don't need prompt management
                "resources": False,    # We don't need resource management
                "tools": True          # We only need tools
            }
            
            await self.session.initialize(
                protocol_version=self.PROTOCOL_VERSION,
                capabilities=capabilities,
                client_info=client_info
            )
            logger.info("Session initialized")
            
            # Add delay after initialization if configured
            if self.initialization_delay:
                delay_seconds = self.initialization_delay / 1000.0
                logger.info(f"Waiting {delay_seconds}s before continuing (initialization delay)")
                await asyncio.sleep(delay_seconds)
            
            # Get list of tools
            tools_info = await self.session.list_tools()
            self._process_tools(tools_info)
            
            logger.info(f"Initialization complete, found {len(self.tools)} tools")
            return True
            
        except Exception as e:
            logger.error(f"Error in async initialization: {e}")
            
            # Clean up contexts if needed
            if self._session_context and self.session:
                try:
                    await self._session_context.__aexit__(None, None, None)
                except:
                    pass
                    
            if self._streams_context:
                try:
                    await self._streams_context.__aexit__(None, None, None)
                except:
                    pass
                    
            return False
            
    def _send_initialization_request(self) -> bool:
        """
        Send a proper initialization request to the server.
        
        This is required for MCP protocol compliance. The server expects
        an initialization request before any tool invocations.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        if not self.message_endpoint:
            logger.error("No message endpoint available for initialization")
            return False
            
        try:
            import requests
            
            # Prepare the initialization request
            init_request = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "completions": False,
                        "prompts": False,
                        "resources": False,
                        "tools": True
                    },
                    "clientInfo": {
                        "name": "RadbotMCPClient",
                        "version": "1.0.0"
                    }
                },
                "id": str(uuid.uuid4())
            }
            
            # Set up headers
            headers = {**self.headers}
            headers["Content-Type"] = "application/json"
            
            # Send the initialization request
            logger.info(f"Sending initialization request to {self.message_endpoint}")
            response = requests.post(
                self.message_endpoint,
                headers=headers,
                json=init_request,
                timeout=self.timeout
            )
            
            # Check response
            if response.status_code in [200, 202]:
                logger.info(f"Initialization request accepted: {response.status_code}")
                
                # Send list_tools request (required by MCP protocol)
                list_tools_request = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": str(uuid.uuid4())
                }
                
                logger.info(f"Sending tools/list request to {self.message_endpoint}")
                list_response = requests.post(
                    self.message_endpoint,
                    headers=headers,
                    json=list_tools_request,
                    timeout=self.timeout
                )
                
                if list_response.status_code in [200, 202]:
                    logger.info(f"Tools/list request accepted: {list_response.status_code}")
                else:
                    logger.warning(f"Tools/list request failed: {list_response.status_code}")
                    # Continue even if list_tools fails - not critical
                
                return True
            else:
                logger.error(f"Initialization request failed: {response.status_code}")
                logger.error(f"Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending initialization request: {e}")
            return False
    
    def _process_tools(self, tools_info: Any) -> None:
        """
        Process tool information from the MCP server.
        
        Handles different formats of tool information that might be
        returned by different MCP server implementations.
        
        Args:
            tools_info: The list of tools from the MCP server
        """
        from google.adk.tools import FunctionTool
        
        # Handle different response formats
        tools_list = []
        
        # Case 1: Direct list of tools
        if isinstance(tools_info, list):
            tools_list = tools_info
            
        # Case 2: Tuple format (common in some MCP servers)
        elif isinstance(tools_info, tuple):
            for item in tools_info:
                if isinstance(item, tuple) and len(item) >= 2:
                    key, value = item[0], item[1]
                    if key == 'tools' and isinstance(value, list):
                        tools_list = value
                        break
        
        # If no tools found in known formats, log warning and return
        if not tools_list:
            logger.warning(f"Couldn't parse tools from response format: {type(tools_info)}")
            return
            
        logger.info(f"Processing {len(tools_list)} tools")
        
        # Process each tool
        for tool_info in tools_list:
            try:
                # Different tools might have different formats
                
                # Case 1: Tool object with name attribute
                if hasattr(tool_info, 'name'):
                    tool_name = tool_info.name
                    logger.info(f"Processing tool: {tool_name}")
                    
                    # Create function for this tool
                    def create_tool_function(name):
                        def tool_function(**kwargs):
                            return self._call_tool(name, kwargs)
                        tool_function.__name__ = name
                        return tool_function
                        
                    function = create_tool_function(tool_name)
                    
                    # Create FunctionTool with appropriate schema
                    try:
                        if hasattr(tool_info, 'inputSchema'):
                            # Create with explicit schema
                            schema = {
                                "name": tool_name,
                                "description": getattr(tool_info, 'description', ''),
                                "parameters": getattr(tool_info, 'inputSchema', {})
                            }
                            
                            try:
                                # Try with function_schema (ADK 0.4.0+)
                                tool = FunctionTool(
                                    function=function, 
                                    function_schema=schema
                                )
                            except TypeError:
                                # Fall back to older schema parameter
                                tool = FunctionTool(function, schema=schema)
                        else:
                            # No schema, create simple tool
                            tool = FunctionTool(function)
                            
                        self.tools.append(tool)
                        logger.info(f"Added tool: {tool_name}")
                    except Exception as e:
                        logger.error(f"Error creating tool {tool_name}: {e}")
                        
                # Case 2: Tuple format (name, description, schema)
                elif isinstance(tool_info, tuple) and len(tool_info) >= 1:
                    tool_name = tool_info[0] if isinstance(tool_info[0], str) else str(tool_info[0])
                    logger.info(f"Processing tuple tool: {tool_name}")
                    
                    # Create function for this tool
                    def create_tool_function(name):
                        def tool_function(**kwargs):
                            return self._call_tool(name, kwargs)
                        tool_function.__name__ = name
                        return tool_function
                        
                    function = create_tool_function(tool_name)
                    
                    # Create schema if available
                    if len(tool_info) >= 3:
                        schema = {
                            "name": tool_name,
                            "description": tool_info[1] if len(tool_info) > 1 else "",
                            "parameters": tool_info[2] if len(tool_info) > 2 else {}
                        }
                        
                        try:
                            try:
                                # Try with function_schema (ADK 0.4.0+)
                                tool = FunctionTool(
                                    function=function, 
                                    function_schema=schema
                                )
                            except TypeError:
                                # Fall back to older schema parameter
                                tool = FunctionTool(function, schema=schema)
                                
                            self.tools.append(tool)
                            logger.info(f"Added tuple tool: {tool_name}")
                        except Exception as e:
                            logger.error(f"Error creating tuple tool {tool_name}: {e}")
                    else:
                        # No schema available
                        try:
                            tool = FunctionTool(function)
                            self.tools.append(tool)
                            logger.info(f"Added simple tuple tool: {tool_name}")
                        except Exception as e:
                            logger.error(f"Error creating simple tuple tool {tool_name}: {e}")
                            
                # Case 3: Dictionary format
                elif isinstance(tool_info, dict) and 'name' in tool_info:
                    tool_name = tool_info['name']
                    logger.info(f"Processing dict tool: {tool_name}")
                    
                    # Create function for this tool
                    def create_tool_function(name):
                        def tool_function(**kwargs):
                            return self._call_tool(name, kwargs)
                        tool_function.__name__ = name
                        return tool_function
                        
                    function = create_tool_function(tool_name)
                    
                    # Get schema from dictionary
                    schema = {
                        "name": tool_name,
                        "description": tool_info.get('description', ''),
                        "parameters": tool_info.get('inputSchema', 
                                                   tool_info.get('parameters', {}))
                    }
                    
                    try:
                        try:
                            # Try with function_schema (ADK 0.4.0+)
                            tool = FunctionTool(
                                function=function, 
                                function_schema=schema
                            )
                        except TypeError:
                            # Fall back to older schema parameter
                            tool = FunctionTool(function, schema=schema)
                            
                        self.tools.append(tool)
                        logger.info(f"Added dict tool: {tool_name}")
                    except Exception as e:
                        logger.error(f"Error creating dict tool {tool_name}: {e}")
                        
                else:
                    logger.warning(f"Unknown tool format: {type(tool_info)}")
                    
            except Exception as e:
                logger.error(f"Error processing tool: {e}")
                
        logger.info(f"Processed {len(self.tools)} tools")
        
    def _call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Call a tool on the MCP server.
        
        Args:
            tool_name: The name of the tool to call
            args: The arguments to pass to the tool
            
        Returns:
            The result of the tool call
        """
        logger.info(f"Calling tool {tool_name} with args: {args}")
        
        # If we have an active session, use it
        if self.session:
            try:
                # Run the async call in the event loop
                if asyncio.get_event_loop().is_running():
                    # We're already in an event loop, use create_task
                    import nest_asyncio
                    nest_asyncio.apply()
                    
                loop = asyncio.get_event_loop()
                result = loop.run_until_complete(self._call_tool_async(tool_name, args))
                return result
            except Exception as e:
                logger.error(f"Error calling tool via session: {e}")
                # Fall back to direct HTTP call
                
        # If we have a message endpoint, make a direct HTTP call
        if self.message_endpoint:
            return self._call_tool_http(tool_name, args)
            
        logger.error(f"No session or message endpoint available to call tool {tool_name}")
        return {
            "error": f"Failed to call tool {tool_name}",
            "message": "No session or message endpoint available"
        }
        
    async def _call_tool_async(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Call a tool on the MCP server asynchronously.
        
        Args:
            tool_name: The name of the tool to call
            args: The arguments to pass to the tool
            
        Returns:
            The result of the tool call
        """
        try:
            logger.info(f"Calling tool {tool_name} asynchronously")
            
            if not self.session:
                logger.error("No session available")
                return {
                    "error": f"Failed to call tool {tool_name}",
                    "message": "No session available"
                }
                
            # Call the tool using the session
            result = await self.session.call_tool(tool_name, args)
            logger.info(f"Tool call successful: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in async tool call: {e}")
            return {
                "error": f"Failed to call tool {tool_name}",
                "message": str(e)
            }
            
    def _call_tool_http(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Call a tool on the MCP server via direct HTTP request.
        
        Args:
            tool_name: The name of the tool to call
            args: The arguments to pass to the tool
            
        Returns:
            The result of the tool call
        """
        import requests

        try:
            endpoint_url = self.message_endpoint

            # Add session_id to endpoint URL if not already present
            if 'session_id' not in endpoint_url and self.session_id:
                separator = '?' if '?' not in endpoint_url else '&'
                endpoint_url = f"{endpoint_url}{separator}session_id={self.session_id}"
                
            logger.info(f"Calling tool {tool_name} via HTTP to {endpoint_url}")
            
            # Generate a unique ID for this request
            request_id = str(uuid.uuid4())
            
            # Prepare the request following the MCP specification
            request_data = {
                "jsonrpc": "2.0",
                "method": "tools/call",  # Standard MCP method for calling tools
                "params": {
                    "name": tool_name,
                    "arguments": args
                },
                "id": request_id
            }
            
            # Set up headers for this call
            headers = {**self.headers}
            headers["Content-Type"] = "application/json"

            # Make the request
            response = requests.post(
                endpoint_url,
                headers=headers,
                json=request_data,
                timeout=self.timeout
            )
            
            # Check response
            if response.status_code in [200, 202]:  # 200 OK or 202 Accepted
                try:
                    # For immediate JSON response (200 OK)
                    if response.status_code == 200 and response.text.strip():
                        try:
                            result = response.json()
                            
                            # Extract result from JSON-RPC wrapper
                            if "result" in result:
                                logger.info(f"Tool {tool_name} call successful (immediate result)")
                                return result.get("result")
                            elif "output" in result:
                                logger.info(f"Tool {tool_name} call successful (output format)")
                                return result.get("output")
                            elif "error" in result:
                                error_msg = result.get("error", {}).get("message", "Unknown error")
                                logger.warning(f"Tool {tool_name} returned error: {error_msg}")
                                return {
                                    "error": f"Tool {tool_name} returned error",
                                    "message": error_msg
                                }
                            else:
                                # Return the whole response
                                logger.info(f"Tool {tool_name} call successful (custom format)")
                                return result
                        except json.JSONDecodeError:
                            # Not JSON, return as text
                            logger.info(f"Non-JSON response from tool {tool_name}: {response.text}")
                            return {
                                "status": "success",
                                "result": response.text,
                                "message": "Response was not JSON format"
                            }
                    
                    # For 202 Accepted, return basic accepted response
                    if response.status_code == 202:
                        logger.info(f"Tool {tool_name} call accepted (202)")
                        if response.text.strip():
                            try:
                                # Try to parse as JSON
                                result = response.json()
                                return result
                            except:
                                # Return text content
                                return {
                                    "status": "accepted",
                                    "message": "Request was accepted and is being processed",
                                    "result": response.text
                                }
                        else:
                            # No content in response
                            return {
                                "status": "accepted",
                                "message": "Request was accepted and is being processed"
                            }
                except Exception as e:
                    logger.error(f"Error processing response for tool {tool_name}: {e}")
                    # Return basic response with the error
                    return {
                        "status": "error",
                        "message": f"Error processing response: {str(e)}",
                        "http_status": response.status_code
                    }
            else:
                logger.error(f"HTTP error: {response.status_code}")
                return {
                    "error": f"Failed to call tool {tool_name}",
                    "message": f"HTTP error: {response.status_code}",
                    "http_status": response.status_code,
                    "response": response.text[:200]  # Include start of response for debugging
                }
                
        except Exception as e:
            logger.error(f"Error calling tool via HTTP: {e}")
            return {
                "error": f"Failed to call tool {tool_name}",
                "message": str(e)
            }
            
    def discover_tools(self) -> List[str]:
        """
        Explicitly discover available tools from the server.
        
        Returns:
            List of available tool names
        """
        # If we already have tools, return their names
        if self.tools:
            return [t.name if hasattr(t, 'name') else str(t) for t in self.tools]
            
        # Try to discover tools if not already initialized
        if not self.initialized:
            self.initialize()
            if self.tools:
                return [t.name if hasattr(t, 'name') else str(t) for t in self.tools]
                
        # Try to get schema from different potential endpoints
        try:
            tool_names = []
            import requests
            
            # Try different endpoints for tools based on common patterns
            schema_endpoints = [
                "/mcp/schema",
                "/schema",
                "/mcp/tools",
                "/tools"
            ]
            
            # Extract base URL from the instance URL
            base_url = self.url
            if "/mcp/sse" in base_url:
                base_url = base_url.split("/mcp/sse")[0]
            elif "/sse" in base_url:
                base_url = base_url.split("/sse")[0]
            elif base_url.endswith("/"):
                base_url = base_url[:-1]
                
            logger.info(f"Base URL for schema discovery: {base_url}")
            
            for endpoint in schema_endpoints:
                schema_url = f"{base_url}{endpoint}"
                logger.info(f"Fetching schema from {schema_url}")
                
                try:
                    schema_response = requests.get(
                        schema_url,
                        headers={**self.headers, "Accept": "application/json"},
                        timeout=self.timeout
                    )
                    
                    if schema_response.status_code == 200:
                        try:
                            schema_data = schema_response.json()
                            
                            # Handle different schema formats
                            if "tools" in schema_data and isinstance(schema_data["tools"], list):
                                for tool in schema_data["tools"]:
                                    if "name" in tool:
                                        tool_names.append(tool["name"])
                                        logger.info(f"Discovered tool from schema: {tool['name']}")
                                # If we found tools, break the loop
                                if tool_names:
                                    break
                            elif "functions" in schema_data and isinstance(schema_data["functions"], list):
                                for func in schema_data["functions"]:
                                    if "name" in func:
                                        tool_names.append(func["name"])
                                        logger.info(f"Discovered function tool from schema: {func['name']}")
                                # If we found functions, break the loop
                                if tool_names:
                                    break
                            # Handle array root response
                            elif isinstance(schema_data, list):
                                for item in schema_data:
                                    if isinstance(item, dict) and "name" in item:
                                        tool_names.append(item["name"])
                                        logger.info(f"Discovered tool from array schema: {item['name']}")
                                # If we found tools, break the loop
                                if tool_names:
                                    break
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in schema response from {schema_url}")
                except Exception as e:
                    logger.warning(f"Error fetching schema from {schema_url}: {e}")
                    
            return tool_names
                
        except Exception as e:
            logger.error(f"Error discovering tools: {e}")
            return []
        
    def get_tools(self) -> List:
        """
        Get the list of tools from this client.
        
        Returns:
            List of tools
        """
        # Initialize if not already done
        if not self.initialized:
            self.initialize()
            
        return self.tools
        
    def __del__(self):
        """
        Clean up resources when the client is deleted.
        """
        # Close any open async sessions/contexts
        if self.session and self._session_context:
            # We need to close the session in the event loop
            try:
                if asyncio.get_event_loop().is_running():
                    # We're already in an event loop
                    import nest_asyncio
                    nest_asyncio.apply()
                    
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._close_session())
            except Exception as e:
                logger.warning(f"Could not close session in event loop: {e}")
                
    async def _close_session(self):
        """
        Close the session and clean up resources.
        """
        if self._session_context and self.session:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing session context: {e}")
                
        if self._streams_context:
            try:
                await self._streams_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing streams context: {e}")
                
        self.session = None
        self._session_context = None
        self._streams_context = None
        self.initialized = False