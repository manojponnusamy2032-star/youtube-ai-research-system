"""Strategy adapter interface placeholder (Principle 4)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.orchestration.schemas.research import ResearchPackage
from src.orchestration.schemas.strategy import StrategyPackage


class StrategyAdapter(ABC):
    """Interface future open-source strategy implementations plug into."""

    @abstractmethod
    def run(self, request: ResearchPackage) -> StrategyPackage:
        raise NotImplementedError
