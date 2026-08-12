"""Common API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized JSON error payload."""

    detail: str = Field(..., description="Human-readable error detail")
    code: str = Field(..., description="Stable error code")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: str = Field(default="ok")
    service: str = Field(default="youtube-ai-research-system")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MetricsResponse(BaseModel):
    """System metrics response."""

    videos: int = 0
    transcripts: int = 0
    analyses: int = 0
    scripts: int = 0
    content_packages: int = 0
    workflows_total: int = 0
    workflows_running: int = 0
    workflows_completed: int = 0
    workflows_failed: int = 0
