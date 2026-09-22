"""Visual planning contract for the orchestration pipeline.

The ``VisualPlan`` is the bridge between the orchestration layer and the
existing YAIRS render pipeline.  Instead of inventing a second renderer input,
``render_job_plan`` holds exactly the ``RenderJobPlan``-shaped dictionary that
the existing ``RenderJobManager`` / ``RenderPipelineOrchestrator`` already
consume.  ``scenes`` is the human-readable structured mirror used for
artifacts and upstream planning.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VisualScenePlan(BaseModel):
    """Structured visual intent for one scene."""

    scene_number: int = Field(..., ge=1)
    duration_seconds: int = Field(..., ge=1)
    narration: str = Field(default="")
    render_type: str = Field(default="stickman_animation")
    visual_prompt: str = Field(default="")
    animation_instructions: str = Field(default="")
    camera_instructions: str = Field(default="")
    audio_requirements: str = Field(default="narration")
    character_action: str = Field(default="idle")
    motions: list[dict[str, Any]] = Field(default_factory=list)
    transition_to_next: dict[str, Any] | None = None
    audio_request: dict[str, Any] | None = None
    visual_description: dict[str, Any] = Field(default_factory=dict)


class VisualPlan(BaseModel):
    """Complete visual plan handed to the renderer adapter."""

    topic: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    job_id: str | None = Field(default=None)
    scenes: list[VisualScenePlan] = Field(default_factory=list)
    # Exact dict consumed by the existing RenderJobManager / render pipeline.
    render_job_plan: dict[str, Any] = Field(default_factory=dict)
    total_duration_seconds: int = Field(default=0, ge=0)