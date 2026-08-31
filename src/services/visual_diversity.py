"""Visual Diversity Policy (V1.4-B).

Deterministic, pure, standalone service that detects repetitive visual
treatments across a sequence of scenes and produces safe variation
recommendations.

This is an advisory-only analysis layer that does not modify any inputs,
invoke the production pipeline, or make any external calls.

It builds on V1.4-A `VisualStoryPlanner` and reuses the existing
beat/focus primitives and vocabulary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.models.content_package import (
    SUPPORTED_MOTION_TYPES,
    SUPPORTED_TRANSITION_TYPES,
)
from src.services.visual_beat_engine import SUPPORTED_BEAT_TYPES
from src.pipeline.auto_publish_pipeline import ScenePlan, VisualScene
from src.services.visual_story_planner import VisualStoryPlan, SUPPORTED_TREATMENTS


# Re-export for test convenience
__all__ = [
    "VisualDiversityDecision",
    "VisualDiversityReport",
    "VisualDiversityPolicy",
    "SUPPORTED_TREATMENTS",
]


# ---------------------------------------------------------------------------
# Deterministic alternative vocabularies (derived from existing capabilities)
# ---------------------------------------------------------------------------

# Camera pattern alternatives - ordered by preference when avoiding repetition
_CAMERA_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "static": ("slow_zoom_in", "pan_right", "pan_left", "focus_on_character"),
    "slow_zoom_in": ("static", "pan_right", "pan_left", "slow_zoom_out"),
    "slow_zoom_out": ("static", "pan_right", "slow_zoom_in", "pan_up"),
    "pan_left": ("pan_right", "static", "slow_zoom_in", "pan_up"),
    "pan_right": ("pan_left", "static", "slow_zoom_in", "pan_down"),
    "pan_up": ("pan_down", "static", "slow_zoom_in", "pan_right"),
    "pan_down": ("pan_up", "static", "slow_zoom_in", "pan_left"),
    "zoom_then_pan": ("slow_zoom_in", "static", "pan_right", "slow_zoom_out"),
    "focus_on_character": ("static", "slow_zoom_in", "pan_right", "focus_on_object"),
    "focus_on_object": ("static", "slow_zoom_in", "pan_right", "focus_on_character"),
}

# Motion type alternatives - ordered by preference when avoiding repetition
_MOTION_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "fade": ("scale", "move", "enter", "zoom"),
    "scale": ("fade", "move", "zoom", "enter"),
    "move": ("fade", "scale", "pan", "enter"),
    "zoom": ("scale", "fade", "move", "pan"),
    "pan": ("move", "scale", "fade", "zoom"),
    "enter": ("fade", "scale", "move", "exit"),
    "exit": ("fade", "scale", "move", "enter"),
    "emphasize": ("scale", "fade", "move", "zoom"),
    "rotate": ("scale", "fade", "move", "zoom"),
}

# Treatment alternatives - ordered by preference when avoiding repetition
_TREATMENT_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "establish": ("explain", "problem_focus", "compare", "proof"),
    "problem_focus": ("explain", "compare", "establish", "proof"),
    "compare": ("explain", "problem_focus", "establish", "proof"),
    "explain": ("establish", "problem_focus", "compare", "proof"),
    "proof": ("solution_growth", "compare", "explain", "cta"),
    "solution_growth": ("proof", "explain", "cta", "establish"),
    "cta": ("solution_growth", "proof", "establish", "explain"),
}

# Focus pattern alternatives
_FOCUS_KIND_ALTERNATIVES: tuple[str, ...] = ("character", "object", "text", "scene")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _normalize(value: str) -> str:
    """Normalize a string for comparison (lowercase, strip)."""
    return str(value or "").strip().lower()


def _get_camera_pattern(scene: ScenePlan, story_decision: Any | None) -> str:
    """Extract camera pattern from scene (explicit) or story decision (derived)."""
    visual = scene.visual
    if visual is not None:
        camera_spec = getattr(visual, "camera_spec", None)
        if camera_spec and isinstance(camera_spec, dict):
            pattern = camera_spec.get("pattern")
            if pattern:
                normalized = _normalize(pattern)
                if normalized in SUPPORTED_CAMERA_PATTERNS:
                    return normalized
        legacy = getattr(visual, "camera_pattern", "")
        if legacy:
            normalized = _normalize(legacy)
            if normalized == "hold":
                return "static"
            if normalized in SUPPORTED_CAMERA_PATTERNS:
                return normalized
    if story_decision is not None:
        camera = getattr(story_decision, "camera_pattern", "")
        if camera:
            return _normalize(camera)
    return ""


def _get_motion_types(scene: ScenePlan, story_decision: Any | None) -> tuple[str, ...]:
    """Extract motion types from scene (explicit) or story decision (derived)."""
    motions: list[str] = []
    visual = scene.visual
    if visual is not None:
        for motion in getattr(visual, "motions", []) or []:
            mtype = getattr(motion, "type", "") or (motion.get("type") if isinstance(motion, dict) else "")
            if mtype:
                normalized = _normalize(mtype)
                if normalized in SUPPORTED_MOTION_TYPES and normalized not in motions:
                    motions.append(normalized)
    if motions:
        return tuple(motions)
    if story_decision is not None:
        motions = getattr(story_decision, "preferred_motion_types", ())
        if motions:
            return tuple(m for m in motions if m in SUPPORTED_MOTION_TYPES)
    return ()


def _get_treatment(scene: ScenePlan, story_decision: Any | None) -> str:
    """Extract treatment from story decision (derived) or infer from beat."""
    if story_decision is not None:
        treatment = getattr(story_decision, "treatment", "")
        if treatment:
            return _normalize(treatment)
    return ""


def _get_focus_pattern(scene: ScenePlan, story_decision: Any | None) -> str:
    """Extract focus target pattern from scene (explicit) or story decision (derived)."""
    visual = scene.visual
    if visual is not None:
        focus = getattr(visual, "primary_focus", "")
        if focus:
            return _normalize(focus)
        camera_spec = getattr(visual, "camera_spec", None)
        if camera_spec and isinstance(camera_spec, dict):
            focus = camera_spec.get("focus_target")
            if focus:
                return _normalize(focus)
    if story_decision is not None:
        focus = getattr(story_decision, "focus_target", "")
        if focus:
            return _normalize(focus)
    return ""


def _get_beat_type(scene: ScenePlan, story_decision: Any | None) -> str:
    """Extract beat type from scene role or story decision."""
    visual = scene.visual
    if visual is not None:
        role = getattr(visual, "scene_role", "")
        if role:
            role_to_beat = {
                "hook": "HOOK",
                "problem": "PROBLEM",
                "contrast": "CONTRAST",
                "explanation": "EXPLANATION",
                "example": "EXAMPLE",
                "solution": "SOLUTION",
                "cta": "CTA",
            }
            normalized = _normalize(role)
            if normalized in role_to_beat:
                return role_to_beat[normalized]
    if story_decision is not None:
        beat = getattr(story_decision, "beat_type", "")
        if beat:
            return beat
    return ""


def _is_explicit_camera(scene: ScenePlan) -> bool:
    """Check if scene has explicit camera intent."""
    visual = scene.visual
    if visual is None:
        return False
    camera_spec = getattr(visual, "camera_spec", None)
    if camera_spec and isinstance(camera_spec, dict):
        pattern = camera_spec.get("pattern")
        if pattern and _normalize(pattern) in SUPPORTED_CAMERA_PATTERNS:
            return True
    legacy = getattr(visual, "camera_pattern", "")
    if legacy:
        normalized = _normalize(legacy)
        if normalized == "hold" or normalized in SUPPORTED_CAMERA_PATTERNS:
            return True
    return False


def _is_explicit_motion(scene: ScenePlan) -> bool:
    """Check if scene has explicit motion intent."""
    visual = scene.visual
    if visual is None:
        return False
    motions = getattr(visual, "motions", []) or []
    for motion in motions:
        mtype = getattr(motion, "type", "") or (motion.get("type") if isinstance(motion, dict) else "")
        if mtype and _normalize(mtype) in SUPPORTED_MOTION_TYPES:
            return True
    return False


def _is_explicit_treatment(scene: ScenePlan) -> bool:
    """Check if scene has explicit treatment intent (always False for now)."""
    return False


def _is_explicit_focus(scene: ScenePlan) -> bool:
    """Check if scene has explicit focus intent."""
    visual = scene.visual
    if visual is None:
        return False
    if getattr(visual, "primary_focus", ""):
        return True
    camera_spec = getattr(visual, "camera_spec", None)
    if camera_spec and isinstance(camera_spec, dict):
        if camera_spec.get("focus_target"):
            return True
    return False


def _recommend_camera(
    current: str,
    previous: str,
    is_explicit: bool,
    seen_in_run: set[str],
) -> tuple[str, ...]:
    """Generate deterministic camera recommendations avoiding repetition."""
    if not current or current not in SUPPORTED_CAMERA_PATTERNS:
        return ()
    if is_explicit:
        return ()
    alternatives = _CAMERA_ALTERNATIVES.get(current, ())
    recommendations: list[str] = []
    for alt in alternatives:
        if alt != previous and alt not in seen_in_run and alt in SUPPORTED_CAMERA_PATTERNS:
            recommendations.append(alt)
    return tuple(recommendations[:3])


def _recommend_motion(
    current: tuple[str, ...],
    previous: tuple[str, ...],
    is_explicit: bool,
    seen_in_run: set[str],
) -> tuple[str, ...]:
    """Generate deterministic motion recommendations avoiding repetition."""
    if not current or is_explicit:
        return ()
    recommendations: list[str] = []
    for motion in current:
        alternatives = _MOTION_ALTERNATIVES.get(motion, ())
        for alt in alternatives:
            if alt not in previous and alt not in seen_in_run and alt in SUPPORTED_MOTION_TYPES:
                if alt not in recommendations:
                    recommendations.append(alt)
    return tuple(recommendations[:3])


def _recommend_treatment(
    current: str,
    previous: str,
    is_explicit: bool,
    seen_in_run: set[str],
) -> tuple[str, ...]:
    """Generate deterministic treatment recommendations avoiding repetition."""
    if not current or current not in SUPPORTED_TREATMENTS or is_explicit:
        return ()
    alternatives = _TREATMENT_ALTERNATIVES.get(current, ())
    recommendations: list[str] = []
    for alt in alternatives:
        if alt != previous and alt not in seen_in_run and alt in SUPPORTED_TREATMENTS:
            recommendations.append(alt)
    return tuple(recommendations[:3])


def _detect_focus_pattern_repetition(
    current: str,
    previous: str,
    run_count: int,
) -> tuple[bool, tuple[str, ...]]:
    """Detect focus pattern repetition and recommend alternatives."""
    if not current or not previous:
        return False, ()
    current_kind = _focus_kind(current)
    previous_kind = _focus_kind(previous)
    repeated = current_kind == previous_kind
    recommendations: tuple[str, ...] = ()
    if repeated and run_count >= 2:
        for kind in _FOCUS_KIND_ALTERNATIVES:
            if kind != current_kind:
                recommendations = (kind,)
                break
    return repeated, recommendations


def _focus_kind(focus: str) -> str:
    """Classify focus target into a kind for pattern detection."""
    normalized = _normalize(focus)
    if not normalized:
        return "scene"
    if "character" in normalized or "person" in normalized or "speaker" in normalized:
        return "character"
    if "text" in normalized or "title" in normalized or "label" in normalized:
        return "text"
    return "object"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VisualDiversityDecision:
    """Analysis and recommendations for a single scene's visual diversity."""

    scene_index: int
    repeated_with_previous: bool
    repeated_camera: bool
    repeated_motion: bool
    repeated_treatment: bool
    repeated_focus_pattern: bool
    warnings: tuple[str, ...]
    camera_recommendations: tuple[str, ...]
    motion_recommendations: tuple[str, ...]
    treatment_recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(frozen=True)
class VisualDiversityReport:
    """Immutable sequence-level visual diversity analysis."""

    decisions: tuple[VisualDiversityDecision, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "warnings": list(self.warnings),
        } 

class VisualDiversityPolicy:
    """Deterministic visual diversity analysis for scene sequences.

    Analyzes a sequence of scenes (and optionally a VisualStoryPlan) to detect
    repetitive visual treatments and provide safe, deterministic variation
    recommendations using only supported vocabulary values.

    This service is pure and read-only - it never mutates inputs.
    """

    def analyze(
        self,
        scenes: list[ScenePlan],
        *,
        story_plan: VisualStoryPlan | None = None,
    ) -> VisualDiversityReport:
        """Analyze a sequence of scenes for visual diversity.

        Args:
            scenes: List of ScenePlan objects to analyze.
            story_plan: Optional VisualStoryPlan from V1.4-A for derived values.

        Returns:
            VisualDiversityReport with per-scene decisions and sequence warnings.
        """
        if not scenes:
            return VisualDiversityReport(decisions=(), warnings=())

        story_decisions: dict[int, Any] = {}
        if story_plan is not None:
            for decision in story_plan.decisions:
                story_decisions[decision.scene_index] = decision

        decisions: list[VisualDiversityDecision] = []
        sequence_warnings: list[str] = []

        camera_run: dict[str, int] = {}
        motion_run: dict[tuple[str, ...], int] = {}
        treatment_run: dict[str, int] = {}
        focus_run: dict[str, int] = {}

        prev_camera = ""
        prev_motions: tuple[str, ...] = ()
        prev_treatment = ""
        prev_focus = ""

        for i, scene in enumerate(scenes):
            story_decision = story_decisions.get(i)

            camera = _get_camera_pattern(scene, story_decision)
            motions = _get_motion_types(scene, story_decision)
            treatment = _get_treatment(scene, story_decision)
            focus = _get_focus_pattern(scene, story_decision)

            explicit_camera = _is_explicit_camera(scene)
            explicit_motion = _is_explicit_motion(scene)
            explicit_treatment = _is_explicit_treatment(scene)

            repeated_camera = bool(camera and camera == prev_camera)
            repeated_motion = bool(motions and motions == prev_motions)
            repeated_treatment = bool(treatment and treatment == prev_treatment)
            repeated_focus, focus_recs = _detect_focus_pattern_repetition(
                focus, prev_focus, focus_run.get(_focus_kind(focus), 0)
            )
            repeated_with_previous = (
                repeated_camera or repeated_motion or repeated_treatment or repeated_focus
            )

            # Update run counters
            if camera:
                camera_run[camera] = camera_run.get(camera, 0) + 1
                for k in list(camera_run.keys()):
                    if k != camera:
                        camera_run[k] = 0
            else:
                camera_run.clear()

            if motions:
                motion_run[motions] = motion_run.get(motions, 0) + 1
                for k in list(motion_run.keys()):
                    if k != motions:
                        motion_run[k] = 0
            else:
                motion_run.clear()

            if treatment:
                treatment_run[treatment] = treatment_run.get(treatment, 0) + 1
                for k in list(treatment_run.keys()):
                    if k != treatment:
                        treatment_run[k] = 0
            else:
                treatment_run.clear()

            focus_kind = _focus_kind(focus)
            if focus:
                focus_run[focus_kind] = focus_run.get(focus_kind, 0) + 1
                for k in list(focus_run.keys()):
                    if k != focus_kind:
                        focus_run[k] = 0
            else:
                focus_run.clear()

            # Build warnings
            warnings: list[str] = []
            if repeated_camera:
                warnings.append(f"repeated_camera:{camera}")
            if repeated_motion:
                warnings.append(f"repeated_motion:{','.join(motions)}")
            if repeated_treatment:
                warnings.append(f"repeated_treatment:{treatment}")
            if repeated_focus:
                warnings.append(f"repeated_focus_pattern:{focus_kind}")

            # Short-run repetition warnings (3+ consecutive)
            if camera and camera_run.get(camera, 0) >= 3:
                warnings.append(f"camera_run:{camera}:{camera_run[camera]}")
            if motions and motion_run.get(motions, 0) >= 3:
                warnings.append(f"motion_run:{','.join(motions)}:{motion_run[motions]}")
            if treatment and treatment_run.get(treatment, 0) >= 3:
                warnings.append(f"treatment_run:{treatment}:{treatment_run[treatment]}")
            if focus and focus_run.get(focus_kind, 0) >= 3:
                warnings.append(f"focus_run:{focus_kind}:{focus_run[focus_kind]}")

            # Generate recommendations
            seen_cameras = {c for c, cnt in camera_run.items() if cnt > 0}
            seen_motions = {m for mtuple, cnt in motion_run.items() for m in mtuple if cnt > 0}
            seen_treatments = {t for t, cnt in treatment_run.items() if cnt > 0}

            camera_recs = _recommend_camera(camera, prev_camera, explicit_camera, seen_cameras)
            motion_recs = _recommend_motion(motions, prev_motions, explicit_motion, seen_motions)
            treatment_recs = _recommend_treatment(treatment, prev_treatment, explicit_treatment, seen_treatments)

            all_treatment_recs = list(treatment_recs)
            all_treatment_recs.extend(focus_recs)

            decision = VisualDiversityDecision(
                scene_index=i,
                repeated_with_previous=repeated_with_previous,
                repeated_camera=repeated_camera,
                repeated_motion=repeated_motion,
                repeated_treatment=repeated_treatment,
                repeated_focus_pattern=repeated_focus,
                warnings=tuple(warnings),
                camera_recommendations=camera_recs,
                motion_recommendations=motion_recs,
                treatment_recommendations=tuple(all_treatment_recs),
            )
            decisions.append(decision)

            prev_camera = camera
            prev_motions = motions
            prev_treatment = treatment
            prev_focus = focus

        # Sequence-level warnings
        if len(scenes) >= 3:
            cameras_used = {
                _get_camera_pattern(scenes[d.scene_index], story_decisions.get(d.scene_index))
                for d in decisions
                if _get_camera_pattern(scenes[d.scene_index], story_decisions.get(d.scene_index))
            }
            if len(cameras_used) <= 1:
                sequence_warnings.append("low_camera_diversity")

            treatments_used = {
                _get_treatment(scenes[d.scene_index], story_decisions.get(d.scene_index))
                for d in decisions
                if _get_treatment(scenes[d.scene_index], story_decisions.get(d.scene_index))
            }
            if len(treatments_used) <= 1:
                sequence_warnings.append("low_treatment_diversity")

        return VisualDiversityReport(
            decisions=tuple(decisions),
            warnings=tuple(sequence_warnings),
        )
