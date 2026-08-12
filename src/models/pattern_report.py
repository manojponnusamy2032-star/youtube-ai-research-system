"""Dataclasses for pattern extraction reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PatternReport:
    """Serializable report for dataset-wide viral pattern analysis."""

    generated_at: str
    videos_analyzed: int
    hooks: dict[str, float] = field(default_factory=dict)
    stories: dict[str, float] = field(default_factory=dict)
    emotions: dict[str, float] = field(default_factory=dict)
    titles: dict[str, float] = field(default_factory=dict)
    thumbnail_psychology: dict[str, float] = field(default_factory=dict)
    retention: dict[str, float] = field(default_factory=dict)
    top_channels: list[dict[str, Any]] = field(default_factory=list)
    top_topics: list[dict[str, Any]] = field(default_factory=list)
    average_viral_score: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert report to a JSON-safe dictionary."""
        return asdict(self)
