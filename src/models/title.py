"""Models for generated YouTube title candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TitleCandidate:
    """Represents one generated title candidate with explainability metadata."""

    title: str
    pattern_used: str
    emotion: str
    title_formula: str
    estimated_ctr: float
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Convert candidate to JSON-safe dictionary."""
        return {
            "title": self.title,
            "pattern_used": self.pattern_used,
            "emotion": self.emotion,
            "title_formula": self.title_formula,
            "estimated_ctr": self.estimated_ctr,
            "confidence": self.confidence,
            "reason": self.reason,
        }
