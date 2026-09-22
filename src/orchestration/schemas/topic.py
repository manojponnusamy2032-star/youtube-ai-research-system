"""Topic intake contract for the orchestration pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TopicRequest(BaseModel):
    """User-facing entry point for a single video topic.

    This is the only contract a caller needs to start the pipeline.  Optional
    context (niche, audience) may be refined by future Trend-Hunter / Topic
    Scorer agents without changing the pipeline's stage contracts.
    """

    topic: str = Field(..., min_length=3, max_length=500, description="The video topic")
    niche: str = Field(default="", max_length=200, description="Optional niche context")
    audience: str = Field(default="general", max_length=100, description="Target audience")
    job_id: str | None = Field(default=None, description="Optional pre-assigned job id")