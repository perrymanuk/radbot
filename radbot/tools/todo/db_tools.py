"""
Database interaction layer for the Todo Tool.

This module encapsulates all direct communication with the PostgreSQL database
using the psycopg2 library. It utilizes connection pooling for efficiency and
defines private functions for core CRUD operations.
"""

import logging
import psycopg2
import psycopg2.extras  # For RealDictCursor
import uuid
from typing import List, Dict, Optional, Any

# Reuse the lazy connection pool from the db package
from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

# Setup logging
logger = logging.getLogger(__name__)


# --- Private CRUD Functions ---

def _get_or_create_project_id(conn: psycopg2.extensions.connection, project_name: str) -> uuid.UUID:
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

def _add_task(conn: psycopg2.extensions.connection, description: str, project_id: uuid.UUID,
              category: Optional[str], origin: Optional[str], related_info: Optional[Dict],
              title: Optional[str] = None) -> uuid.UUID:
    """Inserts a new task into the database and returns its UUID."""
    sql = """
        INSERT INTO tasks (description, project_id, category, origin, related_info, title)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING task_id;
    """
    # psycopg2 automatically handles JSON serialization for related_info if it's a dict
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


def _list_tasks(conn: psycopg2.extensions.connection, project_id: uuid.UUID, 
                status_filter: Optional[str]) -> List[Dict[str, Any]]:
    """Retrieves tasks, optionally filtered by status."""
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


def _complete_task(conn: psycopg2.extensions.connection, task_id: uuid.UUID) -> bool:
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


def _remove_task(conn: psycopg2.extensions.connection, task_id: uuid.UUID) -> bool:
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


def _list_projects(conn: psycopg2.extensions.connection) -> List[Dict[str, Any]]:
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


def create_schema_if_not_exists() -> None:
    """
    Creates the necessary database schema if it doesn't exist.
    Should be called once during application initialization.
    """
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                # Check if the task_status enum type exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_type WHERE typname = 'task_status'
                    );
                """)
                enum_exists = cursor.fetchone()[0]
                
                if not enum_exists:
                    logger.info("Creating task_status ENUM type")
                    cursor.execute("""
                        CREATE TYPE task_status AS ENUM ('backlog', 'inprogress', 'done');
                    """)
                
                # Check if the tasks table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables WHERE table_name = 'tasks'
                    );
                """)
                table_exists = cursor.fetchone()[0]
                
                if not table_exists:
                    logger.info("Creating tasks table")
                    cursor.execute("""
                        CREATE TABLE tasks (
                            task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            project_id UUID NOT NULL,
                            description TEXT NOT NULL,
                            status task_status NOT NULL DEFAULT 'backlog',
                            category TEXT,
                            origin TEXT,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            related_info JSONB
                        );
                    """)
                    
                    # Create an index on project_id and status for faster filtering
                    cursor.execute("""
                        CREATE INDEX idx_tasks_project_status ON tasks (project_id, status);
                    """)
                    
                    logger.info("Database schema created successfully")
                else:
                    logger.info("Tasks table already exists")

                    # Migration: add title column if missing
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'tasks' AND column_name = 'title'
                        );
                    """)
                    title_exists = cursor.fetchone()[0]
                    if not title_exists:
                        logger.info("Adding title column to tasks table")
                        cursor.execute("ALTER TABLE tasks ADD COLUMN title TEXT;")

                # Check if the projects table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables WHERE table_name = 'projects'
                    );
                """)
                projects_table_exists = cursor.fetchone()[0]
                
                if not projects_table_exists:
                    logger.info("Creating projects table")
                    cursor.execute("""
                        CREATE TABLE projects (
                            project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            name TEXT NOT NULL UNIQUE,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    logger.info("Projects table created successfully")
                else:
                    logger.info("Projects table already exists")
    except Exception as e:
        logger.error(f"Error creating database schema: {e}")
        raise