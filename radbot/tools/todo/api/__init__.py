"""
API module for Todo Tool.

This module exports the public tool functions for the Todo Tool.
"""

from .list_tools import list_all_tasks_tool, list_project_tasks_tool
from .project_tools import list_projects_tool
from .task_tools import add_task_tool, complete_task_tool, remove_task_tool
from .update_tools import update_project_tool, update_task_tool

# Combine all tools into a single list for easy registration
ALL_TOOLS = [
    add_task_tool,
    complete_task_tool,
    remove_task_tool,
    list_projects_tool,
    list_project_tasks_tool,
    list_all_tasks_tool,
    update_task_tool,
    update_project_tool,
]

__all__ = [
    "add_task_tool",
    "complete_task_tool",
    "remove_task_tool",
    "list_projects_tool",
    "list_project_tasks_tool",
    "list_all_tasks_tool",
    "update_task_tool",
    "update_project_tool",
    "ALL_TOOLS",
]
