"""
Database module for Todo Tool.

This module exports database functionality for the Todo Tool.
"""

from .connection import get_db_connection, get_db_cursor
from .queries import (
    add_task,
    complete_task,
    get_or_create_project_id,
    get_project,
    get_task,
    list_all_tasks,
    list_projects,
    list_tasks,
    remove_task,
    update_project,
    update_task,
)
from .schema import create_schema_if_not_exists

__all__ = [
    "get_db_connection",
    "get_db_cursor",
    "create_schema_if_not_exists",
    "get_or_create_project_id",
    "add_task",
    "update_task",
    "update_project",
    "list_tasks",
    "list_all_tasks",
    "get_task",
    "get_project",
    "complete_task",
    "remove_task",
    "list_projects",
]
