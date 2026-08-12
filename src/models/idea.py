"""
Models for generated YouTube video ideas.

This module defines Pydantic models for video ideas generated
by the Idea Generator Agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


@dataclass
class Idea:
    """Represents a generated YouTube video idea."""
    id: int | None = None
    title: str = ""
    hook: str = ""
    emotion: str = ""
    topic: str = ""
    virality_score: float = 0.0
    confidence_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "id": self.id,
            "title": self.title,
            "hook": self.hook,
            "emotion": self.emotion,
            "topic": self.topic,
            "virality_score": self.virality_score,
            "confidence_score": self.confidence_score,
        }