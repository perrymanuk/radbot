"""
ADK FunctionTools for Todo List management.

This module defines the public functions that the ADK agent will call. These functions
act as a bridge between the agent's requests and the database interaction logic in db_tools.py.
They handle input parsing, calling the appropriate database function, error handling, and
formatting the response.
"""

import uuid
import traceback
import logging
from typing import Optional, Dict, List, Any
from google.adk.tools import FunctionTool

# Import database interaction functions and Pydantic models
from . import db_tools
from . import models

# Setup logging
logger = logging.getLogger(__name__)

# --- Tool Function Implementations ---

def add_task(description: str, project_id: str, title: Optional[str] = None,
             category: Optional[str] = None,
             origin: Optional[str] = None, related_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Adds a new todo task to the persistent database.

    This tool creates a new task entry with the provided details. It requires
    a description and either a project ID (UUID) or a project name. If a project name
    is provided, the tool will automatically look up or create a project with that name.

    Args:
        description: The main text content describing the task. (Required)
        project_id: The project ID or name the task belongs to. Can be a UUID string or a project name. (Required)
        title: An optional short summary for the task, displayed in the task list.
        category: An optional label to categorize the task (e.g., 'work', 'personal').
        origin: An optional string indicating the source of the task (e.g., 'chat', 'email', 'manual').
        related_info: An optional dictionary for storing supplementary structured data,
                      such as {'link': 'http://example.com', 'notes': 'Further details...'}.

    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "task_id": "new_task_uuid_string"}
        On failure: {"status": "error", "message": "Concise error description..."}
    """
    try:
        # Connect to database
        with db_tools.get_db_connection() as conn:
            # Check if project_id is a UUID or a name
            try:
                # Try to parse as UUID
                project_uuid = uuid.UUID(project_id)
            except ValueError:
                # Not a valid UUID, treat as project name
                logger.info(f"Project ID '{project_id}' is not a UUID, treating as project name")
                project_uuid = db_tools._get_or_create_project_id(conn, project_id)
                logger.info(f"Using project ID: {project_uuid} for project name: {project_id}")

            # Now add the task with the resolved project UUID
            # Convert project_uuid to string format for database operations
            new_task_id = db_tools._add_task(
                conn=conn,
                description=description,
                project_id=project_uuid,  # UUID objects should now be handled correctly with the adapter
                category=category,
                origin=origin,
                related_info=related_info,
                title=title
            )
            
            # Log the task creation for debugging
            logger.debug(f"Created task with ID: {new_task_id} for project: {project_uuid}")
            
        # Create response with string UUID
        return {
            "status": "success",
            "task_id": str(new_task_id)
        }

    except Exception as e:
        # Handle error (logging, truncation, formatting)
        error_message = f"Failed to add task: {str(e)}"
        logger.error(f"Error in add_task tool: {error_message}")
        logger.debug(traceback.format_exc())  # Log full traceback for debugging
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message

        # Return error response directly
        return {
            "status": "error",
            "message": truncated_message
        }


def list_tasks(project_id: str, status_filter: Optional[str] = None, include_done: bool = False) -> Dict[str, Any]:
    """
    Retrieves a list of todo tasks for a specific project, optionally filtered by status.

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
        with db_tools.get_db_connection() as conn:
            # Check if project_id is a UUID or a name
            project_name = None
            try:
                # Try to parse as UUID
                project_uuid = uuid.UUID(project_id)
                
                # Look up the project name for this UUID
                try:
                    with db_tools.get_db_cursor(conn) as cursor:
                        cursor.execute("""
                            SELECT name FROM projects WHERE project_id = %s;
                        """, (project_uuid,))
                        result = cursor.fetchone()
                        if result:
                            project_name = result[0]
                except Exception as e:
                    logger.warning(f"Could not retrieve project name for UUID {project_uuid}: {e}")
                    # Continue without the project name
                    
            except ValueError:
                # Not a valid UUID, treat as project name
                logger.info(f"Project ID '{project_id}' is not a UUID, treating as project name")
                project_name = project_id
                try:
                    project_uuid = db_tools._get_or_create_project_id(conn, project_id)
                    logger.info(f"Using project ID: {project_uuid} for project name: {project_id}")
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Error finding or creating project '{project_id}': {str(e)}"
                    }

            # Handle status filtering based on include_done parameter
            # If status_filter is explicitly set, it takes precedence over include_done
            # If neither is set, we default to excluding 'done' tasks
            effective_status_filter = status_filter
            
            if status_filter is None and not include_done:
                # We'll need to filter out 'done' tasks ourselves
                logger.debug("No status filter specified and include_done=False, will filter out 'done' tasks")
                task_dicts = db_tools._list_tasks(conn, project_uuid, None)  # Get all tasks
                # Filter out 'done' tasks in memory
                task_dicts = [task for task in task_dicts if task.get('status') != 'done']
            else:
                # Use the regular filtering mechanism
                task_dicts = db_tools._list_tasks(conn, project_uuid, effective_status_filter)

            # Convert task dictionaries to JSON-serializable format
            tasks_list = []
            for task_dict in task_dicts:
                # Convert UUID fields to strings
                if 'task_id' in task_dict:
                    task_dict['task_id'] = str(task_dict['task_id'])
                if 'project_id' in task_dict:
                    task_dict['project_id'] = str(task_dict['project_id'])
                # Convert datetime to ISO format string
                if 'created_at' in task_dict and task_dict['created_at']:
                    task_dict['created_at'] = task_dict['created_at'].isoformat()
                    
                tasks_list.append(task_dict)
                
            # Create the response with project info
            return {
                "status": "success",
                "tasks": tasks_list,
                "project": {
                    "id": str(project_uuid),
                    "name": project_name if project_name else "Unknown Project"
                }
            }

    except ValueError as e:  # Catch specific validation errors (e.g., invalid status_filter)
        error_message = f"Input validation error listing tasks: {str(e)}"
        logger.error(f"Error in list_tasks tool: {error_message}")
        return {
            "status": "error",
            "message": error_message
        }
    except Exception as e:
        error_message = f"Failed to list tasks for project {project_id}: {str(e)}"
        logger.error(f"Error in list_tasks tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }


def list_projects() -> Dict[str, Any]:
    """
    Retrieves a list of all available projects.
    
    This tool lists all projects that have been created in the database, including
    their UUIDs and names. This is useful for discovering available projects.
    
    Returns:
        A dictionary containing the list of projects or an error message.
        On success: {"status": "success", "projects": [{"id": "uuid", "name": "project_name", "created_at": "timestamp"},...]}
        On failure: {"status": "error", "message": "Concise error description..."}
    """
    try:
        with db_tools.get_db_connection() as conn:
            projects = db_tools._list_projects(conn)
            
            # Format project data for response
            project_list = []
            for proj in projects:
                project_list.append({
                    "id": str(proj.get("project_id")),
                    "name": proj.get("name"),
                    "created_at": proj.get("created_at").isoformat() if proj.get("created_at") else None
                })
                
            # Create the response
            return {
                "status": "success",
                "projects": project_list
            }
            
    except Exception as e:
        error_message = f"Failed to list projects: {str(e)}"
        logger.error(f"Error in list_projects tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }


def complete_task(task_id: str) -> Dict[str, Any]:
    """
    Marks a specific todo task as 'done'.

    Updates the status of the task identified by the given UUID to 'done'.

    Args:
        task_id: The UUID identifier of the task to mark as completed. (Required)

    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "task_id": "completed_task_uuid_string"}
        On failure: {"status": "error", "message": "Concise error description..."}
                    (e.g., if the task ID doesn't exist)
    """
    try:
        # Convert task_id string to UUID object
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid task ID format: {task_id}. Must be a valid UUID."
            }

        with db_tools.get_db_connection() as conn:
            success = db_tools._complete_task(conn, task_uuid)

        if success:
            return {
                "status": "success",
                "task_id": str(task_uuid)
            }
        else:
            # Task not found or already done (depending on desired logic)
            return {
                "status": "error",
                "message": f"Task with ID {task_id} not found or could not be updated."
            }

    except Exception as e:
        error_message = f"Failed to complete task {task_id}: {str(e)}"
        logger.error(f"Error in complete_task tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }


def remove_task(task_id: str) -> Dict[str, Any]:
    """
    Permanently deletes a specific todo task from the database.

    Removes the task identified by the given UUID. This action cannot be undone.

    Args:
        task_id: The UUID identifier of the task to delete. (Required)

    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "task_id": "deleted_task_uuid_string"}
        On failure: {"status": "error", "message": "Concise error description..."}
                    (e.g., if the task ID doesn't exist)
    """
    try:
        # Convert task_id string to UUID object
        try:
            task_uuid = uuid.UUID(task_id)
            logger.debug(f"Successfully parsed task_id {task_id} as UUID: {task_uuid}")
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid task ID format: {task_id}. Must be a valid UUID."
            }

        # Log the UUID type and value before using it
        logger.debug(f"Removing task with UUID type: {type(task_uuid)}, value: {task_uuid}")

        # Get connection and attempt to remove the task
        with db_tools.get_db_connection() as conn:
            try:
                success = db_tools._remove_task(conn, task_uuid)
                
                if success:
                    logger.info(f"Successfully removed task with ID: {task_uuid}")
                    return {
                        "status": "success",
                        "task_id": str(task_uuid)
                    }
                else:
                    # Task not found
                    logger.warning(f"Task with ID {task_uuid} not found for deletion")
                    return {
                        "status": "error",
                        "message": f"Task with ID {task_id} not found for deletion."
                    }
            except Exception as db_error:
                logger.error(f"Database error in _remove_task: {db_error}")
                return {
                    "status": "error",
                    "message": f"Database error: {str(db_error)}"
                }

    except Exception as e:
        error_message = f"Failed to remove task {task_id}: {str(e)}"
        logger.error(f"Error in remove_task tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }


# --- Initialize database schema ---
def init_database():
    """Initialize the database schema if it doesn't exist."""
    db_tools.create_schema_if_not_exists()


# --- ADK Tool Wrapping ---
add_task_tool = FunctionTool(add_task)
list_tasks_tool = FunctionTool(list_tasks)
list_projects_tool = FunctionTool(list_projects)
complete_task_tool = FunctionTool(complete_task)
remove_task_tool = FunctionTool(remove_task)

# List of all tools to be registered with the agent
ALL_TOOLS = [add_task_tool, list_tasks_tool, list_projects_tool, complete_task_tool, remove_task_tool]
