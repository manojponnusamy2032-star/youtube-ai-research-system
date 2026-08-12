"""
Models for analysis results in YouTube AI Research System.

This module defines Pydantic models for analysis data generated
by the Analysis Agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class DifficultyLevel(str, Enum):
    """Difficulty levels for video analysis."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    ALL_LEVELS = "all_levels"


@dataclass
class Analysis:
    """Analysis model for YouTube video analysis results."""
    video_id: str
    hook_type: str
    opening_summary: str
    main_topic: str
    target_audience: str
    emotion: str
    story_structure: str
    title_formula: str
    thumbnail_pattern: str
    cta_type: str
    value_proposition: str
    estimated_video_style: str
    summary: str
    confidence_score: float
    analysis_model: str
    sub_topics: list[str] = field(default_factory=list)
    retention_techniques: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    psychological_triggers: list[str] = field(default_factory=list)
    difficulty_level: DifficultyLevel = DifficultyLevel.ALL_LEVELS
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "video_id": self.video_id,
            "hook_type": self.hook_type,
            "opening_summary": self.opening_summary,
            "main_topic": self.main_topic,
            "sub_topics": self.sub_topics,
            "target_audience": self.target_audience,
            "emotion": self.emotion,
            "story_structure": self.story_structure,
            "title_formula": self.title_formula,
            "thumbnail_pattern": self.thumbnail_pattern,
            "retention_techniques": self.retention_techniques,
            "cta_type": self.cta_type,
            "keywords": self.keywords,
            "psychological_triggers": self.psychological_triggers,
            "value_proposition": self.value_proposition,
            "difficulty_level": self.difficulty_level.value,
            "estimated_video_style": self.estimated_video_style,
            "summary": self.summary,
            "confidence_score": self.confidence_score,
            "analysis_model": self.analysis_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }