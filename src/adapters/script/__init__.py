"""Script adapter interface placeholder (Principle 4)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.strategy import StrategyPackage


class ScriptAdapter(ABC):
    """Interface future open-source script implementations plug into."""

    @abstractmethod
    def run(self, request: StrategyPackage) -> ScriptPackage:
        raise NotImplementedError
