"""Research agent interface."""

from __future__ import annotations

from src.orchestration.base import StageAgent
from src.orchestration.pipeline import STAGE_RESEARCH
from src.orchestration.schemas.research import ResearchPackage, ResearchRequest


class ResearchAgent(StageAgent[ResearchRequest, ResearchPackage]):
    """Produces a structured ResearchPackage from a ResearchRequest."""

    stage: str = STAGE_RESEARCH

    def run(self, request: ResearchRequest) -> ResearchPackage:
        raise NotImplementedError