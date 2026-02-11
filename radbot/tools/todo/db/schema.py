"""
Database schema management for the Todo Tool.

This module handles schema creation and management for the Todo Tool database.
"""

import logging

from .connection import get_db_connection, get_db_cursor

# Setup logging
logger = logging.getLogger(__name__)


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
