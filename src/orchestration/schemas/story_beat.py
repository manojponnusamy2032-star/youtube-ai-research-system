"""Day 4: Story beat schema for intelligent visual planning.

Story beats break a script into typed narrative units (HOOK, PROBLEM,
EXPLANATION, etc.) with importance, emphasis, and duration metadata.
This drives purposeful visual composition rather than flat scene-by-scene
translation.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


SUPPORTED_BEAT_TYPES = frozenset(
    {"HOOK", "PROBLEM", "EXPLANATION", "EXAMPLE", "CONTRAST",
     "INSIGHT", "ACTION", "CONCLUSION", "SOLUTION", "CTA"}
)


class StoryBeat(BaseModel):
    """A single typed story beat extracted from a script section."""

    beat_id: str  # e.g. "beat-01"
    beat_type: str  # one of SUPPORTED_BEAT_TYPES
    narration: str  # full narration text for this beat
    heading: str  # section heading
    key_message: str  # concise message this beat communicates
    importance: float = Field(ge=0.0, le=1.0)  # 0..1
    emphasis: str  # low / medium / high
    duration_seconds: int  # allocated time for this beat
    scene_count: int = Field(ge=1, default=1)  # how many visual scenes
    subject: str = ""  # detected subject from keyword matching
    character_focus: Optional[str] = None  # primary character or None
    story_arc: str = ""  # opening / development / resolution


class StoryBeatPlan(BaseModel):
    """Complete story beat plan for a script."""

    topic: str
    title: str
    beats: list[StoryBeat]
    total_duration_seconds: int
    warnings: list[str] = Field(default_factory=list)
