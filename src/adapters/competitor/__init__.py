"""Competitor-intelligence adapter interface placeholder (Principle 4)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class CompetitorAdapter(ABC):
    """Interface for a future competitor-intelligence implementation."""

    @abstractmethod
    def analyze(self, topic: str) -> dict[str, Any]:
        raise NotImplementedError
