"""Deterministic mock strategy agent."""

from __future__ import annotations

from src.orchestration.agents.strategy.base import StrategyAgent
from src.orchestration.schemas.research import ResearchPackage
from src.orchestration.schemas.strategy import StrategyPackage


class MockStrategyAgent(StrategyAgent):
    """Mock implementation — deterministic angle built from the research."""

    def run(self, request: ResearchPackage) -> StrategyPackage:
        return StrategyPackage(
            topic=request.topic,
            angle=(
                "People do not quit because they lack talent; they quit because "
                "their expectations do not match the real shape of the learning curve."
            ),
            narrative_outline=[
                "Open on the common story: excited start, then the quit.",
                "Reveal the non-linear learning curve and the frustration plateau.",
                "Explain deliberate practice and why it feels slow on purpose.",
                "Swap motivation for a repeatable daily system.",
                "Close with the compounding breakthrough and a next-step call to action.",
            ],
            key_messages=[
                "Progress is non-linear: plateaus come before breakthroughs.",
                "Early expectations are the real enemy, not ability.",
                "Deliberate practice with feedback beats volume.",
                "Systems carry you on low-motivation days.",
            ],
            emotional_triggers=["relief", "hope", "curiosity"],
            hook_idea=(
                "Most people quit a new skill right before the moment it would "
                "have started working."
            ),
            call_to_action="Commit to one focused 25-minute session today.",
            target_audience=request.target_audience or "general",
            confidence=0.8,
        )