"""Deterministic mock script agent.

Builds a short, valid, fully narratable script from the strategy.  Each
section becomes one rendered scene in the visual stage.

Section durations are estimated from the narration word count (~2.5 spoken
words per second) so the narration fits inside its scene instead of being
truncated by the renderer's ``-shortest`` audio mux.
"""

from __future__ import annotations

import math

from src.orchestration.agents.script.base import ScriptAgent
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.strategy import StrategyPackage

DEFAULT_TITLE = "Why Most People Quit Learning a Skill Too Early"

# Conservative spoken-words-per-second estimate used to size each scene so
# narration is never clipped by the scene video length.
_WORDS_PER_SECOND = 2.5


class MockScriptAgent(ScriptAgent):
    """Mock implementation — deterministic sections with fixed narration."""

    # (heading, narration, minimum_duration_seconds)
    _SECTIONS: list[tuple[str, str, int]] = [
        (
            "The 100-Hour Myth",
            "Most people quit a new skill right before the moment it would have "
            "started working. The first weeks feel slow, so the beginner assumes "
            "progress is broken.",
            5,
        ),
        (
            "The Frustration Plateau",
            "Skill growth is not a straight line. It is a staircase of long flat "
            "plateaus followed by sudden jumps. Quitters leave during the plateau, "
            "just before the jump.",
            5,
        ),
        (
            "Expectations vs Reality",
            "Beginners overestimate early speed and underestimate later speed. "
            "When reality does not match the fantasy, the brain looks for a reason "
            "to stop.",
            5,
        ),
        (
            "Deliberate Practice Feels Slow",
            "Real practice means focused reps with feedback, and it feels boring "
            "on purpose. Mindless repetition feels productive but changes nothing.",
            5,
        ),
        (
            "Build a System, Not Motivation",
            "Systems carry you on the days motivation disappears. One focused "
            "25-minute session beats a heroic three-hour session you will not repeat.",
            5,
        ),
        (
            "The Breakthrough Is Closer Than You Think",
            "Keep the session small, keep the feedback loop tight, and let the "
            "plateau do its work. The breakthrough comes from the reps you did not "
            "want to do.",
            5,
        ),
    ]

    def run(self, request: StrategyPackage) -> ScriptPackage:
        sections = [
            ScriptSection(
                heading=heading,
                narration=narration,
                duration_seconds=max(
                    minimum,
                    math.ceil(len(narration.split()) / _WORDS_PER_SECOND),
                ),
            )
            for heading, narration, minimum in self._SECTIONS
        ]
        total = sum(section.duration_seconds for section in sections)
        return ScriptPackage(
            topic=request.topic,
            title=DEFAULT_TITLE,
            hook=sections[0].narration if sections else "",
            sections=sections,
            call_to_action=request.call_to_action,
            total_duration_seconds=total,
        )