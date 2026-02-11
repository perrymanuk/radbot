"""
List-related tools for the Todo Tool.

This module defines specialized functions for listing tasks, including
listing tasks by project and listing all tasks across projects.
"""

import logging
import traceback
import uuid
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

# Import database module functions
from ..db import get_db_connection, get_or_create_project_id
from ..db import list_all_tasks as db_list_all_tasks
from ..db import list_tasks as db_list_tasks

# Setup logging
logger = logging.getLogger(__name__)

# --- Tool Function Implementations ---


def list_project_tasks(
    project_id: str, status_filter: Optional[str] = None, include_done: bool = False
) -> Dict[str, Any]:
    """
    Retrieves a list of todo tasks for a specific project.

    Fetches tasks associated with the given project, which can be specified by either
    a UUID or a project name. By default, completed tasks ('done' status) are excluded
    unless explicitly requested with include_done=True or status_filter='done'.
    Tasks are returned ordered by creation date, newest first.

    Args:
        project_id: The project ID or name whose tasks should be listed. Can be a UUID or a project name. (Required)
        status_filter: An optional status to filter tasks by. Accepted values are
                       'backlog', 'inprogress', or 'done'. If omitted, tasks of all
                       active statuses (not 'done') are returned.
        include_done: Whether to include completed tasks in the results. Default is False.
                     If status_filter='done', this parameter is ignored.

    Returns:
        A dictionary containing the list of tasks or an error message.
        On success: {"status": "success", "tasks": [list of serialized task objects],
                     "project": {"name": "project_name", "id": "project_uuid"}}
        On failure: {"status": "error", "message": "Concise error description..."}
    """
    try:
        with get_db_connection() as conn:
            # Check if project_id is a UUID or a name
            project_name = None
            try:
                # Try to parse as UUID
                project_uuid = uuid.UUID(project_id)

                # Look up the project name for this UUID
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT name FROM projects WHERE project_id = %s;
                        """,
                            (project_uuid,),
                        )
                        result = cursor.fetchone()
                        if result:
                            project_name = result[0]
                except Exception as e:
                    logger.warning(
                        f"Could not retrieve project name for UUID {project_uuid}: {e}"
                    )
                    # Continue without the project name

            except ValueError:
                # Not a valid UUID, treat as project name
                logger.info(
                    f"Project ID '{project_id}' is not a UUID, treating as project name"
                )
                project_name = project_id
                try:
                    project_uuid = get_or_create_project_id(conn, project_id)
                    logger.info(
                        f"Using project ID: {project_uuid} for project name: {project_id}"
                    )
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Error finding or creating project '{project_id}': {str(e)}",
                    }

            # Handle status filtering based on include_done parameter
            # If status_filter is explicitly set, it takes precedence over include_done
            # If neither is set, we default to excluding 'done' tasks
            effective_status_filter = status_filter

            if status_filter is None and not include_done:
                # We'll need to filter out 'done' tasks ourselves
                logger.debug(
                    "No status filter specified and include_done=False, will filter out 'done' tasks"
                )
                task_dicts = db_list_tasks(conn, project_uuid, None)  # Get all tasks
                # Filter out 'done' tasks in memory
                task_dicts = [
                    task for task in task_dicts if task.get("status") != "done"
                ]
            else:
                # Use the regular filtering mechanism
                task_dicts = db_list_tasks(conn, project_uuid, effective_status_filter)

            # Convert task dictionaries to JSON-serializable format
            tasks_list = []
            for task_dict in task_dicts:
                # Convert UUID fields to strings
                if "task_id" in task_dict:
                    task_dict["task_id"] = str(task_dict["task_id"])
                if "project_id" in task_dict:
                    task_dict["project_id"] = str(task_dict["project_id"])
                # Convert datetime to ISO format string
                if "created_at" in task_dict and task_dict["created_at"]:
                    task_dict["created_at"] = task_dict["created_at"].isoformat()

                tasks_list.append(task_dict)

            # Create the response with project info
            return {
                "status": "success",
                "tasks": tasks_list,
                "project": {
                    "id": str(project_uuid),
                    "name": project_name if project_name else "Unknown Project",
                },
            }

    except (
        ValueError
    ) as e:  # Catch specific validation errors (e.g., invalid status_filter)
        error_message = f"Input validation error listing tasks: {str(e)}"
        logger.error(f"Error in list_project_tasks tool: {error_message}")
        return {"status": "error", "message": error_message}
    except Exception as e:
        error_message = f"Failed to list tasks for project {project_id}: {str(e)}"
        logger.error(f"Error in list_project_tasks tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (
            (error_message[:197] + "...") if len(error_message) > 200 else error_message
        )
        return {"status": "error", "message": truncated_message}


def list_all_tasks(
    status_filter: Optional[str] = None, include_done: bool = False
) -> Dict[str, Any]:
    """
    Retrieves a list of all todo tasks across all projects.

    Fetches all tasks in the database, across all projects. By default, completed tasks
    ('done' status) are excluded unless explicitly requested with include_done=True or
    status_filter='done'. Tasks are returned ordered by creation date, newest first.

    Args:
        status_filter: An optional status to filter tasks by. Accepted values are
                       'backlog', 'inprogress', or 'done'. If omitted, tasks of all
                       active statuses (not 'done') are returned.
        include_done: Whether to include completed tasks in the results. Default is False.
                      If status_filter='done', this parameter is ignored.

    Returns:
        A dictionary containing the list of tasks or an error message.
        On success: {"status": "success", "tasks": [list of serialized task objects with project names]}
        On failure: {"status": "error", "message": "Concise error description..."}
    """
    try:
        with get_db_connection() as conn:
            # Handle status filtering based on include_done parameter
            # If status_filter is explicitly set, it takes precedence over include_done
            effective_status_filter = status_filter

            if status_filter is None and not include_done:
                # Get all tasks then filter out 'done' tasks manually
                task_dicts = db_list_all_tasks(conn)
                # Filter out 'done' tasks
                task_dicts = [
                    task for task in task_dicts if task.get("status") != "done"
                ]
            else:
                # Use the regular filtering mechanism if status_filter is specified or we're including done tasks
                task_dicts = db_list_all_tasks(conn, effective_status_filter)

            # Convert task dictionaries to JSON-serializable format
            tasks_list = []
            for task_dict in task_dicts:
                # Convert UUID fields to strings
                if "task_id" in task_dict:
                    task_dict["task_id"] = str(task_dict["task_id"])
                if "project_id" in task_dict:
                    task_dict["project_id"] = str(task_dict["project_id"])
                # Convert datetime to ISO format string
                if "created_at" in task_dict and task_dict["created_at"]:
                    task_dict["created_at"] = task_dict["created_at"].isoformat()

                tasks_list.append(task_dict)

            # Create the response with task list
            return {"status": "success", "tasks": tasks_list}

    except (
        ValueError
    ) as e:  # Catch specific validation errors (e.g., invalid status_filter)
        error_message = f"Input validation error listing tasks: {str(e)}"
        logger.error(f"Error in list_all_tasks tool: {error_message}")
        return {"status": "error", "message": error_message}
    except Exception as e:
        error_message = f"Failed to list all tasks: {str(e)}"
        logger.error(f"Error in list_all_tasks tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (
            (error_message[:197] + "...") if len(error_message) > 200 else error_message
        )
        return {"status": "error", "message": truncated_message}


# --- ADK Tool Wrapping ---
list_project_tasks_tool = FunctionTool(list_project_tasks)
list_all_tasks_tool = FunctionTool(list_all_tasks)
