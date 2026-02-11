#!/usr/bin/env python3
"""
MCP Standard Input/Output (stdio) Client

This module provides an MCP client implementation for connecting to MCP servers
via standard input/output streams, especially for local processes like Claude CLI.
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Import from MCP SDK
try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    from mcp.types import Tool
except ImportError:
    raise ImportError(
        "MCP Python SDK not installed. "
        "Please install required dependencies with: uv pip install mcp"
    )

logger = logging.getLogger(__name__)


class MCPStdioClient:
    """
    MCP Client for communicating with MCP servers via standard input/output streams.

    This client is designed for MCP servers that communicate via stdio, such as
    Claude CLI's 'claude mcp serve' command.
    """

    # Protocol and version constants
    PROTOCOL_VERSION = "2025-03-26"
    SUPPORTED_VERSIONS = ["2025-03-26", "2024-04-18", "2024-02-15"]

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        working_directory: Optional[str] = None,
        timeout: int = 30,
        env: Optional[Dict[str, str]] = None,
        stderr_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the MCP stdio client.

        Args:
            command: The command to execute (e.g., 'claude')
            args: Arguments for the command (e.g., ['mcp', 'serve'])
            working_directory: Working directory for the command
            timeout: Request timeout in seconds
            env: Environment variables for the process
            stderr_callback: Optional callback function for stderr output
        """
        self.command = command
        self.args = args or []
        self.working_directory = working_directory or os.getcwd()
        self.timeout = timeout
        self.env = env or os.environ.copy()
        self.stderr_callback = stderr_callback or (
            lambda x: logger.debug(f"Server stderr: {x.strip()}")
        )

        # State variables
        self.process = None
        self.session = None
        self._session_context = None
        self._async_loop = None
        self._async_thread = None
        self.tools = []
        self._tool_schemas = {}
        self.initialized = False

        # Event for synchronization
        self._ready_event = threading.Event()
        self._exit_event = threading.Event()

        logger.info(
            f"Initialized MCPStdioClient with command: {command} {' '.join(args or [])}"
        )

    def initialize(self) -> bool:
        """
        Initialize the connection to the MCP server and retrieve tools.

        Returns:
            True if initialization was successful, False otherwise
        """
        if self.initialized and self.process and self.process.poll() is None:
            logger.info("Client already initialized and process is running")
            return True

        try:
            # Start the server process
            if not self._start_process():
                logger.error("Failed to start server process")
                return False

            # Wait for the process to be ready
            if not self._ready_event.wait(timeout=10):
                logger.warning("Timed out waiting for server process to start")
                # Continue anyway, as it might still be starting

            # Start the async thread for the MCP session
            self._start_async_thread()

            # Wait for initialization to complete
            timeout = time.time() + 15
            while not self.initialized and time.time() < timeout:
                time.sleep(0.1)

            if not self.initialized:
                logger.error("Failed to initialize MCP client")
                self.stop()
                return False

            logger.info(
                f"Successfully initialized MCP client with {len(self.tools)} tools"
            )
            return True

        except Exception as e:
            logger.error(f"Error initializing MCP stdio client: {e}")
            self.stop()
            return False

    def _start_process(self) -> bool:
        """
        Start the MCP server process.

        Returns:
            True if the process started successfully, False otherwise
        """
        try:
            # Build the full command
            cmd = [self.command] + self.args
            logger.info(f"Starting MCP server process: {' '.join(cmd)}")

            # Start the process with pipes
            # Merge the process environment with any custom environment variables
            process_env = os.environ.copy()
            if self.env:
                process_env.update(self.env)

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.working_directory,
                env=process_env,
                universal_newlines=False,  # Use binary mode for proper asyncio compatibility
                bufsize=0,  # Unbuffered
            )

            # Start a thread to monitor stderr
            threading.Thread(target=self._monitor_stderr, daemon=True).start()

            logger.info(f"Started MCP server process with PID: {self.process.pid}")
            return True

        except Exception as e:
            logger.error(f"Failed to start MCP server process: {e}")
            return False

    def _monitor_stderr(self):
        """Monitor the server process stderr for output and errors."""
        if not self.process:
            return

        try:
            # Read from stderr line by line
            for line_bytes in iter(self.process.stderr.readline, b""):
                try:
                    line = line_bytes.decode("utf-8")

                    # Call the callback with the line
                    if self.stderr_callback:
                        self.stderr_callback(line)

                    # Check for ready signals
                    if any(
                        msg in line.lower()
                        for msg in ["ready", "listening", "started", "server running"]
                    ):
                        logger.info("MCP server process is ready")
                        self._ready_event.set()

                    # Check for error signals
                    if any(
                        msg in line.lower() for msg in ["error", "exception", "fatal"]
                    ):
                        logger.error(f"MCP server error: {line.strip()}")

                except UnicodeDecodeError:
                    logger.warning("Could not decode stderr line")

                # Exit if requested
                if self._exit_event.is_set():
                    break

        except Exception as e:
            logger.error(f"Error monitoring stderr: {e}")
        finally:
            logger.info("Stopped monitoring stderr")

    def _start_async_thread(self):
        """Start an async thread for the MCP session."""
        if self._async_thread and self._async_thread.is_alive():
            logger.info("Async thread is already running")
            return

        # Create and start the thread
        self._async_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._async_thread.start()
        logger.info("Started async thread for MCP session")

    def _run_async_loop(self):
        """Run the async event loop for the MCP session."""
        try:
            # Create a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._async_loop = loop

            # Run the async initialization
            loop.run_until_complete(self._initialize_async())

            # Run the event loop
            loop.run_forever()

        except Exception as e:
            logger.error(f"Error in async thread: {e}")
        finally:
            # Clean up
            try:
                if loop and loop.is_running():
                    loop.stop()
                if loop and not loop.is_closed():
                    loop.close()
            except Exception as e:
                logger.error(f"Error cleaning up async loop: {e}")

            logger.info("Async thread exiting")

    async def _initialize_async(self):
        """
        Asynchronously initialize the MCP session.
        """
        try:
            if not self.process:
                logger.error("Cannot initialize: No server process")
                return

            logger.info("Initializing MCP client session asynchronously")

            # Create the session using the stdio client from the MCP SDK
            # We need to create StdioServerParameters for existing stdin/stdout
            try:
                # We'll use a direct asyncio-based approach that doesn't depend on external libraries
                logger.info("Using direct asyncio-based MCP client")

                # Create a direct MCP client using asyncio
                class DirectMCPClient:
                    """Direct implementation of MCP client using asyncio and subprocess."""

                    def __init__(self, process):
                        self.process = process
                        self.initialized = False
                        self.message_id = 0

                    async def send_request(self, method, params=None):
                        """Send a JSON-RPC request and get a response using subprocess pipes directly."""
                        self.message_id += 1
                        request = {
                            "jsonrpc": "2.0",
                            "id": self.message_id,
                            "method": method,
                            "params": params or {},
                        }

                        # Convert request to JSON
                        request_json = json.dumps(request) + "\n"

                        # Send to stdin
                        self.process.stdin.write(request_json.encode("utf-8"))
                        self.process.stdin.flush()

                        # Read response from stdout
                        response_line = (
                            self.process.stdout.readline().decode("utf-8").strip()
                        )

                        if not response_line:
                            raise Exception(f"No response received for method {method}")

                        # Parse the response
                        try:
                            response = json.loads(response_line)
                            if "error" in response:
                                error_info = response.get("error", {})
                                raise Exception(f"Error in MCP response: {error_info}")
                            return response.get("result")
                        except json.JSONDecodeError as e:
                            raise Exception(f"Invalid JSON response: {str(e)}")

                    async def initialize(
                        self, protocol_version, capabilities, client_info
                    ):
                        """Initialize the MCP session."""
                        params = {
                            "protocolVersion": protocol_version,
                            "capabilities": capabilities,
                            "clientInfo": client_info,
                        }

                        result = await self.send_request("initialize", params)
                        self.initialized = True
                        return result

                    async def list_tools(self):
                        """List available tools."""
                        return await self.send_request("tools/list", {})

                    async def call_tool(self, tool_name, args):
                        """Call a tool on the server."""
                        params = {"name": tool_name, "inputs": args}
                        return await self.send_request("tools/call", params)

                # Create and use our direct MCP client
                self.session = DirectMCPClient(self.process)

                # Configure client capabilities
                capabilities = {
                    "completions": False,  # We don't need completion capabilities
                    "prompts": False,  # We don't need prompt management
                    "resources": False,  # We don't need resource management
                    "tools": True,  # We only need tools
                }

                # Initialize the session
                await self.session.initialize(
                    protocol_version=self.PROTOCOL_VERSION,
                    capabilities=capabilities,
                    client_info={
                        "name": "RadbotMCPClient",
                        "version": "1.0.0",
                        "protocol_version": self.PROTOCOL_VERSION,
                    },
                )
                logger.info("MCP session initialized")

                # Get list of tools
                tools_info = await self.session.list_tools()
                self._process_tools(tools_info)

                # Mark as initialized
                self.initialized = True
                logger.info(
                    f"Async initialization complete, found {len(self.tools)} tools"
                )

                # Keep the session alive until exit_event is set
                while not self._exit_event.is_set():
                    await asyncio.sleep(0.1)

                logger.info("Closing session due to exit event")

            except ImportError as e:
                logger.error(f"Import error in stdio_client: {e}")
            except Exception as e:
                logger.error(f"Error in stdio_client: {e}")
                # Log more detailed error information
                import traceback

                logger.error(f"Detailed error: {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"Error in async initialization: {e}")

    def _process_tools(self, tools_info):
        """
        Process tool information from the MCP server.

        Args:
            tools_info: Tool information from the server
        """
        from google.adk.tools import FunctionTool

        # Process the tools
        tools_list = []

        # Extract tools from the response
        if hasattr(tools_info, "tools"):
            tools_list = tools_info.tools
        elif isinstance(tools_info, list):
            tools_list = tools_info
        elif isinstance(tools_info, dict) and "tools" in tools_info:
            tools_list = tools_info["tools"]
        else:
            logger.warning(f"Unexpected tools_info format: {type(tools_info)}")
            logger.debug(f"Tools info content: {tools_info}")
            return

        logger.info(f"Processing {len(tools_list)} tools from server")

        # Process each tool
        for tool_info in tools_list:
            try:
                # Extract tool name
                tool_name = getattr(tool_info, "name", None)

                if not tool_name:
                    if isinstance(tool_info, dict) and "name" in tool_info:
                        tool_name = tool_info["name"]
                    elif isinstance(tool_info, tuple) and len(tool_info) > 0:
                        tool_name = tool_info[0]
                    else:
                        logger.warning(f"Could not extract tool name from: {tool_info}")
                        continue

                logger.info(f"Processing tool: {tool_name}")

                # Create function for this tool
                def create_tool_function(name):
                    def tool_function(**kwargs):
                        return self.call_tool(name, kwargs)

                    tool_function.__name__ = name
                    return tool_function

                function = create_tool_function(tool_name)

                # Extract schema if available
                schema = None
                if hasattr(tool_info, "inputSchema"):
                    schema = {
                        "name": tool_name,
                        "description": getattr(tool_info, "description", ""),
                        "parameters": getattr(tool_info, "inputSchema", {}),
                    }
                    self._tool_schemas[tool_name] = schema

                # Create FunctionTool
                try:
                    # Try with function_schema (ADK 0.4.0+)
                    if schema:
                        try:
                            tool = FunctionTool(
                                function=function, function_schema=schema
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

            except Exception as e:
                logger.error(f"Error processing tool: {e}")

        logger.info(f"Processed {len(self.tools)} tools")

    def stop(self):
        """
        Stop the MCP client and server process.
        """
        logger.info("Stopping MCP stdio client")

        # Signal the async thread to exit
        self._exit_event.set()

        # Wait for async thread to finish
        if self._async_thread and self._async_thread.is_alive():
            self._async_thread.join(timeout=2)

        # Terminate the process
        if self.process:
            try:
                # Send SIGTERM to the process
                self.process.terminate()

                # Wait for the process to terminate
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    logger.warning(
                        "MCP server process did not terminate gracefully, forcing kill"
                    )
                    self.process.kill()
                    self.process.wait(timeout=1)

                logger.info("MCP server process terminated")
            except Exception as e:
                logger.error(f"Error terminating MCP server process: {e}")

            self.process = None

        # Clean up other resources
        self.session = None
        self._session_context = None
        self.tools = []
        self._tool_schemas = {}
        self.initialized = False
        self._ready_event.clear()
        self._exit_event.clear()

        logger.info("MCP stdio client stopped")

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            args: Arguments for the tool

        Returns:
            Tool result or error information
        """
        # Check if initialized
        if not self.initialized or not self.session:
            if not self.initialize():
                return {
                    "error": f"Failed to initialize MCP client before calling tool {tool_name}",
                    "status": "not_initialized",
                }

        logger.info(f"Calling tool {tool_name} with args: {args}")

        # Create a result container with event for synchronization
        result_container = {"result": None, "error": None, "done": threading.Event()}

        # Define an async function to call the tool
        async def call_tool_async():
            try:
                response = await self.session.call_tool(tool_name, args)
                result_container["result"] = response
            except Exception as e:
                logger.error(f"Error calling tool {tool_name}: {e}")
                result_container["error"] = str(e)
            finally:
                result_container["done"].set()

        # Schedule the async call in the event loop
        if self._async_loop:
            asyncio.run_coroutine_threadsafe(call_tool_async(), self._async_loop)

            # Wait for the result with timeout
            if not result_container["done"].wait(timeout=self.timeout):
                return {
                    "error": f"Timeout waiting for tool {tool_name}",
                    "status": "timeout",
                }

            # Check for error
            if result_container["error"]:
                return {"error": result_container["error"], "status": "error"}

            # Process the result
            response = result_container["result"]

            # Extract the result from the MCP response
            if hasattr(response, "outputs") and response.outputs:
                # Try to get the content
                content = None
                try:
                    if hasattr(response.outputs, "content"):
                        content = response.outputs.content
                    elif (
                        isinstance(response.outputs, dict)
                        and "content" in response.outputs
                    ):
                        content = response.outputs["content"]
                except:
                    pass

                # If we have content, return it
                if content:
                    return content

                # Otherwise, return the whole outputs
                return response.outputs

            # If no outputs, return the whole response
            return response
        else:
            return {
                "error": f"No async loop available to call tool {tool_name}",
                "status": "no_loop",
            }

    def get_tools(self) -> List[Any]:
        """
        Get the list of tools available from this client.

        Returns:
            List of tools
        """
        # Initialize if not already done
        if not self.initialized:
            self.initialize()

        return self.tools

    def get_tool_schemas(self) -> Dict[str, Any]:
        """
        Get the schemas for all tools.

        Returns:
            Dict mapping tool names to schemas
        """
        return self._tool_schemas

    def __del__(self):
        """Clean up resources when the object is deleted."""
        self.stop()
