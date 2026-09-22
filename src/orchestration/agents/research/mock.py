"""Deterministic mock research agent.

Returns a fixed, valid ResearchPackage.  The topic is woven into the summary
so downstream stages remain coherent for any requested topic.
"""

from __future__ import annotations

from src.orchestration.agents.research.base import ResearchAgent
from src.orchestration.schemas.research import ResearchPackage, ResearchRequest

DEFAULT_TOPIC = "Why Most People Quit Learning a Skill Too Early"


class MockResearchAgent(ResearchAgent):
    """Mock implementation — no network, no LLM, fully deterministic."""

    def run(self, request: ResearchRequest) -> ResearchPackage:
        topic = request.topic.strip()
        summary = (
            f"{topic}. Research on skill acquisition shows that most people "
            "quit a new skill within the first few weeks, usually right before "
            "the first visible breakthrough. The pattern repeats across music, "
            "languages, coding and fitness because expectations, not talent, "
            "drive the decision to stop."
        )
        return ResearchPackage(
            topic=topic,
            niche=request.niche,
            summary=summary,
            key_facts=[
                "Most skill progress is non-linear: long flat plateaus precede sudden jumps.",
                "Beginners typically overestimate the speed of early progress.",
                "The 'valley of despair' is a well-documented phase in the Dunning-Kruger curve.",
                "Consistency beats intensity for long-term skill retention.",
                "Deliberate practice with feedback outperforms passive repetition.",
            ],
            pain_points=[
                "Feeling slow at the start despite high motivation.",
                "Comparing week-1 output to experts' polished results.",
                "Not seeing measurable progress for weeks.",
                "Believing a 'talent gene' determines success.",
            ],
            sub_topics=[
                "The learning curve and its plateaus",
                "How expectations shape persistence",
                "Deliberate practice vs. mindless repetition",
                "Building systems that survive low motivation",
            ],
            sources=[
                "mock://skills-research/learning-curves",
                "mock://skills-research/plateau-studies",
                "mock://skills-research/deliberate-practice",
            ],
            target_audience=request.audience or "general",
            confidence=0.85,
        )