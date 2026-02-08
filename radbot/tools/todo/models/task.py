"""
Pydantic models for the Todo Tool.

These models define the data structures for the Todo Tool, ensuring consistent
data validation and serialization across the application.
"""

import uuid
import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_serializer

# --- Base Task Model ---
class TaskBase(BaseModel):
    """Base model for common task attributes."""
    project_id: uuid.UUID
    description: str
    title: Optional[str] = None
    category: Optional[str] = None
    origin: Optional[str] = None
    related_info: Optional[Dict[str, Any]] = None
    
    @field_serializer('project_id')
    def serialize_uuid(self, uuid_value: uuid.UUID) -> str:
        """Convert UUID to string during serialization."""
        return str(uuid_value)


# --- Model for Creating Tasks ---
class TaskCreate(TaskBase):
    """Data required to create a new task (input)."""
    # Inherits fields from TaskBase
    # description and project_id are implicitly required
    pass


# --- Model for Representing Tasks from DB ---
class Task(TaskBase):
    """Full task representation including DB-generated fields."""
    task_id: uuid.UUID
    status: Literal['backlog', 'inprogress', 'done']
    created_at: datetime.datetime
    project_name: Optional[str] = None  # For list_all_tasks functionality
    
    @field_serializer('task_id')
    def serialize_task_id(self, uuid_value: uuid.UUID) -> str:
        """Convert task_id UUID to string during serialization."""
        return str(uuid_value)
        
    @field_serializer('created_at')
    def serialize_datetime(self, dt: datetime.datetime) -> str:
        """Convert datetime to ISO format string."""
        return dt.isoformat()

    class Config:
        """Configuration for Pydantic model."""
        from_attributes = True  # For Pydantic v2
        json_encoders = {
            uuid.UUID: str,  # Convert UUID to string during JSON serialization
            datetime.datetime: lambda dt: dt.isoformat()  # Convert datetime to ISO format
        }


# --- Models for Tool Inputs ---
class ToolInputAddTask(TaskCreate):
    """Specific input structure for the add_task tool."""
    pass  # Currently identical to TaskCreate, but allows future divergence


class ToolInputListTasks(BaseModel):
    """Input structure for the list_tasks tool."""
    project_id: uuid.UUID
    status_filter: Optional[Literal['backlog', 'inprogress', 'done']] = None
    include_done: Optional[bool] = False
    
    @field_serializer('project_id')
    def serialize_project_id(self, uuid_value: uuid.UUID) -> str:
        """Convert project_id UUID to string during serialization."""
        return str(uuid_value)


class ToolInputUpdateTaskStatus(BaseModel):
    """Input structure for tools modifying task status (complete/remove)."""
    task_id: uuid.UUID
    
    @field_serializer('task_id')
    def serialize_task_id(self, uuid_value: uuid.UUID) -> str:
        """Convert task_id UUID to string during serialization."""
        return str(uuid_value)


# --- Models for Tool Outputs ---
class ToolOutputStatus(BaseModel):
    """Generic success/error status output."""
    status: Literal['success', 'error']
    message: Optional[str] = None  # Used for error messages


class ToolOutputTask(ToolOutputStatus):
    """Success output for operations returning a single task ID."""
    status: Literal['success'] = 'success'
    task_id: uuid.UUID
    
    @field_serializer('task_id')
    def serialize_task_id(self, uuid_value: uuid.UUID) -> str:
        """Convert task_id UUID to string during serialization."""
        return str(uuid_value)


class ToolOutputTaskList(ToolOutputStatus):
    """Success output for list_tasks."""
    status: Literal['success'] = 'success'
    tasks: List[Task]  # List of full Task objects
    project: Optional[Dict[str, Any]] = None  # Optional project info


class ToolErrorOutput(ToolOutputStatus):
    """Standard error output."""
    status: Literal['error'] = 'error'
    message: str  # Error message is required
