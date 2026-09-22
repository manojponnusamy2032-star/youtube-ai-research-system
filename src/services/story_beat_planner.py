"""Day 4: StoryBeatPlanner — converts ScriptPackage sections into typed story beats.

Uses the V1.6 ``VisualBeatEngine`` for keyword-based beat detection and
augments with story arc awareness, key-message extraction, importance-based
duration allocation, and emphasis scoring.

Deterministic: the same inputs always produce the same beats.
"""

from __future__ import annotations

import math
from typing import Optional

from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.story_beat import (
    StoryBeat,
    StoryBeatPlan,
    SUPPORTED_BEAT_TYPES,
)
from src.services.visual_beat_engine import BEAT_EMPHASIS, BEAT_IMPORTANCE, VisualBeatEngine


# ---------------------------------------------------------------------------
# Story-arc role mapping (position -> role hint for the engine)
# ---------------------------------------------------------------------------

_ARC_OPENING_FRACTION = 0.20
_ARC_CLOSING_FRACTION = 0.20

# Only these explicit semantic roles may override keyword detection.
_SEMANTIC_ROLE_HINTS = frozenset({
    "hook", "problem", "contrast", "comparison", "explanation", "example",
    "insight", "action", "conclusion", "solution", "method", "cta",
    "proof", "b_roll",
})


def _arc_role(index: int, total: int) -> str:
    """Return 'opening', 'development', or 'resolution' for *index*."""
    if total <= 1:
        return "opening"
    if index / (total - 1) <= _ARC_OPENING_FRACTION:
        return "opening"
    if index / (total - 1) >= 1 - _ARC_CLOSING_FRACTION:
        return "resolution"
    return "development"


def _extract_key_message(heading: str, narration: str) -> str:
    """Derive a concise key message from heading or first sentence."""
    if heading and len(heading.strip()) > 3:
        return heading.strip()[:140]
    text = (narration or "").strip()
    for sep in (". ", "! ", "? "):
        idx = text.find(sep)
        if idx > 5:
            return text[: idx + 1][:140]
    return text[:140] if text else ""




# ---------------------------------------------------------------------------
# Duration allocation
# ---------------------------------------------------------------------------

def _allocate_durations(
    base_durations: list[int],
    importances: list[float],
    total_duration: int,
) -> list[int]:
    """Allocate *total_duration* weighted by importance, preserving sum."""
    if not base_durations:
        return []
    weights = [0.7 + 0.3 * imp for imp in importances]
    raw = [d * w for d, w in zip(base_durations, weights)]
    total_raw = sum(raw)
    if total_raw == 0:
        return list(base_durations)
    allocated = [max(3, int(round(r / total_raw * total_duration))) for r in raw]
    diff = total_duration - sum(allocated)
    idx = 0
    while diff != 0:
        slot = idx % len(allocated)
        candidate = allocated[slot] + (1 if diff > 0 else -1)
        if candidate >= 3:
            allocated[slot] = candidate
            diff += -1 if diff > 0 else 1
        idx += 1
        if idx > len(allocated) * 20:
            break
    return allocated


# ---------------------------------------------------------------------------
# StoryBeatPlanner
# ---------------------------------------------------------------------------

class StoryBeatPlanner:
    """Convert a ``ScriptPackage`` into a ``StoryBeatPlan``.

    Reuses the V1.6 ``VisualBeatEngine`` for keyword-based detection, then
    layers on story-arc awareness, duration reallocation, and emphasis scoring.
    """

    def __init__(self, engine: Optional[VisualBeatEngine] = None) -> None:
        self._engine = engine or VisualBeatEngine()

    def plan(self, script: ScriptPackage) -> StoryBeatPlan:
        """Produce a ``StoryBeatPlan`` from the script sections."""
        sections = script.sections
        if not sections:
            return StoryBeatPlan(
                topic=script.topic,
                title=script.title,
                beats=[],
                total_duration_seconds=0,
                warnings=["No sections provided — empty beat plan."],
            )

        warnings: list[str] = []
        total = len(sections)
        raw_durations: list[int] = []
        importances: list[float] = []
        engine_beats: list = []

        for idx, section in enumerate(sections):
            arc = _arc_role(idx, total)
            # Day 4 must reuse script content: only honor explicit semantic scene
            # roles (hook/problem/...) as hard overrides.  Generic arc labels
            # ("opening"/"development"/"resolution") carry no content signal, so
            # pass them through as empty and let keyword + position rules decide.
            role_hint = arc if arc.lower() in _SEMANTIC_ROLE_HINTS else ""
            eb = self._engine.detect(
                section.narration,
                scene_index=idx,
                total_scenes=total,
                scene_role=role_hint,
            )
            beat_type: str = eb.type
            if beat_type not in SUPPORTED_BEAT_TYPES:
                beat_type = "EXPLANATION"
                warnings.append(
                    f"Section {idx + 1}: unknown beat type '{eb.type}', "
                    f"falling back to EXPLANATION."
                )
            engine_beats.append(eb)
            raw_durations.append(max(3, section.duration_seconds))
            importances.append(eb.importance)

        allocated = _allocate_durations(
            raw_durations, importances, script.total_duration_seconds
        )

        beats: list[StoryBeat] = []
        for idx, (section, eb, dur) in enumerate(
            zip(sections, engine_beats, allocated)
        ):
            arc = _arc_role(idx, total)
            beat_type = eb.type
            if beat_type not in SUPPORTED_BEAT_TYPES:
                beat_type = "EXPLANATION"
            beats.append(
                StoryBeat(
                    beat_id=f"beat-{idx + 1:02d}",
                    beat_type=beat_type,
                    narration=section.narration,
                    heading=section.heading,
                    key_message=_extract_key_message(
                        section.heading, section.narration
                    ),
                    importance=eb.importance,
                    emphasis=eb.emphasis,
                    duration_seconds=dur,
                    scene_count=_scene_count(dur, eb.emphasis),
                    subject=eb.subject,
                    story_arc=arc,
                )
            )

        return StoryBeatPlan(
            topic=script.topic,
            title=script.title,
            beats=beats,
            total_duration_seconds=sum(b.duration_seconds for b in beats),
            warnings=warnings,
        )

def _scene_count(duration: int, emphasis: str) -> int:
    """How many visual scenes should this beat span?"""
    if emphasis == "high" and duration >= 20:
        return 3
    if duration >= 14:
        return 2
    return 1
