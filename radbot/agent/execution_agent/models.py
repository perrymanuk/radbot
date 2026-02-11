"""
Task models for the execution agent.

This module provides Pydantic models for task instructions and results
used by the Axel execution agent and its worker agents.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Types of tasks that can be performed by worker agents."""

    CODE_IMPLEMENTATION = "code_implementation"
    DOCUMENTATION = "documentation"
    TESTING = "testing"


class TaskInstruction(BaseModel):
    """Instructions from Axel to a worker agent."""

    task_id: str = Field(..., description="Unique identifier for this task")
    task_type: TaskType = Field(..., description="Type of task to perform")
    specification: str = Field(
        ..., description="Markdown documentation with task details"
    )
    context: Dict[str, str] = Field(
        default_factory=dict, description="Additional context needed for task"
    )
    dependencies: List[str] = Field(
        default_factory=list, description="IDs of tasks this depends on"
    )


class TaskStatus(str, Enum):
    """Status of a task execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class TaskResult(BaseModel):
    """Results from a worker agent back to Axel."""

    task_id: str = Field(..., description="ID of the completed task")
    task_type: TaskType = Field(..., description="Type of task that was performed")
    status: TaskStatus = Field(..., description="Completion status of the task")
    summary: str = Field(..., description="Brief summary of what was accomplished")
    details: str = Field(..., description="Detailed markdown description of work done")
    artifacts: Dict[str, str] = Field(
        default_factory=dict, description="Produced artifacts (code, docs, etc.)"
    )
    error_message: Optional[str] = Field(
        None, description="Error details if status is FAILED"
    )
