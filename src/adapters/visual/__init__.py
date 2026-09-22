"""Visual adapter interface placeholder (Principle 4)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.visual import VisualPlan


class VisualAdapter(ABC):
    """Interface future open-source visual implementations plug into."""

    @abstractmethod
    def run(self, request: ScriptPackage) -> VisualPlan:
        raise NotImplementedError
