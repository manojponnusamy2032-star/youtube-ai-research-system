"""Strategy agent interface."""

from __future__ import annotations

from src.orchestration.base import StageAgent
from src.orchestration.pipeline import STAGE_STRATEGY
from src.orchestration.schemas.research import ResearchPackage
from src.orchestration.schemas.strategy import StrategyPackage


class StrategyAgent(StageAgent[ResearchPackage, StrategyPackage]):
    """Produces a structured StrategyPackage from a ResearchPackage."""

    stage: str = STAGE_STRATEGY

    def run(self, request: ResearchPackage) -> StrategyPackage:
        raise NotImplementedError