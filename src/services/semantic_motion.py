"""Semantic Motion Lowerer (V1.3-C).

Translates a high-level SemanticMotionSpec (subject + semantic intent + timing)
into the EXISTING Motion primitives and EffectSpec effects already understood
by the renderer.

This is derived/staging metadata only -- it says HOW the attention identified
by V1.3-B (VisualFocus) can be expressed with primitives that already exist.
It never emits unsupported types, mutates any scene model, or invents elements.
Pure and deterministic: identical inputs always yield identical outputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.models.content_package import (
    SUPPORTED_EASINGS,
    SUPPORTED_MOTION_TARGETS,
    Motion,
)
from src.services.scene_composition import (
    SUPPORTED_EFFECTS,
    EffectSpec,
)

SUPPORTED_SEMANTIC_INTENTS = {
    "emphasize", "reveal", "reveal_decline", "emphasize_growth",
    "compare", "transform", "point_to", "isolate",
    "accumulate", "remove", "transition_attention",
}

DEFAULT_DURATION = 1.0
DEFAULT_EASING = "ease_out"
SCALE_EMPHASIS_TO = 1.2
SCALE_GROWTH_TO = 1.3
CAMERA_ZOOM_IN = 1.15

_INTENT_BASE_DURATION: dict[str, float] = {
    "emphasize": 0.8, "reveal": 1.0, "reveal_decline": 1.2,
    "emphasize_growth": 1.0, "compare": 1.0, "transform": 1.2,
    "point_to": 1.0, "isolate": 0.6, "accumulate": 1.0,
    "remove": 0.6, "transition_attention": 0.8,
}


@dataclass
class SemanticMotionSpec:
    """A high-level semantic motion intent to be lowered into primitives."""

    subject: str = ""
    intent: str = ""
    start_time: float = 0.0
    duration: float | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.subject = str(self.subject or "").strip()
        self.intent = str(self.intent or "").strip().lower()
        if self.start_time is None:
            self.start_time = 0.0
        self.start_time = max(0.0, float(self.start_time))
        if self.duration is not None:
            self.duration = max(0.0, float(self.duration))
        if not isinstance(self.parameters, dict):
            self.parameters = {}

    @property
    def effective_duration(self) -> float:
        if self.duration is not None and self.duration > 0:
            return self.duration
        return _INTENT_BASE_DURATION.get(self.intent, DEFAULT_DURATION)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoweredSemanticMotion:
    """The existing primitives produced by a semantic motion lowering."""

    motions: list[Motion] = field(default_factory=list)
    effects: list[EffectSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "motions": [motion.to_dict() for motion in self.motions],
            "effects": [effect.to_dict() for effect in self.effects],
        }

    def __iter__(self):
        yield self.motions
        yield self.effects


class SemanticMotionLowerer:
    """Lower semantic intent into validated, renderer-neutral primitives."""

    def lower(
        self,
        spec: SemanticMotionSpec,
        *,
        characters: list[Any] | None = None,
        objects: list[Any] | None = None,
        text: list[Any] | None = None,
        text_elements: list[Any] | None = None,
        visual_focus: Any | None = None,
        targets: dict[str, str] | None = None,
    ) -> LoweredSemanticMotion:
        if not isinstance(spec, SemanticMotionSpec):
            return LoweredSemanticMotion()
        known = self._known_targets(characters, objects, text if text is not None else text_elements, targets)
        options = dict(spec.parameters)
        subject = self._resolve(spec.subject, known, visual_focus)
        multi_subjects = self._resolve_many(options.get("subjects", spec.subject), known, visual_focus)
        if spec.intent not in SUPPORTED_SEMANTIC_INTENTS or (not subject and not multi_subjects):
            return LoweredSemanticMotion()
        requested_subjects = options.get("subjects")
        if spec.intent in {"compare", "accumulate"} and isinstance(requested_subjects, (list, tuple)):
            if len(multi_subjects) != len(requested_subjects):
                return LoweredSemanticMotion()

        duration = spec.effective_duration
        easing = self._easing(options.get("easing", DEFAULT_EASING))
        motions: list[Motion] = []
        effects: list[EffectSpec] = []

        def add_motion(motion_type: str, target: _Target, params: dict[str, Any]) -> None:
            motions.append(Motion(
                type=motion_type, target=target.kind, target_id=target.name, label=target.name,
                start_time=spec.start_time, duration=duration, easing=easing,
                parameters=dict(params),
            ))

        def add_effect(effect_type: str, target: _Target = subject) -> None:
            if (options.get("effect") is True or options.get("effect_type") == effect_type) and effect_type in SUPPORTED_EFFECTS:
                effects.append(EffectSpec(type=effect_type, target=target.name, start=spec.start_time, duration=duration))

        intent = spec.intent
        if intent in {"emphasize", "emphasize_growth"}:
            add_motion("scale", subject, {"from": 1.0, "to": SCALE_GROWTH_TO if intent == "emphasize_growth" else SCALE_EMPHASIS_TO})
            add_effect(options.get("effect_type", "highlight"))
        elif intent == "reveal":
            add_motion("fade", subject, {"from": 0.0, "to": 1.0})
            add_effect(options.get("effect_type", "highlight"))
            self._add_camera_zoom(add_motion, options)
        elif intent == "reveal_decline":
            add_motion("fade", subject, {"from": 0.0, "to": 1.0})
            add_motion("scale", subject, {"from": 1.0, "to": 0.8})
            self._add_camera_zoom(add_motion, options)
        elif intent == "compare":
            for index, target in enumerate(multi_subjects):
                add_motion("enter", target, {"direction": "left" if index == 0 else "right"})
        elif intent == "transform":
            old = self._resolve(options.get("from_subject", subject.name), known, visual_focus)
            new = self._resolve(options.get("to_subject", ""), known, visual_focus)
            if old and new and old.name != new.name:
                add_motion("exit", old, {"direction": "left"})
                add_motion("enter", new, {"direction": "right"})
        elif intent == "point_to":
            movement = options.get("from_to")
            if subject.kind == "character" and isinstance(movement, dict) and "from" in movement and "to" in movement:
                add_motion("move", subject, {"from": dict(movement["from"]), "to": dict(movement["to"])})
            elif subject.kind == "camera" and "from" in options and "to" in options:
                add_motion("pan", subject, {"from": dict(options["from"]), "to": dict(options["to"])})
        elif intent == "isolate":
            add_motion("scale", subject, {"from": 1.0, "to": SCALE_EMPHASIS_TO})
            add_effect(options.get("effect_type", "spotlight"))
            for target in self._resolve_many(self._focus_deemphasis(visual_focus), known, None):
                if target.name != subject.name:
                    add_motion("fade", target, {"from": 1.0, "to": 0.45})
        elif intent == "accumulate":
            for target in multi_subjects:
                add_motion("enter", target, {"direction": "bottom"})
        elif intent == "remove":
            add_motion("exit", subject, {"direction": options.get("direction", "fade")})
        elif intent == "transition_attention":
            if subject.kind == "camera" and "from" in options and "to" in options:
                add_motion("pan", subject, {"from": dict(options["from"]), "to": dict(options["to"])})
            else:
                add_motion("fade", subject, {"from": 0.0, "to": 1.0})
        return LoweredSemanticMotion(motions, effects)

    def lower_to_primitives(self, spec: SemanticMotionSpec, **kwargs: Any) -> tuple[list[Motion], list[EffectSpec]]:
        result = self.lower(spec, **kwargs)
        return result.motions, result.effects

    @staticmethod
    def _easing(value: Any) -> str:
        value = str(value).strip().lower()
        return value if value in SUPPORTED_EASINGS else DEFAULT_EASING

    @staticmethod
    def _field(value: Any, name: str, default: Any = "") -> Any:
        return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)

    def _known_targets(self, characters: list[Any] | None, objects: list[Any] | None, text: list[Any] | None, explicit: dict[str, str] | None) -> dict[str, "_Target"]:
        known: dict[str, _Target] = {"scene": _Target("scene", "scene"), "camera": _Target("camera", "camera")}
        for values, kind, field_name in ((characters, "character", "name"), (objects, "object", "name"), (text, "text", "text")):
            for value in values or []:
                name = str(self._field(value, field_name, "")).strip()
                if name:
                    known[name.lower()] = _Target(kind, name)
        for name, kind in (explicit or {}).items():
            if str(kind).lower() in SUPPORTED_MOTION_TARGETS:
                known[str(name).lower()] = _Target(str(kind).lower(), str(name))
        return known

    def _resolve(self, value: Any, known: dict[str, "_Target"], visual_focus: Any | None) -> "_Target | None":
        name = str(value or "").strip().lower()
        if not name and visual_focus is not None:
            name = str(getattr(visual_focus, "emphasis_target", "") or getattr(visual_focus, "primary", "")).strip().lower()
        return known.get(name)

    def _resolve_many(self, values: Any, known: dict[str, "_Target"], visual_focus: Any | None) -> list["_Target"]:
        if isinstance(values, str) and values:
            values = [part.strip() for part in values.replace(" versus ", " vs ").split(" vs ")]
        if not isinstance(values, (list, tuple)):
            values = []
        result: list[_Target] = []
        for value in values:
            target = self._resolve(value, known, visual_focus)
            if target and target not in result:
                result.append(target)
        return result

    @staticmethod
    def _focus_deemphasis(visual_focus: Any | None) -> list[str]:
        return list(getattr(visual_focus, "deemphasis_targets", []) or []) if visual_focus else []

    @staticmethod
    def _add_camera_zoom(add_motion: Any, options: dict[str, Any]) -> None:
        if options.get("camera_zoom") is True:
            add_motion("zoom", _Target("camera", "camera"), {"from": 1.0, "to": CAMERA_ZOOM_IN})


@dataclass(frozen=True)
class _Target:
    kind: str
    name: str
