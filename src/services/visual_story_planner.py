"""Sequence-level visual treatment planning for V1.4-A.

This service is advisory only. It reads existing scene/beat/focus objects and
returns immutable decisions; it does not alter scenes, create render
primitives, or call the production pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.models.content_package import SUPPORTED_MOTION_TYPES, SUPPORTED_TRANSITION_TYPES
from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.services.visual_beat_engine import SCENE_ROLE_BEATS, SUPPORTED_BEAT_TYPES

SUPPORTED_TREATMENTS = {
    "establish",
    "problem_focus",
    "compare",
    "explain",
    "proof",
    "solution_growth",
    "cta",
}

_BEAT_TO_TREATMENT = {
    "HOOK": "establish",
    "PROBLEM": "problem_focus",
    "CONTRAST": "compare",
    "EXPLANATION": "explain",
    "EXAMPLE": "proof",
    "SOLUTION": "solution_growth",
    "CTA": "cta",
}

_TREATMENT_MOTIONS: dict[str, tuple[str, ...]] = {
    "establish": ("enter", "zoom"),
    "problem_focus": ("fade", "scale"),
    "compare": ("enter", "move", "pan"),
    "explain": ("fade", "scale"),
    "proof": ("pan", "scale"),
    "solution_growth": ("scale", "zoom"),
    "cta": ("fade", "scale"),
}

_TREATMENT_ALTERNATIVE_MOTIONS: dict[str, tuple[str, ...]] = {
    "establish": ("fade", "zoom"),
    "problem_focus": ("scale", "zoom"),
    "compare": ("move", "pan"),
    "explain": ("fade", "zoom"),
    "proof": ("pan", "zoom"),
    "solution_growth": ("scale", "fade"),
    "cta": ("fade", "exit"),
}

_TREATMENT_CAMERAS: dict[str, tuple[str, ...]] = {
    "establish": ("slow_zoom_in", "static", "pan_right"),
    "problem_focus": ("focus_on_character", "slow_zoom_in", "static"),
    "compare": ("pan_left", "pan_right", "static"),
    "explain": ("static", "slow_zoom_in", "pan_right"),
    "proof": ("pan_right", "slow_zoom_in", "static"),
    "solution_growth": ("slow_zoom_in", "zoom_then_pan", "static"),
    "cta": ("slow_zoom_out", "static", "pan_up"),
}

_TREATMENT_ALTERNATIVE_CAMERAS: dict[str, tuple[str, ...]] = {
    "establish": ("static", "pan_right"),
    "problem_focus": ("slow_zoom_in", "static"),
    "compare": ("pan_right", "pan_left", "static"),
    "explain": ("slow_zoom_in", "pan_right", "static"),
    "proof": ("slow_zoom_in", "static", "pan_left"),
    "solution_growth": ("zoom_then_pan", "static", "slow_zoom_in"),
    "cta": ("static", "pan_up", "slow_zoom_out"),
}


@dataclass(frozen=True)
class VisualStoryDecision:
    """Advisory visual treatment for one scene in a sequence."""

    scene_index: int
    beat_type: str
    focus_target: str
    treatment: str
    camera_pattern: str
    preferred_motion_types: tuple[str, ...]
    transition_type: str | None
    repeated_with_previous: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualStoryPlan:
    """Immutable sequence-level visual planning report."""

    decisions: tuple[VisualStoryDecision, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "warnings": list(self.warnings),
        }


class VisualStoryPlanner:
    """Plan relative visual treatments without changing render inputs."""

    def plan(
        self,
        scenes: list[Any],
        *,
        beats: list[Any] | None = None,
        focuses: list[Any] | None = None,
    ) -> VisualStoryPlan:
        decisions: list[VisualStoryDecision] = []
        plan_warnings: list[str] = []
        previous_treatment = ""
        previous_camera = ""
        previous_motions: tuple[str, ...] = ()
        previous_focus = ""

        for index, scene in enumerate(scenes or []):
            beat_type, beat_warning = self._beat_type(scene, beats, index)
            treatment = _BEAT_TO_TREATMENT[beat_type]
            focus_target, focus_warning = self._focus_target(scene, focuses, index)
            explicit_camera = self._explicit_camera(scene)
            camera_pattern = explicit_camera or self._choose_camera(
                treatment, previous_camera, index == 0
            )
            explicit_motions = self._explicit_motion_types(scene)
            motion_types = explicit_motions or self._choose_motions(
                treatment, previous_motions, index == 0
            )
            explicit_transition = self._explicit_transition(scene)
            transition_type = explicit_transition or self._recommend_transition(
                beat_type,
                self._beat_type_value(beats, index - 1),
                is_final=index == len(scenes or []) - 1,
            )

            warnings: list[str] = []
            if beat_warning:
                warnings.append(beat_warning)
            if focus_warning:
                warnings.append(focus_warning)
            if index > 0 and treatment == previous_treatment:
                warnings.append("repeated treatment with previous scene")
            if index > 0 and camera_pattern == previous_camera:
                warnings.append("repeated camera pattern with previous scene")
            elif index > 0 and not explicit_camera and self._base_camera(treatment) == previous_camera:
                warnings.append("repeated camera pattern with previous scene")
            if index > 0 and motion_types == previous_motions:
                warnings.append("repeated motion treatment with previous scene")
            if index > 0 and focus_target and focus_target == previous_focus:
                warnings.append("same focus target as previous scene")
            elif index > 0 and focus_target and previous_focus and focus_target != previous_focus:
                warnings.append("focus changed from previous scene")
            if beat_type == "CONTRAST" and index > 0 and camera_pattern == previous_camera:
                warnings.append("contrast scene repeats previous spatial treatment")
            if beat_type == "CTA" and index > 0 and treatment == previous_treatment:
                warnings.append("CTA is not visually distinct from previous scene")
            if explicit_camera and camera_pattern != self._normalize_camera(explicit_camera):
                warnings.append("explicit camera pattern was normalized to supported vocabulary")
            if explicit_transition:
                transition_type = explicit_transition

            decision = VisualStoryDecision(
                scene_index=index,
                beat_type=beat_type,
                focus_target=focus_target,
                treatment=treatment,
                camera_pattern=camera_pattern,
                preferred_motion_types=motion_types,
                transition_type=transition_type,
                repeated_with_previous=bool(index > 0 and (
                    treatment == previous_treatment
                    or camera_pattern == previous_camera
                    or motion_types == previous_motions
                    or (focus_target and focus_target == previous_focus)
                )),
                warnings=tuple(dict.fromkeys(warnings)),
            )
            decisions.append(decision)
            plan_warnings.extend(decision.warnings)
            previous_treatment = treatment
            previous_camera = camera_pattern
            previous_motions = motion_types
            previous_focus = focus_target

        return VisualStoryPlan(tuple(decisions), tuple(dict.fromkeys(plan_warnings)))

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @classmethod
    def _visual(cls, scene: Any) -> Any:
        return cls._field(scene, "visual") or scene

    @classmethod
    def _beat_type(cls, scene: Any, beats: list[Any] | None, index: int) -> tuple[str, str]:
        value = cls._beat_type_value(beats, index)
        if value in SUPPORTED_BEAT_TYPES:
            return value, ""
        visual = cls._visual(scene)
        role = str(cls._field(visual, "scene_role", "") or "").strip().lower()
        role_value = SCENE_ROLE_BEATS.get(role, "")
        if role_value:
            return role_value, "missing or invalid beat; using scene role fallback"
        return "EXPLANATION", "missing or invalid beat; using EXPLANATION fallback"

    @classmethod
    def _beat_type_value(cls, beats: list[Any] | None, index: int) -> str:
        if beats is None or index < 0 or index >= len(beats):
            return ""
        beat = beats[index]
        value = beat.get("type") if isinstance(beat, dict) else getattr(beat, "type", "")
        return str(value or "").strip().upper()

    @classmethod
    def _focus_target(cls, scene: Any, focuses: list[Any] | None, index: int) -> tuple[str, str]:
        visual = cls._visual(scene)
        explicit = str(cls._field(visual, "primary_focus", "") or "").strip()
        if explicit and explicit.lower() != "scene":
            return explicit, ""
        camera_spec = cls._field(visual, "camera_spec", {}) or {}
        camera_focus = cls._field(camera_spec, "focus_target", "")
        if camera_focus:
            return str(camera_focus).strip(), ""
        if focuses is not None and index < len(focuses):
            focus = focuses[index]
            primary = focus.get("primary") if isinstance(focus, dict) else getattr(focus, "primary", "")
            return str(primary or "").strip(), ""
        return "", "missing focus; no target invented"

    @classmethod
    def _explicit_camera(cls, scene: Any) -> str:
        visual = cls._visual(scene)
        camera_spec = cls._field(visual, "camera_spec", {}) or {}
        pattern = str(cls._field(camera_spec, "pattern", "") or "").strip().lower()
        if pattern and pattern in SUPPORTED_CAMERA_PATTERNS:
            return pattern
        legacy = str(cls._field(visual, "camera_pattern", "") or "").strip().lower()
        return cls._normalize_camera(legacy) if legacy and legacy != "hold" else ""

    @staticmethod
    def _normalize_camera(value: str) -> str:
        return {
            "hold": "static",
            "zoom": "slow_zoom_in",
            "zoom_in": "slow_zoom_in",
            "zoom_out": "slow_zoom_out",
            "pan": "pan_right",
            "tracking": "pan_right",
            "follow": "pan_right",
        }.get(value, value if value in SUPPORTED_CAMERA_PATTERNS else "")

    @classmethod
    def _explicit_motion_types(cls, scene: Any) -> tuple[str, ...]:
        motions = cls._field(cls._visual(scene), "motions", []) or []
        result: list[str] = []
        for motion in motions:
            value = str(cls._field(motion, "type", "") or "").strip().lower()
            if value in SUPPORTED_MOTION_TYPES and value not in result:
                result.append(value)
        return tuple(result)

    @classmethod
    def _explicit_transition(cls, scene: Any) -> str | None:
        transition = cls._field(cls._visual(scene), "transition")
        value = str(cls._field(transition, "type", "") or "").strip().lower()
        return value if value in SUPPORTED_TRANSITION_TYPES else None

    @staticmethod
    def _base_camera(treatment: str) -> str:
        return _TREATMENT_CAMERAS[treatment][0]

    @staticmethod
    def _choose_camera(treatment: str, previous: str, first: bool) -> str:
        candidates = _TREATMENT_CAMERAS[treatment]
        if first:
            return candidates[0]
        for candidate in candidates:
            if candidate != previous:
                return candidate
        for candidate in _TREATMENT_ALTERNATIVE_CAMERAS[treatment]:
            if candidate != previous:
                return candidate
        return candidates[0]

    @staticmethod
    def _choose_motions(treatment: str, previous: tuple[str, ...], first: bool) -> tuple[str, ...]:
        candidates = _TREATMENT_MOTIONS[treatment]
        if first or candidates != previous:
            return candidates
        alternative = _TREATMENT_ALTERNATIVE_MOTIONS[treatment]
        return alternative if alternative != previous else candidates

    @staticmethod
    def _recommend_transition(current: str, previous: str, is_final: bool) -> str | None:
        if is_final:
            return None
        if current == "CONTRAST" or previous == "CONTRAST":
            return "slide_left"
        if previous == "PROBLEM" and current == "SOLUTION":
            return "slide_up"
        if previous == "EXPLANATION" and current in {"EXAMPLE", "SOLUTION"}:
            return "crossfade"
        if previous == "HOOK" and current == "EXPLANATION":
            return "crossfade"
        return "cut"
