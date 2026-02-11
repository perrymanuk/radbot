"""
Pydantic models for structured data interfaces in the radbot framework.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class UserInfoInput(BaseModel):
    """Schema for structured user information input."""

    user_id: str = Field(description="The unique ID of the user.")
    query_topic: str = Field(description="The topic the user is asking about.")


class ExtractedInfoOutput(BaseModel):
    """Schema for structured information extraction output."""

    summary: str = Field(description="A brief summary of the extracted information.")
    key_points: List[str] = Field(description="A list of key points.")


class MemoryQueryInput(BaseModel):
    """Schema for memory query input."""

    query: str = Field(description="The search query.")
    user_id: str = Field(description="The user ID to filter memory by.")
    max_results: Optional[int] = Field(
        default=5, description="Maximum number of results to return."
    )
