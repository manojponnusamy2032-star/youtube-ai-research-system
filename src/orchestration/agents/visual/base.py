"""Visual planner agent interface."""

from __future__ import annotations

from src.orchestration.base import StageAgent
from src.orchestration.pipeline import STAGE_VISUAL_PLAN
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.visual import VisualPlan


class VisualPlannerAgent(StageAgent[ScriptPackage, VisualPlan]):
    """Produces a VisualPlan (render-ready) from a ScriptPackage."""

    stage: str = STAGE_VISUAL_PLAN

    def run(self, request: ScriptPackage) -> VisualPlan:
        raise NotImplementedError