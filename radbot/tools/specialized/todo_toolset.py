"""Todo toolset for specialized agents.

This module provides tools for managing tasks, projects, and todo lists.
"""

import logging
from typing import Any, List, Optional

# Import todo tools
try:
    from radbot.tools.todo.todo_tools import (
        add_task,
        complete_task,
        list_all_tasks,
        list_project_tasks,
        list_projects,
        remove_task,
        update_project,
        update_task,
    )
except ImportError:
    # Define placeholders if not available
    add_task = None
    complete_task = None
    remove_task = None
    list_projects = None
    list_project_tasks = None
    list_all_tasks = None
    update_task = None
    update_project = None

# Try to import API-based todo tools if available
try:
    from radbot.tools.todo.api.list_tools import get_list_tools
    from radbot.tools.todo.api.project_tools import get_project_tools
    from radbot.tools.todo.api.task_tools import get_task_tools
    from radbot.tools.todo.api.update_tools import get_update_tools
except ImportError:
    get_task_tools = None
    get_project_tools = None
    get_list_tools = None
    get_update_tools = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)


def create_todo_toolset() -> List[Any]:
    """Create the set of tools for the todo specialized agent.

    Returns:
        List of tools for task and project management
    """
    toolset = []

    # Add basic task management tools
    todo_funcs = [
        (add_task, "add_task"),
        (complete_task, "complete_task"),
        (remove_task, "remove_task"),
        (list_projects, "list_projects"),
        (list_project_tasks, "list_project_tasks"),
        (list_all_tasks, "list_all_tasks"),
        (update_task, "update_task"),
        (update_project, "update_project"),
    ]

    for func, name in todo_funcs:
        if func:
            try:
                toolset.append(func)
                logger.info(f"Added {name} to todo toolset")
            except Exception as e:
                logger.error(f"Failed to add {name}: {e}")

    # Add API-based todo tools if available
    api_tool_getters = [
        (get_task_tools, "task tools"),
        (get_project_tools, "project tools"),
        (get_list_tools, "list tools"),
        (get_update_tools, "update tools"),
    ]

    for getter, name in api_tool_getters:
        if getter:
            try:
                tools = getter()
                if tools:
                    toolset.extend(tools)
                    logger.info(f"Added {len(tools)} {name} to todo toolset")
            except Exception as e:
                logger.error(f"Failed to add {name}: {e}")

    return toolset


# Register the toolset with the system
register_toolset(
    name="todo",
    toolset_func=create_todo_toolset,
    description="Agent specialized in task and project management",
    allowed_transfers=[],  # Only allows transfer back to main orchestrator
)
