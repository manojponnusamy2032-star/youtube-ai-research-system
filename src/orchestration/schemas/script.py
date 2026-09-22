"""Script stage contract for the orchestration pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScriptSection(BaseModel):
    """One narrated section of the script.

    Each section maps to exactly one rendered scene.  ``duration_seconds``
    drives both narration pacing and scene length in the visual stage.
    """

    heading: str = Field(..., min_length=1)
    narration: str = Field(..., min_length=1)
    duration_seconds: int = Field(default=4, ge=1)


class ScriptPackage(BaseModel):
    """Structured script consumed by the visual planning stage."""

    topic: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    hook: str = Field(default="")
    sections: list[ScriptSection] = Field(default_factory=list)
    call_to_action: str = Field(default="")
    total_duration_seconds: int = Field(default=0, ge=0)

    # -- Day-2 real-adapter pass-through (all optional; mocks leave defaults) --
    # The real YAIRS script engine emits intro/section/scene payloads with
    # richer fields (transitions, examples, retention checkpoints, visual
    # directions, sfx) than the normalized ``sections`` above.  They are kept
    # verbatim so the real visual planner can rebuild its ScriptPlan without
    # information loss.
    intro: str = Field(default="")
    section_payloads: list[dict[str, Any]] = Field(default_factory=list)
    scene_payloads: list[dict[str, Any]] = Field(default_factory=list)
    estimated_duration_minutes: int = Field(default=0, ge=0)