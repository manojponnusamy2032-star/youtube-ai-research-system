"""Schemas for research workflow execution endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    """Request payload for end-to-end research workflow."""

    keyword: str = Field(..., min_length=1, max_length=200)
    max_results: int = Field(default=50, ge=1, le=50)
    limit: int = Field(default=50, ge=1, le=200)
    force_reanalyze: bool = False
    continue_on_error: bool = False
    run_title_generation: bool = False
    run_content_generation: bool = False
    run_render_job_management: bool = False
    run_final_media_generation: bool = False
    topic: str | None = None
    title_topic: str | None = None
    audience: str | None = None
    niche: str | None = None
    trend_data: Any = None
    final_media_output_path: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "keyword": "youtube automation",
                "max_results": 25,
                "limit": 25,
                "run_title_generation": True,
                "run_content_generation": True,
                "topic": "YouTube AI Automation",
                "audience": "new creators",
                "niche": "education",
                "trend_data": ["AI workflow", "faceless channels"],
            }
        }
    }


class WorkflowAcceptedResponse(BaseModel):
    """Immediate response after background workflow scheduling."""

    workflow_id: str
    status: str
    created_at: datetime


class WorkflowStatusResponse(BaseModel):
    """Workflow status query response."""

    workflow_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
