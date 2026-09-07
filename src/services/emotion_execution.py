"""V1.6-F: deterministic character emotion execution.

Activates the renderer's existing emotion systems (per-emotion color tint
blended into the character base color and emotion-driven posture cues) by
staging an ``emotion`` key on exactly one character per scene: the character
the scene is emotionally about, resolved from planner-authoritative signals.

Derivation chain (highest priority first, per the approved specification):

1. Explicitly authored ``emotion`` on the selected character dict — never
   modified or duplicated.
2. V1.4 story treatment (``visual_planning["story"]["treatment"]``).
3. V1.3 beat type (``beat["type"]``).
4. V1.3 scene role (deterministic fallback).
5. ``neutral`` fallback.

No forced alternation between consecutive scenes: when two scenes
legitimately map to the same emotion, the same emotion is staged. Semantic
correctness takes precedence over visual variety.

The layer is additive and pure: input character dicts are never mutated; the
bearer's dict is shallow-copied with the ``emotion`` key added and all other
members pass through untouched. Every generated value is validated against
``scene_composition.SUPPORTED_EMOTIONS`` so it always remains compatible
with ``CharacterSpec(**character_dict)`` and the existing renderer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.services.scene_composition import SUPPORTED_EMOTIONS

# V1.6-F feature flag. Default OFF: when disabled the layer returns the
# caller's character list unchanged and never adds emotion keys or metadata.
VISUAL_EMOTION_EXECUTION_ENABLED = False

NEUTRAL_EMOTION = "neutral"

# Fixed, deterministic semantic mappings over the planner vocabularies.
TREATMENT_EMOTIONS = {
    "establish": "excited",
    "problem_focus": "frustrated",
    "compare": "surprised",
    "explain": "focused",
    "proof": "focused",
    "solution_growth": "happy",
    "cta": "excited",
}

BEAT_EMOTIONS = {
    "hook": "excited",
    "problem": "frustrated",
    "contrast": "surprised",
    "explanation": "focused",
    "example": "focused",
    "solution": "happy",
    "cta": "excited",
}

ROLE_EMOTIONS = {
    "hook": "excited",
    "explanation": "focused",
    "conclusion": "excited",
    "cta": "excited",
}


def _normalize(value: Any) -> str:
    """Normalize a vocabulary value for deterministic comparison."""
    return str(value or "").strip().lower()


def _validated_emotion(value: Any, warnings: list[str], context: str) -> str:
    """Return ``value`` only when the renderer vocabulary supports it."""
    emotion = _normalize(value)
    if emotion in SUPPORTED_EMOTIONS:
        return emotion
    warnings.append(f"unsupported_emotion:{context}:{emotion or 'empty'}")
    return NEUTRAL_EMOTION


def _attention_primary(
    planning_metadata: dict[str, Any] | None,
) -> tuple[str, str] | None:
    """Resolve the V1.4-E attention primary target as ``(name, kind)``.

    Returns ``None`` when there is no usable attention information at all
    (missing/malformed planning metadata), which is distinct from an explicit
    target that is simply not a character in the scene.
    """
    if not isinstance(planning_metadata, dict):
        return None
    attention = planning_metadata.get("attention")
    if not isinstance(attention, dict):
        return None
    name = _normalize(attention.get("primary_target"))
    if not name or name == "scene":
        return None
    return name, _normalize(attention.get("target_kind"))


def _resolve_emotion(
    planning_metadata: dict[str, Any] | None,
    beat: dict[str, Any] | None,
    scene_role: str,
    warnings: list[str],
) -> tuple[str, str]:
    """Derive ``(emotion, source)`` via treatment -> beat -> role -> neutral."""
    if isinstance(planning_metadata, dict):
        story = planning_metadata.get("story")
        if isinstance(story, dict):
            treatment = _normalize(story.get("treatment"))
            if treatment:
                if treatment in TREATMENT_EMOTIONS:
                    emotion = _validated_emotion(
                        TREATMENT_EMOTIONS[treatment], warnings, f"treatment:{treatment}"
                    )
                    return emotion, "treatment"
                warnings.append(f"unknown_treatment:{treatment}")
    if isinstance(beat, dict):
        beat_type = _normalize(beat.get("type"))
        if beat_type:
            if beat_type in BEAT_EMOTIONS:
                emotion = _validated_emotion(
                    BEAT_EMOTIONS[beat_type], warnings, f"beat:{beat_type}"
                )
                return emotion, "beat"
            warnings.append(f"unknown_beat:{beat_type}")
    role = _normalize(scene_role)
    if role and role in ROLE_EMOTIONS:
        emotion = _validated_emotion(ROLE_EMOTIONS[role], warnings, f"role:{role}")
        return emotion, "role"
    return NEUTRAL_EMOTION, "neutral"


@dataclass(frozen=True)
class EmotionDecision:
    """What the V1.6-F emotion layer decided for one scene."""

    scene_index: int
    bearer: str | None = None
    emotion: str = NEUTRAL_EMOTION
    source: str = ""  # explicit | treatment | beat | role | neutral
    changed: bool = False
    skipped: bool = False
    reason: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        # JSON-stable serialization: sequences become lists so the payload
        # survives pipeline metadata round-trips unchanged.
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class EmotionResult:
    """Per-scene output: staged character dicts + the decision."""

    characters: tuple[dict[str, Any], ...] = ()
    decision: EmotionDecision = field(
        default_factory=lambda: EmotionDecision(scene_index=0)
    )


def apply_emotion_execution(
    characters: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    scene_index: int = 0,
    scene_role: str = "general",
    planning_metadata: dict[str, Any] | None = None,
    beat: dict[str, Any] | None = None,
) -> EmotionResult:
    """Stage a deterministic ``emotion`` on the single emotion-bearer.

    The bearer is the V1.4-E attention primary target when it is a character
    present in the scene; otherwise (no usable attention information) the
    first declared character. Explicitly authored emotion on the bearer is
    preserved untouched. Input members are never mutated: the bearer's dict
    is shallow-copied, every other member is passed through by reference.
    """
    members = list(characters) if characters is not None else []

    if not VISUAL_EMOTION_EXECUTION_ENABLED:
        decision = EmotionDecision(
            scene_index=scene_index,
            skipped=True,
            reason="emotion execution disabled (flag OFF)",
        )
        return EmotionResult(tuple(members), decision)

    if not members:
        decision = EmotionDecision(
            scene_index=scene_index,
            skipped=True,
            reason="no characters in scene",
        )
        return EmotionResult((), decision)

    dict_positions = [
        position
        for position, member in enumerate(members)
        if isinstance(member, dict)
    ]
    if not dict_positions:
        decision = EmotionDecision(
            scene_index=scene_index,
            skipped=True,
            reason="no character dicts available",
            warnings=("non_dict_members",),
        )
        return EmotionResult(tuple(members), decision)

    warnings: list[str] = []
    attention = _attention_primary(planning_metadata)
    bearer_position: int | None = None
    if attention is None:
        # No usable attention information: the role/neutral fallback targets
        # the first declared character (deterministic declared order).
        bearer_position = dict_positions[0]
    else:
        target_name, target_kind = attention
        for position in dict_positions:
            if _normalize(members[position].get("name")) == target_name:
                bearer_position = position
                break
        if bearer_position is None:
            if target_kind == "object":
                warnings.append(f"attention_target_is_object:{target_name}")
            else:
                warnings.append(f"attention_target_absent:{target_name}")
            decision = EmotionDecision(
                scene_index=scene_index,
                skipped=True,
                reason="attention target is not a character in this scene",
                warnings=tuple(warnings),
            )
            return EmotionResult(tuple(members), decision)

    bearer = members[bearer_position]
    bearer_name = _normalize(bearer.get("name"))
    authored = bearer.get("emotion")
    if isinstance(authored, str) and authored.strip():
        decision = EmotionDecision(
            scene_index=scene_index,
            bearer=bearer_name,
            emotion=_normalize(authored),
            source="explicit",
            changed=False,
            skipped=True,
            reason="explicit emotion preserved",
        )
        return EmotionResult(tuple(members), decision)

    emotion, source = _resolve_emotion(planning_metadata, beat, scene_role, warnings)
    staged = dict(bearer)
    staged["emotion"] = emotion
    staged_members = list(members)
    staged_members[bearer_position] = staged
    decision = EmotionDecision(
        scene_index=scene_index,
        bearer=bearer_name,
        emotion=emotion,
        source=source,
        changed=True,
        skipped=False,
        reason=f"emotion staged from {source}",
        warnings=tuple(warnings),
    )
    return EmotionResult(tuple(staged_members), decision)
