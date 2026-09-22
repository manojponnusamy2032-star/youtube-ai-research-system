"""Correction target dependency map (Day 5).

Conceptual pipeline dependency chain:

    RESEARCH -> STRATEGY -> SCRIPT -> STORY_BEATS -> VISUAL_BEATS -> RENDER

When an artifact changes, ONLY downstream artifacts are invalidated.
Examples:

    VISUAL_BEATS changed -> invalidate render (do NOT invalidate script)
    SCRIPT changed       -> invalidate story beats, visual beats, render
    RENDER changed       -> only re-render
"""

from __future__ import annotations

from src.orchestration.pipeline import (
    STAGE_RENDER,
    STAGE_SCRIPT,
    STAGE_STRATEGY,
    STAGE_VISUAL_PLAN,
)
from src.orchestration.repair.models import CorrectionTarget

# Ordered dependency chain, upstream -> downstream.
CORRECTION_CHAIN: list[CorrectionTarget] = [
    CorrectionTarget.RESEARCH,
    CorrectionTarget.STRATEGY,
    CorrectionTarget.SCRIPT,
    CorrectionTarget.STORY_BEATS,
    CorrectionTarget.VISUAL_BEATS,
    CorrectionTarget.RENDER,
]

# Correction target -> (pipeline stage to re-run, VideoJob artifact field).
_TARGET_STAGE: dict[CorrectionTarget, str] = {
    CorrectionTarget.RESEARCH: "research",
    CorrectionTarget.STRATEGY: STAGE_STRATEGY,
    CorrectionTarget.SCRIPT: STAGE_SCRIPT,
    CorrectionTarget.STORY_BEATS: STAGE_VISUAL_PLAN,
    CorrectionTarget.VISUAL_BEATS: STAGE_VISUAL_PLAN,
    CorrectionTarget.RENDER: STAGE_RENDER,
}

_TARGET_ARTIFACT: dict[CorrectionTarget, str] = {
    CorrectionTarget.RESEARCH: "research",
    CorrectionTarget.STRATEGY: "strategy",
    CorrectionTarget.SCRIPT: "script",
    CorrectionTarget.STORY_BEATS: "visual_plan",
    CorrectionTarget.VISUAL_BEATS: "visual_plan",
    CorrectionTarget.RENDER: "artifact",
}


def downstream_of(target: CorrectionTarget) -> list[CorrectionTarget]:
    """Return all targets strictly downstream of ``target`` (inclusive of render)."""
    index = CORRECTION_CHAIN.index(target)
    return CORRECTION_CHAIN[index:]


def invalidation_set(target: CorrectionTarget) -> list[CorrectionTarget]:
    """Targets whose artifacts must be invalidated when ``target`` changes.

    Includes ``target`` itself plus everything downstream.
    """
    return downstream_of(target)


def is_downstream(candidate: CorrectionTarget, reference: CorrectionTarget) -> bool:
    """True when ``candidate`` is at or below ``reference`` in the chain."""
    return (
        CORRECTION_CHAIN.index(candidate)
        >= CORRECTION_CHAIN.index(reference)
    )


def pipeline_stage_for(target: CorrectionTarget) -> str:
    """Map a correction target onto the orchestrator pipeline stage to re-run."""
    return _TARGET_STAGE[target]


def artifact_field_for(target: CorrectionTarget) -> str:
    """Map a correction target onto the VideoJob artifact field it rewrites."""
    return _TARGET_ARTIFACT[target]
