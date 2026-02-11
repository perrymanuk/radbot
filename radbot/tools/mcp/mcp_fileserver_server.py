#!/usr/bin/env python3
"""
MCP Fileserver Server

This script implements a standalone MCP server that provides filesystem operations.
It uses the model-context-protocol library to create an MCP server and exposes
filesystem operations as tools.

Usage:
    python -m radbot.tools.mcp_fileserver_server /path/to/root/directory

Example:
    python -m radbot.tools.mcp_fileserver_server ~/data
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import mcp.server.stdio

# Import MCP server components
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FileServerMCP:
    """
    MCP server implementation for filesystem operations.

    This class handles file operations while enforcing security constraints
    like root directory isolation and operation restrictions.
    """

    def __init__(
        self, root_dir: str, allow_write: bool = False, allow_delete: bool = False
    ):
        """
        Initialize the FileServerMCP.

        Args:
            root_dir: Root directory for filesystem operations
            allow_write: Allow write operations
            allow_delete: Allow delete operations
        """
        self.root_dir = os.path.abspath(os.path.expanduser(root_dir))
        self.allow_write = allow_write
        self.allow_delete = allow_delete

        logger.info(f"Initializing FileServerMCP with root_dir: {self.root_dir}")
        logger.info(
            f"Write operations: {'Enabled' if self.allow_write else 'Disabled'}"
        )
        logger.info(
            f"Delete operations: {'Enabled' if self.allow_delete else 'Disabled'}"
        )

        # Check if the root directory exists
        if not os.path.isdir(self.root_dir):
            logger.error(f"Root directory does not exist: {self.root_dir}")
            raise ValueError(f"Root directory does not exist: {self.root_dir}")

    def _validate_path(self, path: str) -> str:
        """
        Validate that a path is within the root directory.

        Args:
            path: Relative path to validate

        Returns:
            Absolute path if valid

        Raises:
            ValueError: If path is outside root directory
        """
        # Handle empty or root path
        if not path or path == "/" or path == ".":
            return self.root_dir

        # Remove leading / for consistency
        if path.startswith("/"):
            path = path[1:]

        # Combine with root directory
        full_path = os.path.abspath(os.path.join(self.root_dir, path))

        # Check if path is within root directory
        if not full_path.startswith(self.root_dir):
            logger.warning(f"Attempted access outside root directory: {path}")
            raise ValueError(f"Path is outside root directory: {path}")

        return full_path

    def _get_relative_path(self, full_path: str) -> str:
        """
        Get the relative path from the root directory.

        Args:
            full_path: Absolute path

        Returns:
            Relative path from root directory
        """
        return os.path.relpath(full_path, self.root_dir)

    def _format_file_info(self, full_path: str) -> Dict[str, Any]:
        """
        Get formatted file information.

        Args:
            full_path: Absolute path to file or directory

        Returns:
            Dictionary with file information
        """
        stat_info = os.stat(full_path)
        rel_path = self._get_relative_path(full_path)

        # Format timestamps
        mtime = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
        ctime = datetime.fromtimestamp(stat_info.st_ctime).isoformat()
        atime = datetime.fromtimestamp(stat_info.st_atime).isoformat()

        return {
            "path": rel_path,
            "name": os.path.basename(full_path),
            "type": "directory" if os.path.isdir(full_path) else "file",
            "size": stat_info.st_size,
            "created": ctime,
            "modified": mtime,
            "accessed": atime,
            "permissions": stat_info.st_mode & 0o777,
        }

    async def list_files(self, path: str = "") -> List[Dict[str, Any]]:
        """
        List files and directories in a path.

        Args:
            path: Path to list (relative to root directory)

        Returns:
            List of file and directory information
        """
        try:
            full_path = self._validate_path(path)

            # Check if path exists
            if not os.path.exists(full_path):
                logger.warning(f"Path not found: {path}")
                raise FileNotFoundError(f"Path not found: {path}")

            # Check if path is a directory
            if not os.path.isdir(full_path):
                logger.warning(f"Path is not a directory: {path}")
                raise ValueError(f"Path is not a directory: {path}")

            # Get directory contents
            contents = []
            for item in os.listdir(full_path):
                item_path = os.path.join(full_path, item)
                contents.append(self._format_file_info(item_path))

            return contents
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}")
            raise

    async def read_file(self, path: str) -> str:
        """
        Read the contents of a file.

        Args:
            path: Path to the file (relative to root directory)

        Returns:
            Contents of the file
        """
        try:
            full_path = self._validate_path(path)

            # Check if path exists
            if not os.path.exists(full_path):
                logger.warning(f"File not found: {path}")
                raise FileNotFoundError(f"File not found: {path}")

            # Check if path is a file
            if not os.path.isfile(full_path):
                logger.warning(f"Path is not a file: {path}")
                raise ValueError(f"Path is not a file: {path}")

            # Read file contents
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            return content
        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            raise

    async def write_file(
        self, path: str, content: str, append: bool = False
    ) -> Dict[str, Any]:
        """
        Write content to a file.

        Args:
            path: Path to the file (relative to root directory)
            content: Content to write
            append: Append to file instead of overwriting

        Returns:
            Dictionary with operation result
        """
        if not self.allow_write:
            logger.warning("Write operations are disabled")
            raise PermissionError("Write operations are disabled")

        try:
            full_path = self._validate_path(path)

            # Check if directory exists
            dir_path = os.path.dirname(full_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

            # Write file
            mode = "a" if append else "w"
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)

            return {
                "path": path,
                "operation": "append" if append else "write",
                "status": "success",
                "size": len(content),
            }
        except Exception as e:
            logger.error(f"Error writing file: {str(e)}")
            raise

    async def delete_file(self, path: str) -> Dict[str, Any]:
        """
        Delete a file or directory.

        Args:
            path: Path to the file or directory (relative to root directory)

        Returns:
            Dictionary with operation result
        """
        if not self.allow_delete:
            logger.warning("Delete operations are disabled")
            raise PermissionError("Delete operations are disabled")

        try:
            full_path = self._validate_path(path)

            # Check if path exists
            if not os.path.exists(full_path):
                logger.warning(f"Path not found: {path}")
                raise FileNotFoundError(f"Path not found: {path}")

            # Delete file or directory
            if os.path.isdir(full_path):
                import shutil

                shutil.rmtree(full_path)
                item_type = "directory"
            else:
                os.remove(full_path)
                item_type = "file"

            return {
                "path": path,
                "operation": "delete",
                "status": "success",
                "type": item_type,
            }
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise

    async def get_file_info(self, path: str) -> Dict[str, Any]:
        """
        Get information about a file or directory.

        Args:
            path: Path to the file or directory (relative to root directory)

        Returns:
            Dictionary with file information
        """
        try:
            full_path = self._validate_path(path)

            # Check if path exists
            if not os.path.exists(full_path):
                logger.warning(f"Path not found: {path}")
                raise FileNotFoundError(f"Path not found: {path}")

            return self._format_file_info(full_path)
        except Exception as e:
            logger.error(f"Error getting file info: {str(e)}")
            raise

    async def copy_file(self, source: str, destination: str) -> Dict[str, Any]:
        """
        Copy a file or directory.

        Args:
            source: Source path (relative to root directory)
            destination: Destination path (relative to root directory)

        Returns:
            Dictionary with operation result
        """
        if not self.allow_write:
            logger.warning("Write operations are disabled")
            raise PermissionError("Write operations are disabled")

        try:
            src_path = self._validate_path(source)
            dst_path = self._validate_path(destination)

            # Check if source exists
            if not os.path.exists(src_path):
                logger.warning(f"Source not found: {source}")
                raise FileNotFoundError(f"Source not found: {source}")

            # Create destination directory if it doesn't exist
            dst_dir = os.path.dirname(dst_path)
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)

            # Copy file or directory
            if os.path.isdir(src_path):
                import shutil

                shutil.copytree(src_path, dst_path)
                item_type = "directory"
            else:
                import shutil

                shutil.copy2(src_path, dst_path)
                item_type = "file"

            return {
                "source": source,
                "destination": destination,
                "operation": "copy",
                "status": "success",
                "type": item_type,
            }
        except Exception as e:
            logger.error(f"Error copying file: {str(e)}")
            raise

    async def move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """
        Move or rename a file or directory.

        Args:
            source: Source path (relative to root directory)
            destination: Destination path (relative to root directory)

        Returns:
            Dictionary with operation result
        """
        if not self.allow_write:
            logger.warning("Write operations are disabled")
            raise PermissionError("Write operations are disabled")

        try:
            src_path = self._validate_path(source)
            dst_path = self._validate_path(destination)

            # Check if source exists
            if not os.path.exists(src_path):
                logger.warning(f"Source not found: {source}")
                raise FileNotFoundError(f"Source not found: {source}")

            # Create destination directory if it doesn't exist
            dst_dir = os.path.dirname(dst_path)
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)

            # Move file or directory
            import shutil

            shutil.move(src_path, dst_path)
            item_type = "directory" if os.path.isdir(dst_path) else "file"

            return {
                "source": source,
                "destination": destination,
                "operation": "move",
                "status": "success",
                "type": item_type,
            }
        except Exception as e:
            logger.error(f"Error moving file: {str(e)}")
            raise


def setup_mcp_server(
    root_dir: str, allow_write: bool = False, allow_delete: bool = False
) -> Tuple[Server, FileServerMCP]:
    """
    Set up the MCP server for filesystem operations.

    Args:
        root_dir: Root directory for filesystem operations
        allow_write: Allow write operations
        allow_delete: Allow delete operations

    Returns:
        Tuple of (Server, FileServerMCP)
    """
    logger.info(f"Setting up MCP server for filesystem operations")
    logger.info(f"Root directory: {root_dir}")
    logger.info(f"Allow write: {allow_write}")
    logger.info(f"Allow delete: {allow_delete}")

    # Create the file server
    fs = FileServerMCP(root_dir, allow_write, allow_delete)

    # Create MCP server
    app = Server("fileserver-mcp-server")

    # Define MCP tools
    @app.list_tools()
    async def list_tools() -> List[mcp_types.Tool]:
        """MCP handler to list available tools."""
        logger.info("MCP Server: Received list_tools request")

        tools = [
            mcp_types.Tool(
                name="list_files",
                description="List files and directories in a path",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to list (relative to root directory)",
                        }
                    },
                },
            ),
            mcp_types.Tool(
                name="read_file",
                description="Read the contents of a file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file (relative to root directory)",
                        }
                    },
                    "required": ["path"],
                },
            ),
            mcp_types.Tool(
                name="get_file_info",
                description="Get information about a file or directory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file or directory (relative to root directory)",
                        }
                    },
                    "required": ["path"],
                },
            ),
        ]

        # Add write operations if enabled
        if fs.allow_write:
            tools.extend(
                [
                    mcp_types.Tool(
                        name="write_file",
                        description="Write content to a file",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the file (relative to root directory)",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Content to write",
                                },
                                "append": {
                                    "type": "boolean",
                                    "description": "Append to file instead of overwriting",
                                },
                            },
                            "required": ["path", "content"],
                        },
                    ),
                    mcp_types.Tool(
                        name="copy_file",
                        description="Copy a file or directory",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "source": {
                                    "type": "string",
                                    "description": "Source path (relative to root directory)",
                                },
                                "destination": {
                                    "type": "string",
                                    "description": "Destination path (relative to root directory)",
                                },
                            },
                            "required": ["source", "destination"],
                        },
                    ),
                    mcp_types.Tool(
                        name="move_file",
                        description="Move or rename a file or directory",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "source": {
                                    "type": "string",
                                    "description": "Source path (relative to root directory)",
                                },
                                "destination": {
                                    "type": "string",
                                    "description": "Destination path (relative to root directory)",
                                },
                            },
                            "required": ["source", "destination"],
                        },
                    ),
                ]
            )

        # Add delete operations if enabled
        if fs.allow_delete:
            tools.append(
                mcp_types.Tool(
                    name="delete_file",
                    description="Delete a file or directory",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file or directory (relative to root directory)",
                            }
                        },
                        "required": ["path"],
                    },
                )
            )

        logger.info(f"MCP Server: Advertising {len(tools)} tools")
        return tools

    @app.call_tool()
    async def call_tool(
        name: str, arguments: Dict[str, Any]
    ) -> List[mcp_types.TextContent]:
        """MCP handler to execute a tool call."""
        logger.info(
            f"MCP Server: Received call_tool request for '{name}' with args: {arguments}"
        )

        try:
            # Route to appropriate method
            if name == "list_files":
                path = arguments.get("path", "")
                result = await fs.list_files(path)
                return [
                    mcp_types.TextContent(
                        type="text", text=json.dumps(result, indent=2)
                    )
                ]

            elif name == "read_file":
                path = arguments.get("path", "")
                if not path:
                    raise ValueError("Path is required")

                result = await fs.read_file(path)
                return [mcp_types.TextContent(type="text", text=result)]

            elif name == "write_file":
                path = arguments.get("path", "")
                content = arguments.get("content", "")
                append = arguments.get("append", False)

                if not path:
                    raise ValueError("Path is required")
                if content is None:
                    raise ValueError("Content is required")

                result = await fs.write_file(path, content, append)
                return [
                    mcp_types.TextContent(
                        type="text", text=json.dumps(result, indent=2)
                    )
                ]

            elif name == "delete_file":
                path = arguments.get("path", "")
                if not path:
                    raise ValueError("Path is required")

                result = await fs.delete_file(path)
                return [
                    mcp_types.TextContent(
                        type="text", text=json.dumps(result, indent=2)
                    )
                ]

            elif name == "get_file_info":
                path = arguments.get("path", "")
                if not path:
                    raise ValueError("Path is required")

                result = await fs.get_file_info(path)
                return [
                    mcp_types.TextContent(
                        type="text", text=json.dumps(result, indent=2)
                    )
                ]

            elif name == "copy_file":
                source = arguments.get("source", "")
                destination = arguments.get("destination", "")

                if not source:
                    raise ValueError("Source is required")
                if not destination:
                    raise ValueError("Destination is required")

                result = await fs.copy_file(source, destination)
                return [
                    mcp_types.TextContent(
                        type="text", text=json.dumps(result, indent=2)
                    )
                ]

            elif name == "move_file":
                source = arguments.get("source", "")
                destination = arguments.get("destination", "")

                if not source:
                    raise ValueError("Source is required")
                if not destination:
                    raise ValueError("Destination is required")

                result = await fs.move_file(source, destination)
                return [
                    mcp_types.TextContent(
                        type="text", text=json.dumps(result, indent=2)
                    )
                ]

            else:
                logger.warning(f"Unknown tool: {name}")
                raise ValueError(f"Tool '{name}' not implemented")

        except Exception as e:
            logger.error(f"Error executing tool '{name}': {str(e)}")

            # Map exception types to error types
            error_type = "EXECUTION_ERROR"
            if isinstance(e, FileNotFoundError):
                error_type = "FILE_NOT_FOUND"
            elif isinstance(e, PermissionError):
                error_type = "PERMISSION_DENIED"
            elif isinstance(e, ValueError):
                error_type = "INVALID_ARGUMENT"

            # Re-raise the exception with appropriate error message
            raise Exception(f"{error_type}: {str(e)}")

    return app, fs


async def start_server_async(
    exit_stack, root_dir: str, allow_write: bool = False, allow_delete: bool = False
):
    """
    Start the MCP server asynchronously.

    Args:
        exit_stack: AsyncExitStack for resource management
        root_dir: Root directory for filesystem operations
        allow_write: Allow write operations
        allow_delete: Allow delete operations

    Returns:
        The server process
    """
    app, _ = setup_mcp_server(root_dir, allow_write, allow_delete)

    stdio_server_context = await exit_stack.enter_async_context(
        mcp.server.stdio.stdio_server()
    )
    read_stream, write_stream = stdio_server_context

    logger.info("MCP Server starting...")
    # Start the server
    init_options = InitializationOptions(
        server_name=app.name,
        server_version="0.1.0",
        capabilities=app.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )

    # Run the server in a task to avoid blocking
    server_task = asyncio.create_task(app.run(read_stream, write_stream, init_options))

    # Return the task so it can be managed externally
    return server_task


def start_server(root_dir: str, allow_write: bool = False, allow_delete: bool = False):
    """
    Start the MCP server.

    Args:
        root_dir: Root directory for filesystem operations
        allow_write: Allow write operations
        allow_delete: Allow delete operations
    """
    try:
        # Create an exit stack for standalone mode
        async def run_standalone():
            from contextlib import AsyncExitStack

            async with AsyncExitStack() as exit_stack:
                await start_server_async(
                    exit_stack, root_dir, allow_write, allow_delete
                )
                # Block indefinitely (or until interrupted)
                await asyncio.Future()

        asyncio.run(run_standalone())
    except KeyboardInterrupt:
        logger.info("MCP Server interrupted by user")
    except Exception as e:
        logger.error(f"MCP Server error: {str(e)}")
    finally:
        logger.info("MCP Server exited")


def main():
    """Command line entry point."""
    parser = argparse.ArgumentParser(description="MCP Fileserver Server")
    parser.add_argument("root_dir", help="Root directory for filesystem operations")
    parser.add_argument(
        "--allow-write", action="store_true", help="Allow write operations"
    )
    parser.add_argument(
        "--allow-delete", action="store_true", help="Allow delete operations"
    )

    args = parser.parse_args()

    print(f"Starting MCP Fileserver Server")
    print(f"Root directory: {args.root_dir}")
    print(f"Allow write: {args.allow_write}")
    print(f"Allow delete: {args.allow_delete}")

    start_server(args.root_dir, args.allow_write, args.allow_delete)

    return 0


if __name__ == "__main__":
    sys.exit(main())
