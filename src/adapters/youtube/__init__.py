"""YouTube publisher adapter interface placeholder (Principle 4)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class YouTubeAdapter(ABC):
    """Interface for a future YouTube upload/analytics implementation."""

    @abstractmethod
    def publish(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
