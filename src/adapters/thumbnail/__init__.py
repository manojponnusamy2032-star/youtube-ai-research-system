"""Thumbnail adapter interface placeholder (Principle 4)."""
from __future__ import annotations
from abc import ABC, abstractmethod


class ThumbnailAdapter(ABC):
    """Interface for a future open-source thumbnail implementation."""

    @abstractmethod
    def generate(self, title: str, output_path: str) -> str:
        raise NotImplementedError
