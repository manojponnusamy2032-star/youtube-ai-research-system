"""Production / render stage contracts for the orchestration pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.orchestration.schemas.visual import VisualPlan


class ProductionRequest(BaseModel):
    """Input for the renderer adapter.

    ``render_config`` maps 1:1 onto the existing ``RenderConfig`` dataclass
    fields (width, height, fps, video_codec, audio_format, ...).
    """

    job_id: str = Field(..., min_length=1)
    visual_plan: VisualPlan
    output_path: str = Field(..., min_length=1, description="Final MP4 destination")
    render_config: dict[str, Any] = Field(default_factory=dict)


class VideoArtifact(BaseModel):
    """Final output produced by a renderer adapter."""

    job_id: str = Field(..., min_length=1)
    status: str = Field(default="completed", pattern="^(completed|failed)$")
    output_path: str = Field(default="")
    mp4_exists: bool = Field(default=False)
    file_size_bytes: int = Field(default=0, ge=0)
    scene_count: int = Field(default=0, ge=0)
    total_duration_seconds: int = Field(default=0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)