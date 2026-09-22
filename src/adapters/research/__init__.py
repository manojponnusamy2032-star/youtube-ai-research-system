"""Research adapter interface placeholder (Principle 4)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from src.orchestration.schemas.research import ResearchPackage, ResearchRequest


class ResearchAdapter(ABC):
    """Interface future open-source research implementations plug into."""

    @abstractmethod
    def run(self, request: ResearchRequest) -> ResearchPackage:
        raise NotImplementedError
