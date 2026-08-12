"""
Job model for YAIRS.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Job(BaseModel):
    """
    Represents one unit of work in the pipeline.
    """

    id: Optional[int] = None

    agent_name: str

    status: str = "pending"

    payload: str = ""

    error: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    started_at: Optional[datetime] = None

    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True