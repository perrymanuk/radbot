"""
Specialized tools for the Axel execution agent.

This module provides tools specific to the execution agent's needs,
focused on code execution, testing, and implementation tasks.
"""

import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Union

from google.adk.tools.function_tool import FunctionTool

from radbot.filesystem.tools import copy as copy_file
from radbot.filesystem.tools import edit_file as edit_file_func
from radbot.filesystem.tools import (
    get_info,
    list_directory,
    read_file,
    search,
    write_file,
)
from radbot.tools.shell.shell_command import execute_shell_command

# Set up logging
logger = logging.getLogger(__name__)


def code_execution_tool(code: str, description: str = "") -> Dict[str, Any]:
    """
    Execute Python code safely in a controlled environment.

    This is a wrapper around the execute_shell_command function that
    specifically handles Python code execution with safety measures.

    Args:
        code: The Python code to execute
        description: Optional description of what the code does

    Returns:
        Dict[str, Any]: The execution result with stdout, stderr, and exit_code
    """
    # Create a temporary file for the code
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(code.encode("utf-8"))
        temp_file = f.name

    try:
        # Execute the code with a timeout to prevent infinite loops
        result = execute_shell_command(
            command="python", arguments=[temp_file], timeout=30  # 30 second timeout
        )

        # Add the code to the result for reference
        result["code"] = code
        if description:
            result["description"] = description

        return result
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def run_tests(test_file: str, test_pattern: Optional[str] = None) -> Dict[str, Any]:
    """
    Run tests using pytest.

    Args:
        test_file: Path to the test file to run
        test_pattern: Optional pattern to filter tests

    Returns:
        Dict[str, Any]: The test results
    """
    # Build the command with appropriate options
    command = f"pytest {test_file} -v"
    if test_pattern:
        command += f" -k '{test_pattern}'"

    # Run the command
    return execute_shell_command(
        command=command, timeout=60, cwd=os.getcwd()  # 60 second timeout
    )


def validate_code(file_path: str) -> Dict[str, Any]:
    """
    Validate Python code for syntax and style issues.

    This runs pylint on the specified file to check for code quality issues.

    Args:
        file_path: Path to the Python file to validate

    Returns:
        Dict[str, Any]: The validation results
    """
    # Ensure the file exists
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}", "exit_code": 1}

    # Run pylint on the file
    return execute_shell_command(
        command=f"pylint {file_path}", timeout=30, cwd=os.getcwd()  # 30 second timeout
    )


def generate_documentation(
    file_path: str, output_format: str = "markdown"
) -> Dict[str, Any]:
    """
    Generate documentation for a Python file.

    Args:
        file_path: Path to the Python file to document
        output_format: Output format (markdown or rst)

    Returns:
        Dict[str, Any]: The generated documentation
    """
    # Ensure the file exists
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}", "exit_code": 1}

    # Use pydoc to generate documentation
    format_arg = "html" if output_format == "html" else "text"

    result = execute_shell_command(
        command=(
            f"pydoc -w {file_path}" if format_arg == "html" else f"pydoc {file_path}"
        ),
        timeout=30,  # 30 second timeout
        cwd=os.getcwd(),
    )

    # If HTML was generated, read the content
    if format_arg == "html":
        html_file = os.path.basename(file_path).replace(".py", ".html")
        if os.path.exists(html_file):
            with open(html_file, "r") as f:
                result["html_content"] = f.read()

            # Cleanup
            os.unlink(html_file)

    return result


def create_function_tool(func):
    """
    Create a FunctionTool from a function.

    Args:
        func: The function to create a tool from

    Returns:
        FunctionTool: The FunctionTool for the function
    """
    return FunctionTool(func)


# Create all the tools
code_execution_tool_obj = create_function_tool(code_execution_tool)
run_tests_tool = create_function_tool(run_tests)
validate_code_tool = create_function_tool(validate_code)
generate_documentation_tool = create_function_tool(generate_documentation)

# File operation tools - we reuse these from the filesystem module
list_directory_tool = create_function_tool(list_directory)
read_file_tool = create_function_tool(read_file)
write_file_tool = create_function_tool(write_file)
edit_file_tool = create_function_tool(edit_file_func)
copy_file_tool = create_function_tool(copy_file)
search_tool = create_function_tool(search)
get_info_tool = create_function_tool(get_info)

# Collect all execution tools
execution_tools = [
    code_execution_tool_obj,
    run_tests_tool,
    validate_code_tool,
    generate_documentation_tool,
    list_directory_tool,
    read_file_tool,
    write_file_tool,
    edit_file_tool,
    copy_file_tool,
    search_tool,
    get_info_tool,
]
