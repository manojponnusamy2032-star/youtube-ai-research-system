"""Script agent interface."""

from __future__ import annotations

from src.orchestration.base import StageAgent
from src.orchestration.pipeline import STAGE_SCRIPT
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.strategy import StrategyPackage


class ScriptAgent(StageAgent[StrategyPackage, ScriptPackage]):
    """Produces a structured ScriptPackage from a StrategyPackage."""

    stage: str = STAGE_SCRIPT

    def run(self, request: StrategyPackage) -> ScriptPackage:
        raise NotImplementedError