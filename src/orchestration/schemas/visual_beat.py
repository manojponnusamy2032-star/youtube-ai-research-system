"""Day 4: Visual beat schema for intelligent scene composition.

A VisualBeat represents a single visual scene derived from a story beat,
containing character state, camera intent, emphasis scoring, transition
type, and state-change tracking to guarantee visual progression.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VisualState(BaseModel):
    """Snapshot of visual state for anti-static-sequence tracking."""

    character_position: str = "center"
    character_action: str = "idle"
    character_emotion: str = "neutral"
    character_pose: str = "idle"
    camera_pattern: str = "static"
    environment: str = ""
    objects: list[str] = Field(default_factory=list)


class VisualBeat(BaseModel):
    """A single visual scene derived from a story beat."""

    beat_id: str  # e.g. "vb-01"
    story_beat_id: str  # links to StoryBeat.beat_id
    scene_number: int  # 1-based
    scene_purpose: str  # human-readable purpose of this scene
    narration_text: str  # narration for this scene

    # Character state
    character_action: str
    character_emotion: str
    character_pose: str

    # Camera
    camera_pattern: str

    # Environment and objects
    environment: str
    objects: list[str] = Field(default_factory=list)

    # Text overlay
    text_overlay: str

    # Emphasis
    emphasis_score: float = Field(ge=0.0, le=1.0)
    emphasis_label: str  # low / medium / high

    # Transition to next scene
    transition_type: str
    transition_duration: float = 0.5

    # State tracking
    state_changed: list[str] = Field(default_factory=list)

    # Duration
    duration_seconds: int


class VisualBeatPlan(BaseModel):
    """Complete visual beat plan produced by the VisualBeatPlanner."""

    beats: list[VisualBeat]
    total_duration_seconds: int
    state_progression: list[list[str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
