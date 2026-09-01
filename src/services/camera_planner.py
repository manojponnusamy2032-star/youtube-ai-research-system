"""Camera Continuity Planner (V1.4-D).

Deterministic, pure, standalone planning service that makes camera behavior
work as a sequence, rather than selecting camera treatment independently
for every scene.

This is an advisory-only planning layer that does not modify any inputs,
invoke the production pipeline, or make any external calls.

It builds on V1.4-A `VisualStoryPlanner`, V1.4-B `VisualDiversityPolicy`,
and V1.4-C `CompositionPlanner` and reuses the existing camera vocabulary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.pipeline.auto_publish_pipeline import ScenePlan
from src.services.visual_story_planner import VisualStoryPlan
from src.services.visual_diversity import VisualDiversityReport
from src.services.composition_planner import CompositionPlan


# Re-export for test convenience
__all__ = [
    "CameraDecision",
    "CameraPlan",
    "CameraPlanner",
    "SUPPORTED_CAMERA_PATTERNS",
    "SUPPORTED_CONTINUITY_STATES",
]


# ---------------------------------------------------------------------------
# Vocabulary constants
# ---------------------------------------------------------------------------

SUPPORTED_CONTINUITY_STATES = {
    "established",
    "continued",
    "changed",
    "reversed",
    "held",
    "fallback",
}

# Safe scene-level focus target (a category, not an invented identifier).
_SCENE_TARGET = "scene"


# ---------------------------------------------------------------------------
# Treatment-to-camera mappings (from V1.4-A conventions)
# ---------------------------------------------------------------------------

_TREATMENT_CAMERAS: dict[str, tuple[str, ...]] = {
    "establish": ("static", "slow_zoom_in", "pan_right"),
    "problem_focus": ("focus_on_character", "slow_zoom_in", "static"),
    "compare": ("static", "pan_left", "pan_right"),
    "explain": ("static", "slow_zoom_in", "pan_right"),
    "proof": ("focus_on_object", "slow_zoom_in", "static"),
    "solution_growth": ("slow_zoom_in", "zoom_then_pan", "static"),
    "cta": ("static", "slow_zoom_out", "focus_on_character"),
}

_TREATMENT_ALTERNATIVE_CAMERAS: dict[str, tuple[str, ...]] = {
    "establish": ("slow_zoom_in", "pan_right", "static"),
    "problem_focus": ("slow_zoom_in", "static", "focus_on_character"),
    "compare": ("pan_right", "pan_left", "static"),
    "explain": ("pan_right", "static", "slow_zoom_in"),
    "proof": ("slow_zoom_in", "static", "focus_on_object"),
    "solution_growth": ("zoom_then_pan", "static", "slow_zoom_in"),
    "cta": ("focus_on_character", "static", "slow_zoom_out"),
}


# ---------------------------------------------------------------------------
# Composition-to-camera preferences
# ---------------------------------------------------------------------------

_COMPOSITION_CAMERA: dict[str, tuple[str, ...]] = {
    "single_subject": ("focus_on_character", "slow_zoom_in", "static"),
    "subject_support": ("static", "slow_zoom_in", "pan_right"),
    "comparison": ("static", "pan_left", "pan_right"),
    "text_led": ("static", "slow_zoom_out"),
    "object_led": ("focus_on_object", "slow_zoom_in", "static"),
    "problem_focus": ("focus_on_character", "slow_zoom_in", "static"),
    "solution_result": ("slow_zoom_in", "zoom_then_pan", "static"),
}


# ---------------------------------------------------------------------------
# Pan direction grouping for continuity
# ---------------------------------------------------------------------------

_HORIZONTAL_PANS = {"pan_left", "pan_right"}
_VERTICAL_PANS = {"pan_up", "pan_down"}
_ZOOM_PATTERNS = {"slow_zoom_in", "slow_zoom_out"}
_FOCUS_PATTERNS = {"focus_on_character", "focus_on_object"}


def _normalize(value: str) -> str:
    """Normalize a string for comparison (lowercase, strip)."""
    return str(value or "").strip().lower()


def _get_explicit_camera(scene: ScenePlan) -> str:
    """Extract explicit camera pattern from scene.

    Only a real, directed camera intent counts as explicit. The default
    VisualScene camera value "hold" (meaning "no camera direction set")
    is treated as no-intent so the planner can derive a better pattern.
    """
    visual = scene.visual
    if visual is None:
        return ""

    # Check camera_spec first
    camera_spec = getattr(visual, "camera_spec", None)
    if camera_spec and isinstance(camera_spec, dict):
        pattern = camera_spec.get("pattern")
        if pattern:
            normalized = _normalize(pattern)
            if normalized in SUPPORTED_CAMERA_PATTERNS:
                return normalized

    # Check legacy camera_pattern
    legacy = getattr(visual, "camera_pattern", "")
    if legacy:
        normalized = _normalize(legacy)
        if normalized == "hold":
            # Default/no-intent value - not an explicit direction.
            return ""
        if normalized in SUPPORTED_CAMERA_PATTERNS:
            return normalized
    return ""


def _get_explicit_focus_target(scene: ScenePlan) -> str | None:
    """Extract explicit focus target from scene.

    The default primary_focus value "scene" is treated as no-intent so the
    planner can derive a character/object target only when one really exists.
    """
    visual = scene.visual
    if visual is None:
        return None

    # Check camera_spec focus_target
    camera_spec = getattr(visual, "camera_spec", None)
    if camera_spec and isinstance(camera_spec, dict):
        target = camera_spec.get("focus_target")
        if target:
            return _normalize(target)

    # Check primary_focus (ignoring the default "scene" value)
    focus = getattr(visual, "primary_focus", "")
    if focus and _normalize(focus) != "scene":
        return _normalize(focus)
    return None


def _has_characters(scene: ScenePlan) -> bool:
    """Check if scene has characters."""
    visual = scene.visual
    if visual is None:
        return False
    return len(getattr(visual, "characters", []) or []) > 0


def _has_objects(scene: ScenePlan) -> bool:
    """Check if scene has objects."""
    visual = scene.visual
    if visual is None:
        return False
    return len(getattr(visual, "objects", []) or []) > 0


def _get_treatment(scene: ScenePlan, story_decision: Any | None) -> str:
    """Extract treatment from story decision."""
    if story_decision is not None:
        treatment = getattr(story_decision, "treatment", "")
        if treatment:
            return _normalize(treatment)
    return ""


def _get_composition_type(composition_decision: Any | None) -> str:
    """Extract composition type from V1.4-C decision."""
    if composition_decision is not None:
        comp_type = getattr(composition_decision, "composition_type", "")
        if comp_type:
            return _normalize(comp_type)
    return ""


def _is_repeated_in_diversity(diversity_decision: Any | None) -> bool:
    """Check if V1.4-B reports camera repetition."""
    if diversity_decision is None:
        return False
    return getattr(diversity_decision, "repeated_camera", False)


def _get_diversity_camera_recs(diversity_decision: Any | None) -> tuple[str, ...]:
    """Get camera recommendations from V1.4-B."""
    if diversity_decision is None:
        return ()
    recs = getattr(diversity_decision, "camera_recommendations", ())
    return tuple(r for r in recs if r in SUPPORTED_CAMERA_PATTERNS)


def _get_pan_direction(pattern: str) -> str:
    """Get the direction category of a pan pattern."""
    if pattern in _HORIZONTAL_PANS:
        return "horizontal"
    if pattern in _VERTICAL_PANS:
        return "vertical"
    if pattern in _ZOOM_PATTERNS:
        return "zoom"
    if pattern in _FOCUS_PATTERNS:
        return "focus"
    return "static"


def _is_pan_pattern(pattern: str) -> bool:
    """Check if pattern is a pan movement."""
    return pattern in _HORIZONTAL_PANS or pattern in _VERTICAL_PANS


def _choose_camera_pattern(
    treatment: str,
    composition_type: str,
    explicit_camera: str,
    previous_pattern: str,
    run_count: int,
    has_characters: bool,
    has_objects: bool,
    diversity_repeated: bool,
    diversity_recs: tuple[str, ...],
) -> str:
    """Choose camera pattern based on context."""

    # Explicit camera takes precedence
    if explicit_camera:
        return explicit_camera

    # Build candidate list from treatment
    candidates: tuple[str, ...] = ()
    if treatment and treatment in _TREATMENT_CAMERAS:
        candidates = _TREATMENT_CAMERAS[treatment]
    elif composition_type and composition_type in _COMPOSITION_CAMERA:
        candidates = _COMPOSITION_CAMERA[composition_type]

    # If repetition detected, use alternatives
    if (diversity_repeated or run_count >= 2) and treatment and treatment in _TREATMENT_ALTERNATIVE_CAMERAS:
        candidates = _TREATMENT_ALTERNATIVE_CAMERAS[treatment]

    # If diversity provided recommendations, use them
    if diversity_recs:
        # Filter recommendations based on target availability
        for rec in diversity_recs:
            if rec == "focus_on_character" and not has_characters:
                continue
            if rec == "focus_on_object" and not has_objects:
                continue
            if rec != previous_pattern or run_count < 2:
                return rec

    # Select from candidates
    if candidates:
        # For repetition, try to pick different pattern
        if run_count >= 2 or diversity_repeated:
            for candidate in candidates:
                if candidate != previous_pattern:
                    # Validate target availability
                    if candidate == "focus_on_character" and not has_characters:
                        continue
                    if candidate == "focus_on_object" and not has_objects:
                        continue
                    return candidate

        # Default: first valid candidate
        for candidate in candidates:
            if candidate == "focus_on_character" and not has_characters:
                continue
            if candidate == "focus_on_object" and not has_objects:
                continue
            return candidate

    # Safe fallback
    if has_characters:
        return "focus_on_character"
    if has_objects:
        return "focus_on_object"
    return "static"


def _determine_focus_target(
    pattern: str,
    explicit_target: str | None,
    scene: ScenePlan,
) -> str | None:
    """Determine focus target for camera pattern."""
    # Explicit target takes precedence
    if explicit_target:
        return explicit_target

    # For focus patterns, find a target
    if pattern == "focus_on_character":
        visual = scene.visual
        if visual:
            characters = getattr(visual, "characters", []) or []
            if characters:
                first = characters[0]
                if isinstance(first, dict):
                    return first.get("name", "character")
                return getattr(first, "name", "character")
        return None  # No character target available

    if pattern == "focus_on_object":
        visual = scene.visual
        if visual:
            objects = getattr(visual, "objects", []) or []
            if objects:
                first = objects[0]
                if isinstance(first, dict):
                    return first.get("name", "object")
                return getattr(first, "name", "object")
        return None  # No object target available

    return None


def _determine_continuity_state(
    current_pattern: str,
    previous_pattern: str,
) -> str:
    """Determine continuity state between scenes."""
    if not previous_pattern:
        return "established"

    if current_pattern == previous_pattern:
        return "held"

    # Check for reversal
    if (_get_pan_direction(current_pattern) == _get_pan_direction(previous_pattern)
        and _is_pan_pattern(current_pattern) and _is_pan_pattern(previous_pattern)):
        return "reversed"

    return "changed"


# ---------------------------------------------------------------------------
# Scene-level target resolution (camera focus targets)
# ---------------------------------------------------------------------------

_CAMERA_TARGET_KINDS = ("character", "object")


def _ordered_targets(scene: ScenePlan) -> list[tuple[str, str]]:
    """Return ``(name, kind)`` for camera-focusable targets in scene order.

    Only *existing* scene elements are collected - characters first, then
    objects - matching the camera focus vocabulary
    (``focus_on_character`` / ``focus_on_object``). Names are returned exactly
    as they appear in the scene; nothing is invented.
    """
    ordered: list[tuple[str, str]] = []
    visual = scene.visual
    if visual is None:
        return ordered
    for kind in _CAMERA_TARGET_KINDS:
        for elem in getattr(visual, f"{kind}s", []) or []:
            if isinstance(elem, dict):
                name = str(elem.get("name") or "").strip()
            else:
                name = str(getattr(elem, "name", "") or "").strip()
            if name:
                ordered.append((name, kind))
    return ordered


def _first_matching_name(
    ordered: list[tuple[str, str]],
    query: str | None,
) -> str | None:
    """Return the existing element name matching ``query``, or ``None``.

    Matching mirrors ``VisualFocusResolver`` (exact normalized match first,
    then a substring match in either direction). A query that names nothing
    real returns ``None`` - a target is never invented.
    """
    q = _normalize(query or "")
    if not q:
        return None
    for name, _kind in ordered:
        if _normalize(name) == q:
            return name
    for name, _kind in ordered:
        h = _normalize(name)
        if h and (q in h or h in q):
            return name
    return None


def _resolve_scene(scene: ScenePlan, explicit_target: str | None = None) -> str:
    """Resolve a valid scene-level camera focus target.

    Priority:
      1. Existing explicit/valid primary focus target when it represents a
         real scene target (an existing character/object, or the scene-level
         target itself).
      2. Character target when characters exist.
      3. Object target when objects exist.
      4. ``"scene"`` as the final safe fallback.

    An explicit target that names no real scene element is skipped - never
    invented and never returned.
    """
    ordered = _ordered_targets(scene)

    # 1. Explicit focus target, only when it names a real scene target.
    if explicit_target:
        normalized = _normalize(explicit_target)
        if normalized == _SCENE_TARGET:
            return _SCENE_TARGET
        matched = _first_matching_name(ordered, explicit_target)
        if matched is not None:
            return matched

    # 2/3. First character, then first object (deterministic scene order).
    for name, kind in ordered:
        if kind == "character":
            return name
    for name, kind in ordered:
        if kind == "object":
            return name

    # 4. Safe scene-level fallback.
    return _SCENE_TARGET


def _resolve_secondary(scene: ScenePlan, primary_target: str | None) -> str | None:
    """Resolve a secondary camera focus target when a meaningful one exists.

    Priority:
      1. Existing explicit focus information (``camera_spec.focus_target``,
         then ``primary_focus``) when it names a real element distinct from
         the primary target.
      2. A different character from the primary target.
      3. A different object from the primary target.
      4. ``None`` when no valid distinct secondary target exists.

    Never returns the primary target again and never invents a target.
    """
    primary_norm = _normalize(primary_target or "")
    ordered = _ordered_targets(scene)

    def _distinct(name: str | None) -> str | None:
        if not name:
            return None
        if primary_norm and _normalize(name) == primary_norm:
            return None
        return name

    # 1. Existing explicit focus information, when real and distinct.
    visual = scene.visual
    if visual is not None:
        camera_spec = getattr(visual, "camera_spec", None)
        if isinstance(camera_spec, dict):
            spec_target = _normalize(str(camera_spec.get("focus_target") or ""))
            if spec_target and spec_target != _SCENE_TARGET:
                distinct = _distinct(_first_matching_name(ordered, spec_target))
                if distinct is not None:
                    return distinct
        focus = _normalize(getattr(visual, "primary_focus", ""))
        if focus and focus != _SCENE_TARGET:
            distinct = _distinct(_first_matching_name(ordered, focus))
            if distinct is not None:
                return distinct

    # 2/3. A different character, then a different object.
    for name, kind in ordered:
        if kind == "character":
            distinct = _distinct(name)
            if distinct is not None:
                return distinct
    for name, kind in ordered:
        if kind == "object":
            distinct = _distinct(name)
            if distinct is not None:
                return distinct

    # 4. No valid distinct secondary target exists.
    return None


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraDecision:
    """Camera recommendation for a single scene in a sequence."""

    scene_index: int
    recommended_pattern: str
    focus_target: str | None
    continuity_from_previous: str
    repeated_with_previous: bool
    explicit_camera_preserved: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(frozen=True)
class CameraPlan:
    """Immutable sequence-level camera planning report."""

    decisions: tuple[CameraDecision, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "warnings": list(self.warnings),
        }


class CameraPlanner:
    """Deterministic camera continuity planning for scene sequences.

    Analyzes a sequence of scenes (and optionally V1.4-A/B/C outputs) to
    recommend camera patterns that maintain visual continuity while avoiding
    repetitive patterns.

    This service is pure and read-only - it never mutates inputs.
    """

    def plan(
        self,
        scenes: list[ScenePlan],
        *,
        story_plan: VisualStoryPlan | None = None,
        diversity_report: VisualDiversityReport | None = None,
        composition_plan: CompositionPlan | None = None,
        ) -> CameraPlan:
        """Analyze a sequence of scenes for camera continuity.

        Args:
            scenes: List of ScenePlan objects to analyze.
            story_plan: Optional VisualStoryPlan from V1.4-A.
            diversity_report: Optional VisualDiversityReport from V1.4-B.
            composition_plan: Optional CompositionPlan from V1.4-C.

        Returns:
            CameraPlan with per-scene decisions and sequence warnings.
        """
        if not scenes:
            return CameraPlan(decisions=(), warnings=())

        # Build lookup dictionaries
        story_decisions: dict[int, Any] = {}
        if story_plan is not None:
            for decision in story_plan.decisions:
                story_decisions[decision.scene_index] = decision

        diversity_decisions: dict[int, Any] = {}
        if diversity_report is not None:
            for decision in diversity_report.decisions:
                diversity_decisions[decision.scene_index] = decision

        composition_decisions: dict[int, Any] = {}
        if composition_plan is not None:
            for decision in composition_plan.decisions:
                composition_decisions[decision.scene_index] = decision

        decisions: list[CameraDecision] = []
        sequence_warnings: list[str] = []
        camera_run: dict[str, int] = {}
        prev_pattern = ""

        for i, scene in enumerate(scenes):
            story_decision = story_decisions.get(i)
            diversity_decision = diversity_decisions.get(i)
            composition_decision = composition_decisions.get(i)

            explicit_camera = _get_explicit_camera(scene)
            explicit_target = _get_explicit_focus_target(scene)
            treatment = _get_treatment(scene, story_decision)
            composition_type = _get_composition_type(composition_decision)
            has_characters = _has_characters(scene)
            has_objects = _has_objects(scene)
            diversity_repeated = _is_repeated_in_diversity(diversity_decision)
            diversity_recs = _get_diversity_camera_recs(diversity_decision)

            recommended_pattern = _choose_camera_pattern(
                treatment=treatment,
                composition_type=composition_type,
                explicit_camera=explicit_camera,
                previous_pattern=prev_pattern,
                run_count=camera_run.get(prev_pattern, 0) if prev_pattern else 0,
                has_characters=has_characters,
                has_objects=has_objects,
                diversity_repeated=diversity_repeated,
            diversity_recs=diversity_recs,
            )

            if recommended_pattern:
                camera_run[recommended_pattern] = camera_run.get(recommended_pattern, 0) + 1
                for k in list(camera_run.keys()):
                    if k != recommended_pattern:
                        camera_run[k] = 0
            else:
                camera_run.clear()

            repeated_with_previous = (
                recommended_pattern == prev_pattern and recommended_pattern != ""
            )

            focus_target = _determine_focus_target(
                recommended_pattern, explicit_target, scene
            )

            continuity = _determine_continuity_state(recommended_pattern, prev_pattern)

            warnings: list[str] = []

            if explicit_camera:
                warnings.append("explicit_camera_preserved")
                if repeated_with_previous:
                    warnings.append("explicit_camera_repetition")

            if repeated_with_previous:
                warnings.append(f"repeated_camera:{recommended_pattern}")

            run_count = camera_run.get(recommended_pattern, 0)
            if run_count >= 3:
                warnings.append(f"camera_run:{recommended_pattern}:{run_count}")

            decision = CameraDecision(
                scene_index=i,
                recommended_pattern=recommended_pattern,
                focus_target=focus_target,
                continuity_from_previous=continuity,
                repeated_with_previous=repeated_with_previous,
                explicit_camera_preserved=bool(explicit_camera),
                warnings=tuple(warnings),
            )
            decisions.append(decision)

            prev_pattern = recommended_pattern

        if len(scenes) >= 3:
            patterns_used = {d.recommended_pattern for d in decisions if d.recommended_pattern}
            if len(patterns_used) <= 1:
                sequence_warnings.append("low_camera_diversity")

        return CameraPlan(
            decisions=tuple(decisions),
            warnings=tuple(sequence_warnings),
        )
