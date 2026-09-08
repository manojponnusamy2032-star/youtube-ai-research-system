"""Deterministic scene-aware motion variation (V1.6-C).

This layer selects existing ``Motion`` primitives for scenes that have no
explicit motion for the selected target. It changes only derived staging
metadata and is deliberately independent of the renderer implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.models.content_package import Motion, SUPPORTED_MOTION_TYPES


VISUAL_MOTION_VARIATION_ENABLED = False

SUPPORTED_MOTION_INTENTS = frozenset(
    {"idle", "talk", "explain", "point", "emphasize", "react", "walk", "approach", "interact", "gesture", "reveal", "transition", "focus"}
)

ROLE_INTENTS: dict[str, tuple[str, ...]] = {
    "hook": ("react", "emphasize"),
    "problem": ("react", "emphasize"),
    "explanation": ("explain", "point", "emphasize"),
    "object_interaction": ("interact", "point", "emphasize"),
    "character_action": ("walk", "gesture", "emphasize"),
    "transformation": ("reveal", "emphasize", "approach"),
    "comparison": ("emphasize", "gesture"),
    "payoff": ("gesture", "emphasize"),
    "solution": ("explain", "emphasize"),
    "cta": ("gesture", "emphasize"),
}

_INTENT_TYPES: dict[str, tuple[str, ...]] = {
    "react": ("emphasize",),
    "emphasize": ("scale",),
    "explain": ("emphasize",),
    "point": ("emphasize",),
    "interact": ("scale",),
    "gesture": ("emphasize",),
    "reveal": ("scale",),
    "approach": ("move",),
    "walk": ("move",),
    "transition": ("fade",),
    "focus": ("scale",),
}


@dataclass(frozen=True)
class MotionVariationDecision:
    scene_index: int
    scene_role: str = "general"
    intent: str = "idle"
    target: str | None = None
    target_id: str | None = None
    motion_type: str | None = None
    changed: bool = False
    skipped: bool = False
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MotionVariationResult:
    motions: tuple[Motion, ...] = ()
    decision: MotionVariationDecision = field(
        default_factory=lambda: MotionVariationDecision(scene_index=0)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "motions": [motion.to_dict() for motion in self.motions],
            "decision": self.decision.to_dict(),
        }


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _names(values: list[Any] | None) -> list[str]:
    return [str(_field(value, "name", "")).strip() for value in values or [] if str(_field(value, "name", "")).strip()]


def _choose_intent(scene_role: str, scene_index: int, character_count: int, object_count: int) -> str:
    options = ROLE_INTENTS.get(scene_role, ("emphasize",))
    if not character_count and not object_count:
        return "idle"
    return options[max(int(scene_index), 0) % len(options)]


def _target_for_intent(
    intent: str,
    characters: list[Any],
    objects: list[Any],
    primary_focus: str,
    focus_target: str | None,
) -> tuple[str, str] | None:
    char_names = _names(characters)
    object_names = _names(objects)
    preferred = str(focus_target or "").strip()
    if preferred in char_names or preferred in object_names:
        return ("character" if preferred in char_names else "object", preferred)
    if primary_focus == "object" and object_names:
        return "object", object_names[0]
    if char_names:
        return "character", char_names[0]
    if object_names:
        return "object", object_names[0]
    return None


def _build_motion(
    intent: str,
    target: tuple[str, str],
    scene_index: int,
    duration: float,
) -> Motion | None:
    target_kind, target_id = target
    motion_types = _INTENT_TYPES.get(intent, ())
    motion_type = motion_types[scene_index % len(motion_types)] if motion_types else ""
    if motion_type not in SUPPORTED_MOTION_TYPES:
        return None
    start = min(max(0.15, duration * 0.18), max(0.15, duration - 0.2))
    motion_duration = min(max(0.35, duration * 0.42), max(0.35, duration - start))
    params: dict[str, Any]
    if motion_type == "scale":
        params = {"from": 1.0, "to": 1.08 if scene_index % 2 == 0 else 1.12}
    elif motion_type == "move":
        params = {"from": {"x": 0.30, "y": 0.75}, "to": {"x": 0.42, "y": 0.75}}
    elif motion_type == "fade":
        params = {"from": 0.65, "to": 1.0}
    else:
        params = {"strength": 0.08 if scene_index % 2 == 0 else 0.12}
        motion_type = "emphasize"
    return Motion(
        type=motion_type,
        target=target_kind,
        target_id=target_id,
        label=f"v1.6-c:{intent}",
        start_time=start,
        duration=motion_duration,
        easing="ease_in_out",
        parameters=params,
    )


def apply_motion_variation(
    characters: list[Any] | None,
    objects: list[Any] | None,
    explicit_motions: list[Motion] | None = None,
    *,
    scene_index: int = 0,
    scene_role: str = "general",
    primary_focus: str = "scene",
    focus_target: str | None = None,
    duration: float = 1.0,
    explicit_character_action: str = "idle",
) -> MotionVariationResult:
    """Append one safe, deterministic motion when the scene permits it."""
    role = str(scene_role or "general").strip().lower() or "general"
    existing = tuple(motion for motion in (explicit_motions or []) if isinstance(motion, Motion))
    if not VISUAL_MOTION_VARIATION_ENABLED:
        return MotionVariationResult(existing, MotionVariationDecision(int(scene_index), role, skipped=True, reason="motion variation disabled (flag OFF)"))

    if str(explicit_character_action or "idle").strip().lower() not in {"", "idle"}:
        return MotionVariationResult(existing, MotionVariationDecision(int(scene_index), role, skipped=True, reason="explicit character action preserved"))

    target = _target_for_intent(_choose_intent(role, scene_index, len(characters or []), len(objects or [])), characters or [], objects or [], str(primary_focus or "scene").lower(), focus_target)
    intent = _choose_intent(role, scene_index, len(characters or []), len(objects or []))
    if target is None or intent not in SUPPORTED_MOTION_INTENTS:
        return MotionVariationResult(existing, MotionVariationDecision(int(scene_index), role, intent=intent, skipped=True, reason="no valid motion target"))
    if any(motion.target == target[0] and motion.target_id == target[1] for motion in existing):
        return MotionVariationResult(existing, MotionVariationDecision(int(scene_index), role, intent=intent, target=target[0], target_id=target[1], skipped=True, reason="explicit motion for target preserved"))

    motion = _build_motion(intent, target, int(scene_index), max(0.5, float(duration)))
    if motion is None:
        return MotionVariationResult(existing, MotionVariationDecision(int(scene_index), role, intent=intent, target=target[0], target_id=target[1], skipped=True, warnings=("unsupported_motion_fallback",), reason="no supported motion primitive"))
    decision = MotionVariationDecision(int(scene_index), role, intent=intent, target=target[0], target_id=target[1], motion_type=motion.type, changed=True, reason="assigned deterministic scene-aware motion")
    return MotionVariationResult(existing + (motion,), decision)