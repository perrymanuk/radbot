"""
Scheduler tools for the radbot agent.

This package provides tools for creating, listing, and deleting scheduled tasks
that run on a cron schedule. Jobs persist in PostgreSQL and survive restarts.
"""

from .db import init_scheduler_schema
from .schedule_tools import (
    SCHEDULER_TOOLS,
    create_scheduled_task_tool,
    delete_scheduled_task_tool,
    list_scheduled_tasks_tool,
)

__all__ = [
    "create_scheduled_task_tool",
    "list_scheduled_tasks_tool",
    "delete_scheduled_task_tool",
    "SCHEDULER_TOOLS",
    "init_scheduler_schema",
]
