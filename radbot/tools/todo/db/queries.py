"""
Database queries and operations for the Todo Tool.

This module encapsulates all direct database query operations
for the Todo Tool using the psycopg2 library.
"""

import logging
import psycopg2
import psycopg2.extras  # For RealDictCursor
import uuid
import json
from typing import List, Dict, Optional, Any

from .connection import get_db_cursor

# Setup logging
logger = logging.getLogger(__name__)

# --- Database Query Functions ---

def get_or_create_project_id(conn: psycopg2.extensions.connection, project_name: str) -> uuid.UUID:
    """Gets an existing project ID or creates a new one for the given project name."""
    # First check if we already have a project table
    try:
        with get_db_cursor(conn) as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables WHERE table_name = 'projects'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                # Create the projects table if it doesn't exist
                logger.info("Creating projects table")
                cursor.execute("""
                    CREATE TABLE projects (
                        project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
                logger.info("Projects table created successfully")
    except Exception as e:
        logger.error(f"Error checking/creating projects table: {e}")
        raise
    
    # Now try to find an existing project with this name
    try:
        with get_db_cursor(conn) as cursor:
            cursor.execute("""
                SELECT project_id FROM projects WHERE name = %s;
            """, (project_name,))
            result = cursor.fetchone()
            
            if result:
                # Found existing project
                return result[0]
            else:
                # Create new project
                with get_db_cursor(conn, commit=True) as cursor:
                    cursor.execute("""
                        INSERT INTO projects (name) VALUES (%s) RETURNING project_id;
                    """, (project_name,))
                    new_id = cursor.fetchone()[0]
                    logger.info(f"Created new project '{project_name}' with ID {new_id}")
                    return new_id
    except Exception as e:
        logger.error(f"Error getting/creating project ID for '{project_name}': {e}")
        raise


def add_task(conn: psycopg2.extensions.connection, description: str, project_id: uuid.UUID,
             category: Optional[str], origin: Optional[str], related_info: Optional[Dict],
             title: Optional[str] = None) -> uuid.UUID:
    """Inserts a new task into the database and returns its UUID."""
    sql = """
        INSERT INTO tasks (description, project_id, category, origin, related_info, title)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        RETURNING task_id;
    """
    # Convert related_info dict to JSON string if it exists
    if related_info is not None:
        related_info = json.dumps(related_info)

    # Set up parameters for query
    params = (description, project_id, category, origin, related_info, title)
    try:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()
            if result:
                return result[0]  # task_id is the first column
            else:
                # This should ideally not happen with RETURNING if insert succeeds
                raise psycopg2.DatabaseError("INSERT operation did not return task_id.")
    except psycopg2.IntegrityError as e:
        logger.error(f"Integrity error adding task: {e}")
        # Could potentially parse the error for specifics (e.g., constraint violation)
        raise  # Re-raise to be handled by the calling tool function
    except psycopg2.Error as e:
        logger.error(f"Database error adding task: {e}")
        raise  # Re-raise for generic handling


def update_task(conn: psycopg2.extensions.connection, task_id: uuid.UUID,
               description: Optional[str] = None,
               project_id: Optional[uuid.UUID] = None,
               status: Optional[str] = None,
               category: Optional[str] = None,
               origin: Optional[str] = None,
               related_info: Optional[Dict] = None,
               title: Optional[str] = None) -> bool:
    """
    Updates a task with the provided fields. Only updates fields that are not None.
    Returns True if the update was successful, False if the task wasn't found.
    """
    # Start building SQL update statement and parameters
    update_fields = []
    params = []
    
    # Add fields that are provided (not None)
    if description is not None:
        update_fields.append("description = %s")
        params.append(description)
    
    if project_id is not None:
        update_fields.append("project_id = %s")
        params.append(project_id)
    
    if status is not None:
        # Validate status against allowed ENUM values
        allowed_statuses = ('backlog', 'inprogress', 'done')
        if status not in allowed_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {allowed_statuses}")
        update_fields.append("status = %s")
        params.append(status)
    
    if category is not None:
        update_fields.append("category = %s")
        params.append(category)
    
    if origin is not None:
        update_fields.append("origin = %s")
        params.append(origin)
    
    if related_info is not None:
        update_fields.append("related_info = %s::jsonb")
        # Convert dict to JSON string for PostgreSQL
        params.append(json.dumps(related_info))

    if title is not None:
        update_fields.append("title = %s")
        params.append(title)

    # If no fields to update, return early
    if not update_fields:
        logger.warning("No fields provided to update task")
        return False
    
    # Construct SQL statement
    sql = f"""
        UPDATE tasks
        SET {", ".join(update_fields)}
        WHERE task_id = %s
        RETURNING task_id;
    """
    
    # Add task_id to params
    params.append(task_id)
    
    try:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(sql, tuple(params))
            # Check if a row was actually updated
            return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error updating task {task_id}: {e}")
        raise


def update_project(conn: psycopg2.extensions.connection, project_id: uuid.UUID, 
                  name: str) -> bool:
    """
    Updates a project's name.
    Returns True if the update was successful, False if the project wasn't found.
    """
    sql = """
        UPDATE projects
        SET name = %s
        WHERE project_id = %s
        RETURNING project_id;
    """
    params = (name, project_id)
    
    try:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(sql, params)
            # Check if a row was actually updated
            return cursor.rowcount > 0
    except psycopg2.IntegrityError as e:
        # This likely means a project with this name already exists
        logger.error(f"Integrity error updating project {project_id}: {e}")
        raise
    except psycopg2.Error as e:
        logger.error(f"Database error updating project {project_id}: {e}")
        raise


def list_tasks(conn: psycopg2.extensions.connection, project_id: uuid.UUID,
              status_filter: Optional[str]) -> List[Dict[str, Any]]:
    """Retrieves tasks for a specific project, optionally filtered by status."""
    base_sql = """
        SELECT task_id, project_id, description, status, category, origin, created_at, related_info, title
        FROM tasks
        WHERE project_id = %s
    """
    params: List[Any] = [project_id]

    if status_filter:
        # Validate status_filter against allowed ENUM values
        allowed_statuses = ('backlog', 'inprogress', 'done')
        if status_filter not in allowed_statuses:
            raise ValueError(f"Invalid status filter: {status_filter}. Must be one of {allowed_statuses}")
        base_sql += " AND status = %s"
        params.append(status_filter)

    base_sql += " ORDER BY created_at DESC;"  # Example ordering

    try:
        # Using RealDictCursor for easy dictionary conversion
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(base_sql, tuple(params))
            results = cursor.fetchall()
            # Convert RealDictRow objects to standard dicts for broader compatibility
            return [dict(row) for row in results]
    except psycopg2.Error as e:
        logger.error(f"Database error listing tasks: {e}")
        raise


def list_all_tasks(conn: psycopg2.extensions.connection, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all tasks across all projects, optionally filtered by status."""
    base_sql = """
        SELECT t.task_id, t.project_id, p.name as project_name, t.description,
               t.status, t.category, t.origin, t.created_at, t.related_info, t.title
        FROM tasks t
        JOIN projects p ON t.project_id = p.project_id
    """
    params: List[Any] = []

    if status_filter:
        # Validate status_filter against allowed ENUM values
        allowed_statuses = ('backlog', 'inprogress', 'done')
        if status_filter not in allowed_statuses:
            raise ValueError(f"Invalid status filter: {status_filter}. Must be one of {allowed_statuses}")
        base_sql += " WHERE t.status = %s"
        params.append(status_filter)

    base_sql += " ORDER BY t.created_at DESC;"  # Most recent first

    try:
        # Using RealDictCursor for easy dictionary conversion
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(base_sql, tuple(params))
            results = cursor.fetchall()
            # Convert RealDictRow objects to standard dicts for broader compatibility
            return [dict(row) for row in results]
    except psycopg2.Error as e:
        logger.error(f"Database error listing all tasks: {e}")
        raise


def get_task(conn: psycopg2.extensions.connection, task_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Retrieves a specific task by its ID.
    Returns None if the task doesn't exist.
    """
    sql = """
        SELECT t.task_id, t.project_id, p.name as project_name, t.description,
               t.status, t.category, t.origin, t.created_at, t.related_info, t.title
        FROM tasks t
        JOIN projects p ON t.project_id = p.project_id
        WHERE t.task_id = %s;
    """
    params = (task_id,)
    
    try:
        # Using RealDictCursor for easy dictionary conversion
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()
            if result:
                # Convert result to a regular dict and handle datetime serialization
                task_dict = dict(result)
                # Convert datetime to ISO format string
                if 'created_at' in task_dict and task_dict['created_at']:
                    task_dict['created_at'] = task_dict['created_at'].isoformat()
                # Convert UUID fields to strings
                if 'task_id' in task_dict and task_dict['task_id']:
                    task_dict['task_id'] = str(task_dict['task_id'])
                if 'project_id' in task_dict and task_dict['project_id']:
                    task_dict['project_id'] = str(task_dict['project_id'])
                return task_dict
            return None
    except psycopg2.Error as e:
        logger.error(f"Database error getting task {task_id}: {e}")
        raise


def get_project(conn: psycopg2.extensions.connection, project_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Retrieves a specific project by its ID.
    Returns None if the project doesn't exist.
    """
    sql = """
        SELECT project_id, name, created_at
        FROM projects
        WHERE project_id = %s;
    """
    params = (project_id,)
    
    try:
        # Using RealDictCursor for easy dictionary conversion
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql, params)
            result = cursor.fetchone()
            if result:
                # Convert result to a regular dict and handle datetime serialization
                project_dict = dict(result)
                # Convert datetime to ISO format string
                if 'created_at' in project_dict and project_dict['created_at']:
                    project_dict['created_at'] = project_dict['created_at'].isoformat()
                # Convert UUID to string
                if 'project_id' in project_dict and project_dict['project_id']:
                    project_dict['project_id'] = str(project_dict['project_id'])
                return project_dict
            return None
    except psycopg2.Error as e:
        logger.error(f"Database error getting project {project_id}: {e}")
        raise


def complete_task(conn: psycopg2.extensions.connection, task_id: uuid.UUID) -> bool:
    """Updates a task's status to 'done'."""
    sql = """
        UPDATE tasks
        SET status = 'done'
        WHERE task_id = %s
        RETURNING task_id;
    """
    params = (task_id,)
    try:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(sql, params)
            # Check if a row was actually updated
            return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error completing task {task_id}: {e}")
        raise


def remove_task(conn: psycopg2.extensions.connection, task_id: uuid.UUID) -> bool:
    """Deletes a task from the database."""
    sql = """
        DELETE FROM tasks
        WHERE task_id = %s
        RETURNING task_id;
    """
    # Convert task_id to string if it's a UUID object
    task_id_str = str(task_id) if isinstance(task_id, uuid.UUID) else task_id
    params = (task_id_str,)
    
    logger.debug(f"Executing DELETE query with params: {params}")
    
    try:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(sql, params)
            # Check if a row was actually deleted
            affected_rows = cursor.rowcount
            logger.debug(f"DELETE affected {affected_rows} rows")
            return affected_rows > 0
    except psycopg2.Error as e:
        logger.error(f"Database error removing task {task_id}: {e}")
        raise


def list_projects(conn: psycopg2.extensions.connection) -> List[Dict[str, Any]]:
    """Retrieves all projects from the database."""
    try:
        # First check if the projects table exists
        with get_db_cursor(conn) as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables WHERE table_name = 'projects'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                # Create the projects table if it doesn't exist
                logger.info("Creating projects table")
                cursor.execute("""
                    CREATE TABLE projects (
                        project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
                logger.info("Projects table created successfully")
                return []  # Return empty list since we just created the table
        
        # Get all projects
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT project_id, name, created_at
                FROM projects
                ORDER BY name ASC;
            """)
            results = cursor.fetchall()
            # Convert RealDictRow objects to standard dicts for broader compatibility
            return [dict(row) for row in results]
    except psycopg2.Error as e:
        logger.error(f"Database error listing projects: {e}")
        raise
