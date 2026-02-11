import asyncio
import atexit
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from threading import RLock, Thread, local
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Import from ADK 0.3.0 locations
from google.adk.events import Event
from google.adk.tools import FunctionTool
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Tool as MCPTool

from radbot.tools.mcp.mcp_fileserver_server import (
    start_server,
    start_server_async,
)

logger = logging.getLogger(__name__)

_global_exit_stack: Optional[AsyncExitStack] = None
_global_lock = RLock()
_thread_local = local()


def cleanup_fileserver_sync() -> None:
    """Cleanup function to be called on exit.
    Properly closes the MCP server and any associated resources.
    """
    global _global_exit_stack

    logger.info("Cleaning up MCP fileserver resources")

    # Handle global exit stack
    if _global_exit_stack is not None:
        try:
            # Close the AsyncExitStack synchronously
            asyncio.run(_global_exit_stack.aclose())
            logger.info("Closed global exit stack")
        except Exception as e:
            logger.warning(f"Error closing global exit stack: {e}")
        finally:
            _global_exit_stack = None

    # Handle thread-local exit stacks
    if hasattr(_thread_local, "mcp_exit_stacks"):
        for thread_id, exit_stack in _thread_local.mcp_exit_stacks.items():
            try:
                asyncio.run(exit_stack.aclose())
                logger.info(f"Closed thread-local exit stack for thread {thread_id}")
            except Exception as e:
                logger.warning(
                    f"Error closing thread-local exit stack for thread {thread_id}: {e}"
                )

    logger.info("MCP fileserver cleanup completed")


def get_mcp_fileserver_config() -> Tuple[str, bool, bool]:
    """Get the MCP fileserver configuration from environment variables."""
    root_dir = os.environ.get("MCP_FS_ROOT_DIR", os.path.expanduser("~"))
    allow_write = os.environ.get("MCP_FS_ALLOW_WRITE", "false").lower() == "true"
    allow_delete = os.environ.get("MCP_FS_ALLOW_DELETE", "false").lower() == "true"
    logger.info(
        f"MCP Fileserver Config: root_dir={root_dir}, allow_write={allow_write}, allow_delete={allow_delete}"
    )
    return root_dir, allow_write, allow_delete


async def _create_fileserver_toolset_async() -> List[FunctionTool]:
    """Create the MCP fileserver toolset asynchronously."""
    global _global_exit_stack

    root_dir, allow_write, allow_delete = get_mcp_fileserver_config()

    # Initialize thread-local storage if not already done
    if not hasattr(_thread_local, "mcp_exit_stacks"):
        _thread_local.mcp_exit_stacks = {}

    # Create an AsyncExitStack to manage resources
    exit_stack = AsyncExitStack()
    current_thread_id = threading.get_ident()
    _thread_local.mcp_exit_stacks[current_thread_id] = exit_stack

    try:
        # Start the server and get the tools
        server_process = await start_server_async(
            exit_stack, root_dir, allow_write, allow_delete
        )

        # Create and initialize the client session
        # Use a different command for stdio_client to avoid starting a Python process
        # that might interfere with our existing server
        client_transport = await exit_stack.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command="/bin/cat",  # Simple command that will be replaced by the server's stdio
                    args=[],
                    env={},
                )
            )
        )
        client = await exit_stack.enter_async_context(ClientSession(*client_transport))
        await client.initialize()

        # Set the global exit stack for cleanup if needed
        with _global_lock:
            if _global_exit_stack is None:
                _global_exit_stack = exit_stack

        # Create wrapper functions for each tool
        tools = []
        mcp_tools = await client.list_tools()

        for mcp_tool in mcp_tools.tools:
            # Capture tool name in closure
            tool_name = mcp_tool.name

            # Create a wrapper function for this specific tool
            def make_tool_func(tool_name):
                # Use variable number of keyword arguments to handle any parameter schema
                def tool_func(**kwargs):
                    # Forward the call to our handler
                    return handle_fileserver_tool_call(
                        tool_name, kwargs
                    ).function_call_event

                # Set the docstring based on the tool description
                tool_func.__doc__ = mcp_tool.description
                # Set the name to match the original tool
                tool_func.__name__ = tool_name

                return tool_func

            # Create a FunctionTool from our wrapper function
            func = make_tool_func(tool_name)
            tools.append(FunctionTool(func=func))

        logger.info(
            f"Successfully created MCP fileserver toolset with {len(tools)} tools"
        )
        return tools
    except Exception as e:
        # Clean up if there's an error
        logger.error(f"Error creating MCP fileserver toolset: {e}")
        await exit_stack.aclose()
        _thread_local.mcp_exit_stacks.pop(current_thread_id, None)
        raise


def run_async_in_thread(coro):
    """Run an asynchronous coroutine in a separate thread."""

    # Create a new event loop for the executor to prevent conflicts
    def run_with_new_loop(coro):
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_with_new_loop, coro)
        return future.result()


def create_fileserver_toolset() -> List[FunctionTool]:
    """Create the MCP fileserver toolset."""
    try:
        # Special debug for when we're already in an event loop
        try:
            asyncio.get_running_loop()
            logger.warning(
                "SPECIAL DEBUG: Running in existing event loop, cannot create fileserver in async context"
            )
            logger.warning("This likely means you're using this in an async context")
            # Instead of using the complex async method in a thread, which can hang,
            # let's create a simplified set of tool stubs with proper descriptions
            # These will be replaced with the actual implementation when called
            logger.info("Creating simplified MCP fileserver tool stubs")

            # For ADK 0.3.0+, we need to use the function-based constructor, not keyword arguments
            # Create wrapper functions for each tool type

            def list_files_func(path: str = "") -> dict:
                """List files and directories in a path."""
                return handle_fileserver_tool_call(
                    "list_files", {"path": path}
                ).function_call_event

            def read_file_func(path: str) -> dict:
                """Read the contents of a file."""
                return handle_fileserver_tool_call(
                    "read_file", {"path": path}
                ).function_call_event

            def get_file_info_func(path: str) -> dict:
                """Get information about a file or directory."""
                return handle_fileserver_tool_call(
                    "get_file_info", {"path": path}
                ).function_call_event

            # Create the basic tools
            tools = [
                FunctionTool(func=list_files_func),
                FunctionTool(func=read_file_func),
                FunctionTool(func=get_file_info_func),
            ]

            # Add write operations if enabled
            root_dir, allow_write, allow_delete = get_mcp_fileserver_config()
            if allow_write:
                # Add write tool functions
                def write_file_func(
                    path: str, content: str, append: bool = False
                ) -> dict:
                    """Write content to a file."""
                    return handle_fileserver_tool_call(
                        "write_file",
                        {"path": path, "content": content, "append": append},
                    ).function_call_event

                def copy_file_func(source: str, destination: str) -> dict:
                    """Copy a file or directory."""
                    return handle_fileserver_tool_call(
                        "copy_file", {"source": source, "destination": destination}
                    ).function_call_event

                def move_file_func(source: str, destination: str) -> dict:
                    """Move or rename a file or directory."""
                    return handle_fileserver_tool_call(
                        "move_file", {"source": source, "destination": destination}
                    ).function_call_event

                # Add the write tools
                tools.extend(
                    [
                        FunctionTool(func=write_file_func),
                        FunctionTool(func=copy_file_func),
                        FunctionTool(func=move_file_func),
                    ]
                )

            # Add delete operations if enabled
            if allow_delete:

                def delete_file_func(path: str) -> dict:
                    """Delete a file or directory."""
                    return handle_fileserver_tool_call(
                        "delete_file", {"path": path}
                    ).function_call_event

                tools.append(FunctionTool(func=delete_file_func))

            logger.info(f"Created {len(tools)} MCP fileserver tool stubs")
            return tools
        except RuntimeError:
            # No event loop running, we can create our own
            return asyncio.run(_create_fileserver_toolset_async())
    except Exception as e:
        logger.warning(f"Cannot create fileserver toolset: {e}")
        # Return empty list as fallback
        return []


async def _handle_fileserver_tool_call_async(
    tool_name: str, params: Dict[str, Any]
) -> Event:
    """Handle a fileserver tool call asynchronously."""
    try:
        # Get thread-local exit stack or create a new one
        current_thread_id = threading.get_ident()
        if (
            not hasattr(_thread_local, "mcp_exit_stacks")
            or current_thread_id not in _thread_local.mcp_exit_stacks
        ):
            # Initialize thread-local storage if not already done
            if not hasattr(_thread_local, "mcp_exit_stacks"):
                _thread_local.mcp_exit_stacks = {}

            # Create an AsyncExitStack to manage resources
            exit_stack = AsyncExitStack()
            _thread_local.mcp_exit_stacks[current_thread_id] = exit_stack

            # Start the server
            root_dir, allow_write, allow_delete = get_mcp_fileserver_config()
            await start_server_async(exit_stack, root_dir, allow_write, allow_delete)
        else:
            exit_stack = _thread_local.mcp_exit_stacks[current_thread_id]

        # Create and initialize the client session
        client_transport = await exit_stack.enter_async_context(
            stdio_client(StdioServerParameters(command="python"))
        )
        async with ClientSession(*client_transport) as client:
            # Initialize the client
            await client.initialize()

            # Call the tool
            response = await client.call_tool(tool_name, params)

            # ADK 0.3.0 - Create a proper Event with function_response
            return Event(function_call_event={"name": tool_name, "response": response})
    except Exception as e:
        logger.error(f"Error handling fileserver tool call: {e}")
        return Event(
            function_call_event={
                "name": tool_name,
                "error": f"Error handling fileserver tool call: {e}",
            }
        )


def handle_fileserver_tool_call(tool_name: str, params: Dict[str, Any]) -> Event:
    """Handle a fileserver tool call."""
    try:
        # Check if we're already in an event loop
        try:
            asyncio.get_running_loop()
            # Run in a separate thread to avoid event loop conflicts
            return run_async_in_thread(
                partial(_handle_fileserver_tool_call_async, tool_name, params)
            )
        except RuntimeError:
            # No event loop running, we can create our own
            return asyncio.run(_handle_fileserver_tool_call_async(tool_name, params))
    except Exception as e:
        logger.error(f"Error handling fileserver tool call: {e}")
        return Event(
            function_call_event={
                "name": tool_name,
                "error": f"Error handling fileserver tool call: {e}",
            }
        )


# Register the cleanup function to be called on exit
atexit.register(cleanup_fileserver_sync)
