"""
Update tools for the Todo Tool.

This module defines the public functions for updating existing tasks and projects.
"""

import uuid
import traceback
import logging
import psycopg2
from typing import Optional, Dict, Any, List
from google.adk.tools import FunctionTool

# Import database and model modules
from ..db import (
    get_db_connection, 
    update_task as db_update_task, 
    update_project as db_update_project,
    get_task as db_get_task,
    get_project as db_get_project,
    get_or_create_project_id
)

# Setup logging
logger = logging.getLogger(__name__)

# --- Tool Function Implementations ---

def update_task(task_id: str, description: Optional[str] = None,
               project_id: Optional[str] = None, status: Optional[str] = None,
               category: Optional[str] = None, origin: Optional[str] = None,
               related_info: Optional[Dict[str, Any]] = None,
               title: Optional[str] = None) -> Dict[str, Any]:
    """
    Updates an existing todo task with the provided information.

    This tool allows you to modify various attributes of an existing task.
    Only the fields you provide will be updated; others will remain unchanged.

    Args:
        task_id: The UUID identifier of the task to update. (Required)
        description: The new description text for the task.
        project_id: The new project ID or name to move the task to.
        status: The new status ('backlog', 'inprogress', or 'done').
        category: The new category label.
        origin: The new origin information.
        related_info: Additional structured data to store with the task.
        title: An optional short summary for the task.
    
    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "task_id": "updated_task_uuid_string", "task": {...}}
        On failure: {"status": "error", "message": "Concise error description..."}
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
        
        # Connect to database
        with get_db_connection() as conn:
            # First check if the task exists
            task_data = db_get_task(conn, task_uuid)
            if not task_data:
                return {
                    "status": "error",
                    "message": f"Task with ID {task_id} not found."
                }
            
            # Handle project_id conversion if provided
            project_uuid = None
            if project_id is not None:
                try:
                    # Try to parse as UUID
                    project_uuid = uuid.UUID(project_id)
                except ValueError:
                    # Not a valid UUID, treat as project name
                    logger.info(f"Project ID '{project_id}' is not a UUID, treating as project name")
                    try:
                        project_uuid = get_or_create_project_id(conn, project_id)
                        logger.info(f"Using project ID: {project_uuid} for project name: {project_id}")
                    except Exception as e:
                        return {
                            "status": "error",
                            "message": f"Error finding or creating project '{project_id}': {str(e)}"
                        }
            
            # Update the task
            success = db_update_task(
                conn=conn,
                task_id=task_uuid,
                description=description,
                project_id=project_uuid,
                status=status,
                category=category,
                origin=origin,
                related_info=related_info,
                title=title
            )
            
            if success:
                # Get the updated task data
                updated_task = db_get_task(conn, task_uuid)
                # Updated task data already has all datetime and UUID values converted to strings by db_get_task
                return {
                    "status": "success",
                    "task_id": str(task_uuid),
                    "task": updated_task
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to update task with ID {task_id}."
                }
                
    except ValueError as e:
        # Catch validation errors (e.g., invalid status)
        error_message = f"Input validation error: {str(e)}"
        logger.error(f"Error in update_task tool: {error_message}")
        return {
            "status": "error",
            "message": error_message
        }
    except Exception as e:
        # Handle general errors
        error_message = f"Failed to update task {task_id}: {str(e)}"
        logger.error(f"Error in update_task tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }


def update_project(project_id: str, name: str) -> Dict[str, Any]:
    """
    Updates an existing project's name.
    
    This tool allows you to rename a project.
    
    Args:
        project_id: The UUID identifier of the project to update. (Required)
        name: The new name for the project. (Required)
    
    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "project_id": "updated_project_uuid", "project": {...}}
        On failure: {"status": "error", "message": "Concise error description..."}
    """
    try:
        # Convert project_id string to UUID object
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid project ID format: {project_id}. Must be a valid UUID."
            }
        
        # Connect to database
        with get_db_connection() as conn:
            # First check if the project exists
            project_data = db_get_project(conn, project_uuid)
            if not project_data:
                return {
                    "status": "error",
                    "message": f"Project with ID {project_id} not found."
                }
            
            # Update the project
            try:
                success = db_update_project(
                    conn=conn,
                    project_id=project_uuid,
                    name=name
                )
                
                if success:
                    # Get the updated project data
                    updated_project = db_get_project(conn, project_uuid)
                    # Updated project data already has datetime and UUID converted to strings by db_get_project
                    return {
                        "status": "success",
                        "project_id": str(project_uuid),
                        "project": updated_project
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Failed to update project with ID {project_id}."
                    }
            except psycopg2.IntegrityError:
                # This happens if a project with this name already exists
                return {
                    "status": "error",
                    "message": f"A project with the name '{name}' already exists."
                }
                
    except Exception as e:
        # Handle general errors
        error_message = f"Failed to update project {project_id}: {str(e)}"
        logger.error(f"Error in update_project tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }

# --- ADK Tool Wrapping ---
update_task_tool = FunctionTool(update_task)
update_project_tool = FunctionTool(update_project)
