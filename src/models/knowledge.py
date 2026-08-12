"""Knowledge models for reusable viral strategy entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class KnowledgeEntry:
    """Represents one reusable strategy item in the knowledge base."""

    category: str
    pattern: str
    frequency: float
    average_views: float
    confidence: float
    recommendation: str
    id: int | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert entry into a serializable dictionary."""
        return {
            "id": self.id,
            "category": self.category,
            "pattern": self.pattern,
            "frequency": self.frequency,
            "average_views": self.average_views,
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "created_at": self.created_at,
        }
