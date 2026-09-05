"""Camera Execution Layer (V1.6-D).

Deterministic, pure, standalone service that translates camera intent and
planning decisions (V1.4 camera/attention planners and V1.5 planning
application, or explicit scene ``camera_spec``) into *executable* ``CameraSpec``
metadata consumed by the existing renderer.

This is an **execution layer**, not a planning replacement: V1.4 decides WHAT
the camera should do; this layer makes that decision visibly happen by producing
the exact camera spec the renderer already knows how to execute.  It never
modifies V1.4/V1.5 planner results, never mutates ScenePlan/VisualScene, and
does not change the renderer.

Precedence (highest to lowest):

1. Explicit camera motion primitives (``Motion`` with ``target=="camera"``) --
   the renderer executes these directly and suppresses the declarative camera
   spec, so this layer defers without writing anything.
2. Explicit executable camera spec (``visual_description["camera"]["pattern"]``
   in ``SUPPORTED_CAMERA_PATTERNS``) -- preserved exactly as authored.
3. V1.4 camera decision (``visual_planning.camera.recommended_pattern``) and
   V1.4-A story recommendation (``visual_planning.recommended_camera``).
4. V1.6-D scene-aware fallback derived deterministically from the scene role
   (used only when no planning decision exists).
5. Safe fallback -- static framing (identical to today's renderer default).

Focal point priority for ``focus_on_character``/``focus_on_object``:
explicit ``camera_spec.focus_target``, then the V1.4 camera decision focus
target, then the V1.4 attention ``primary_target``, then a safe downgrade to
``slow_zoom_in`` (the renderer would otherwise zoom with no subject).

Execution model: the produced ``camera`` dict is a ``CameraSpec``-compatible
dict using the renderer's existing vocabulary and coordinate conventions
(normalized positions, renderer-bounded zoom/pan patterns).  Camera *movement*
is smoothed temporally by the existing renderer interpolation
(``apply_easing``/``interpolate_value``); this layer only supplies the bounded
end state, duration and easing -- it does not introduce a second animation
framework.

Continuity: sequence-level execution threads the previous scene's executed
camera so the *fallback* path (step 4) avoids direct direction reversals
(``pan_left``<->``pan_right``, ``slow_zoom_in``<->``slow_zoom_out``).  Planner
decisions remain authoritative and are never rewritten for continuity.

Determinism: no ``random``, no timestamps, no UUIDs, no global state.  Identical
inputs always produce identical outputs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

VISUAL_CAMERA_EXECUTION_ENABLED = False


# ---------------------------------------------------------------------------
# Deterministic scene-role fallback vocabulary (fallback path only)
# ---------------------------------------------------------------------------

# Scene role -> deterministic preferred camera options (fixed order; the
# scene index picks an option by rotation).  Only used when no explicit camera
# and no V1.4/V1.5 camera decision exists, so planner output stays authoritative.
_ROLE_FALLBACK_CAMERAS: dict[str, tuple[str, ...]] = {
    "hook": ("slow_zoom_in", "static"),
    "problem": ("slow_zoom_in", "focus_on_character", "static"),
    "explanation": ("static", "pan_right"),
    "object_interaction": ("focus_on_object", "slow_zoom_in", "static"),
    "character_action": ("pan_right", "static", "slow_zoom_in"),
    "transformation": ("slow_zoom_out", "static"),
    "comparison": ("pan_left", "pan_right", "static"),
    "payoff": ("slow_zoom_in", "focus_on_character", "static"),
    "solution": ("slow_zoom_in", "static"),
    "cta": ("static", "slow_zoom_out"),
}

_DEFAULT_FALLBACK_PATTERN = "static"

# Direct reversals avoided in the fallback path only (light continuity).
_OPPOSITE_PATTERN: dict[str, str] = {
    "pan_left": "pan_right",
    "pan_right": "pan_left",
    "slow_zoom_in": "slow_zoom_out",
    "slow_zoom_out": "slow_zoom_in",
}

_FOCUS_PATTERNS = frozenset({"focus_on_character", "focus_on_object"})

# Emphasis patterns get a short, controlled duration (seconds) so the movement
# completes early and holds -- an emphasis zoom rather than a full-scene crawl.
_EMPHATIC_PATTERNS: frozenset[str] = frozenset(
    {"focus_on_character", "focus_on_object"}
)
_EMPHATIC_MAX_SECONDS = 1.6
_MIN_DURATION_SECONDS = 0.4
# ---------------------------------------------------------------------------
# Data model (frozen / immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraExecutionDecision:
    """What the V1.6-D execution layer decided for one scene."""

    scene_index: int
    pattern: str = "static"
    focus_target: str | None = None
    duration: float = 0.0
    easing: str = "ease_in_out"
    source: str = "none"
    changed: bool = False
    skipped: bool = False
    warnings: tuple[str, ...] = ()
    reason: str = ""
    original_camera: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CameraExecutionReport:
    decisions: tuple[CameraExecutionDecision, ...] = ()
    applied_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0
    enabled: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "warning_count": self.warning_count,
            "enabled": self.enabled,
            "summary": self.summary,
        }
# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _norm_pattern(value: Any) -> str:
    return str(value or "").strip().lower()


def _norm_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_duration(value: Any) -> float:
    """Return a finite positive scene duration (seconds), never NaN/inf."""
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(duration) or duration <= 0:
        return 1.0
    return duration


def _collect_names(
    visual_description: dict[str, Any],
) -> tuple[frozenset[str], frozenset[str]]:
    """Collect normalized character and object names from a staged description."""
    char_names: set[str] = set()
    for character in visual_description.get("characters") or ():
        if isinstance(character, dict):
            name = _norm_name(character.get("name"))
            if name:
                char_names.add(name)
    obj_names: set[str] = set()
    for obj in visual_description.get("objects") or ():
        if isinstance(obj, dict):
            name = _norm_name(obj.get("name"))
            if name:
                obj_names.add(name)
    return frozenset(char_names), frozenset(obj_names)


def _resolve_focus(
    candidate: Any,
    char_names: frozenset[str],
    obj_names: frozenset[str],
) -> str | None:
    """Resolve a focus target against real scene elements. Never invents."""
    name = _norm_name(candidate)
    if name and (name in char_names or name in obj_names):
        return name
    return None


def _has_camera_motion(camera_motions: list[Any] | None) -> bool:
    """Return True when an explicit camera motion primitive is present.

    The renderer executes explicit ``target=="camera"`` motions directly and
    suppresses the declarative CameraSpec path, so this layer must defer to
    them (explicit scene intent always wins).
    """
    for motion in camera_motions or []:
        if isinstance(motion, dict):
            target = _norm_pattern(motion.get("target"))
        else:
            target = _norm_pattern(getattr(motion, "target", ""))
        if target == "camera":
            return True
    return False


def _has_executable_pattern(staged_camera: dict[str, Any]) -> bool:
    """Return True when the staged camera already carries an executable pattern."""
    return _norm_pattern(staged_camera.get("pattern")) in SUPPORTED_CAMERA_PATTERNS
def _decision_camera(
    planning_metadata: dict[str, Any] | None,
) -> tuple[str, Any, str]:
    """Extract a safe camera pattern from V1.4/V1.5 planning metadata.

    Returns ``(pattern, focus_candidate, source)`` where pattern is a supported
    pattern or "" when no usable recommendation exists.
    """
    if not isinstance(planning_metadata, dict):
        return "", None, ""
    camera_meta = planning_metadata.get("camera")
    if isinstance(camera_meta, dict):
        recommended = _norm_pattern(camera_meta.get("recommended_pattern"))
        if recommended in SUPPORTED_CAMERA_PATTERNS:
            return recommended, camera_meta.get("focus_target"), "v14_camera_decision"
    recommended = _norm_pattern(planning_metadata.get("recommended_camera"))
    if recommended in SUPPORTED_CAMERA_PATTERNS:
        return recommended, None, "v14_story_recommendation"
    return "", None, ""


def _preferred_focus(
    planning_metadata: dict[str, Any] | None,
    char_names: frozenset[str],
    obj_names: frozenset[str],
) -> str | None:
    """Resolve the best available focus target from planning metadata."""
    if not isinstance(planning_metadata, dict):
        return None
    camera_meta = planning_metadata.get("camera")
    if isinstance(camera_meta, dict):
        target = _resolve_focus(
            camera_meta.get("focus_target"), char_names, obj_names
        )
        if target:
            return target
    attention_meta = planning_metadata.get("attention")
    if isinstance(attention_meta, dict):
        target = _resolve_focus(
            attention_meta.get("primary_target"), char_names, obj_names
        )
        if target:
            return target
    return None


def _fallback_pattern(role: str, scene_index: int, previous_pattern: str) -> str:
    """Deterministic scene-role fallback with light continuity (no reversals)."""
    options = _ROLE_FALLBACK_CAMERAS.get(role, (_DEFAULT_FALLBACK_PATTERN,))
    pattern = options[abs(int(scene_index)) % len(options)]
    prev = _norm_pattern(previous_pattern)
    if prev and _OPPOSITE_PATTERN.get(pattern) == prev and len(options) > 1:
        # Light continuity for the fallback path only: do not directly reverse
        # the previous scene's pan/zoom direction.
        pattern = options[(abs(int(scene_index)) + 1) % len(options)]
    if pattern not in SUPPORTED_CAMERA_PATTERNS:
        return _DEFAULT_FALLBACK_PATTERN
    return pattern


def _build_camera(
    pattern: str,
    focus_target: str | None,
    scene_duration: float,
) -> dict[str, Any]:
    """Build a bounded, renderer-executable CameraSpec-compatible dict."""
    camera: dict[str, Any] = {"pattern": pattern, "easing": "ease_in_out"}
    if pattern in _FOCUS_PATTERNS and focus_target:
        camera["focus_target"] = focus_target
    duration = max(_MIN_DURATION_SECONDS, scene_duration)
    if pattern in _EMPHATIC_PATTERNS:
        # Short controlled emphasis movement that completes early and holds.
        duration = min(duration, _EMPHATIC_MAX_SECONDS)
    camera["duration"] = round(
        max(_MIN_DURATION_SECONDS, min(duration, scene_duration)), 3
    )
    return camera


def _decision_from_path(
    scene_index: int,
    pattern: str,
    focus_target: str | None,
    duration: float,
    source: str,
    *,
    changed: bool,
    warnings: tuple[str, ...],
    reason: str,
    original_camera: dict[str, Any],
) -> CameraExecutionDecision:
    return CameraExecutionDecision(
        scene_index=int(scene_index),
        pattern=pattern,
        focus_target=focus_target,
        duration=round(duration, 3),
        easing="ease_in_out",
        source=source,
        changed=changed,
        skipped=not changed,
        warnings=warnings,
        reason=reason,
        original_camera=dict(original_camera),
    )
# ---------------------------------------------------------------------------
# Per-scene camera execution
# ---------------------------------------------------------------------------


def apply_camera_execution(
    visual_description: dict[str, Any] | None,
    *,
    scene_index: int = 0,
    scene_role: str = "general",
    duration: float | None = None,
    planning_metadata: dict[str, Any] | None = None,
    previous_camera: dict[str, Any] | None = None,
    camera_motions: list[Any] | None = None,
) -> tuple[dict[str, Any], CameraExecutionDecision]:
    """Translate camera intent into an executable CameraSpec.

    The returned ``visual_description`` carries an executable ``camera`` dict
    (when a decision is applied) plus a ``camera_execution`` metadata key (when
    the feature is enabled).  When the flag is OFF the description is returned
    as a shallow copy that is content-identical to the input.

    Args:
        visual_description: Staged visual description dict (may be None/empty).
        scene_index: Zero-based scene index (used for deterministic rotation).
        scene_role: Narrative scene role (fallback path only).
        duration: Scene duration in seconds.
        planning_metadata: V1.4 ``visual_planning`` metadata dict, when present.
        previous_camera: The executed camera dict of the previous scene, when
            available (used for light continuity in the fallback path only).
        camera_motions: Explicit ``Motion`` primitives for this scene; any with
            ``target=="camera"`` are deferred to (renderer executes them).

    Returns:
        A ``(new_visual_description, decision)`` tuple.  The decision carries
        ``skipped=True`` whenever execution is deferred to existing behavior.
    """
    scene_duration = _safe_duration(duration)

    if not VISUAL_CAMERA_EXECUTION_ENABLED:
        decision = CameraExecutionDecision(
            scene_index=int(scene_index),
            skipped=True,
            reason="camera execution disabled (flag OFF)",
        )
        return dict(visual_description or {}), decision

    desc = dict(visual_description or {})
    original_camera = desc.get("camera")
    if not isinstance(original_camera, dict):
        original_camera = {}
    original_camera = dict(original_camera)

    warnings: list[str] = []
    char_names, obj_names = _collect_names(desc)

    # 1) Explicit camera motion primitives take the renderer's motion path and
    #    suppress the declarative CameraSpec; defer to them unchanged.
    if _has_camera_motion(camera_motions):
        decision = _decision_from_path(
            scene_index,
            pattern="static",
            focus_target=None,
            duration=0.0,
            source="explicit_camera_motion",
            changed=False,
            warnings=("explicit_camera_motion_preserved",),
            reason="explicit camera motion preserved",
            original_camera=original_camera,
        )
        desc["camera_execution"] = decision.to_dict()
        return desc, decision

    # 2) Explicit executable camera spec (author-authored or V1.5-applied) is
    #    preserved exactly; the renderer already executes it.
    if _has_executable_pattern(original_camera):
        decision = _decision_from_path(
            scene_index,
            pattern=_norm_pattern(original_camera.get("pattern")),
            focus_target=original_camera.get("focus_target"),
            duration=float(original_camera.get("duration") or 0.0),
            source="explicit_camera",
            changed=False,
            warnings=("explicit_camera_preserved",),
            reason="explicit camera spec preserved",
            original_camera=original_camera,
        )
        desc["camera_execution"] = decision.to_dict()
        return desc, decision

    focus_candidate: Any = None
    source = ""
    pattern = ""

    # 3) V1.4/V1.5 camera decision (planning metadata).
    decision_pattern, decision_focus, decision_source = _decision_camera(
        planning_metadata
    )
    if decision_pattern:
        pattern = decision_pattern
        source = decision_source
        focus_candidate = decision_focus
    else:
        # 4) Scene-aware fallback (deterministic, continuity-guarded).
        fallback = _fallback_pattern(
            _norm_pattern(scene_role),
            int(scene_index),
            _norm_pattern((previous_camera or {}).get("pattern")),
        )
        pattern = fallback
        source = (
            "scene_role_fallback"
            if fallback != _DEFAULT_FALLBACK_PATTERN
            else "safe_fallback"
        )

    if pattern not in SUPPORTED_CAMERA_PATTERNS:
        pattern = _DEFAULT_FALLBACK_PATTERN
        source = "safe_fallback"

    # Focal point resolution (only used by focus patterns).
    explicit_focus = _resolve_focus(
        original_camera.get("focus_target"), char_names, obj_names
    )
    resolved_focus = explicit_focus
    if resolved_focus is None and pattern in _FOCUS_PATTERNS:
        resolved_focus = _preferred_focus(planning_metadata, char_names, obj_names)
    if resolved_focus is None and pattern in _FOCUS_PATTERNS and focus_candidate:
        resolved_focus = _resolve_focus(focus_candidate, char_names, obj_names)

    if pattern in _FOCUS_PATTERNS and resolved_focus is None:
        # No resolvable focus subject: downgrade to a safe zoom that needs no
        # target.  This is safer than zooming with nothing to center on.
        warnings.append("focus_target_unresolvable")
        pattern = "slow_zoom_in"
        if source != "safe_fallback":
            source = f"{source}|zoom_fallback"
        else:
            source = "safe_fallback"

    camera = _build_camera(pattern, resolved_focus, scene_duration)
    effective_duration = float(camera.get("duration", 0.0))

    if source == "explicit_camera":
        reason_parts = ["explicit camera spec preserved"]
    elif source == "v14_camera_decision":
        reason_parts = ["V1.4 camera decision executed"]
    elif source == "v14_story_recommendation":
        reason_parts = ["V1.4 story camera recommendation executed"]
    elif source == "scene_role_fallback":
        reason_parts = ["scene-aware fallback executed"]
    else:
        reason_parts = ["safe static fallback"]
    reason_parts.extend(warnings)
    reason = "; ".join(reason_parts)

    new_desc = dict(desc)
    new_desc["camera"] = camera
    decision = _decision_from_path(
        scene_index,
        pattern=pattern,
        focus_target=resolved_focus,
        duration=effective_duration,
        source=source,
        changed=True,
        warnings=tuple(warnings),
        reason=reason,
        original_camera=original_camera,
    )
    new_desc["camera_execution"] = decision.to_dict()
    return new_desc, decision
# ---------------------------------------------------------------------------
# Sequence-level application
# ---------------------------------------------------------------------------


def apply_camera_execution_sequence(
    visual_descriptions: list[dict[str, Any]],
    planning_metadatas: list[dict[str, Any] | None] | None = None,
    *,
    scene_roles: list[str] | None = None,
    durations: list[float] | None = None,
    camera_motions: list[list[Any]] | None = None,
) -> tuple[list[dict[str, Any]], CameraExecutionReport]:
    """Apply camera execution across a sequence of scenes.

    Threads the previous scene's executed camera into each scene so the
    fallback path avoids direct direction reversals.  When the feature flag is
    OFF this returns the original descriptions unchanged (as new lists) with a
    disabled report.

    Args:
        visual_descriptions: Staged visual description dicts.
        planning_metadatas: Parallel V1.4 ``visual_planning`` metadata dicts
            (or None entries when no planning metadata exists for the scene).
        scene_roles: Optional parallel scene roles (defaults to "general").
        durations: Optional parallel scene durations (defaults to 1.0).
        camera_motions: Optional parallel explicit motion lists.

    Returns:
        A ``(new_visual_descriptions, report)`` tuple.
    """
    total = len(visual_descriptions)
    if not VISUAL_CAMERA_EXECUTION_ENABLED:
        report = CameraExecutionReport(
            applied_count=0,
            skipped_count=total,
            warning_count=0,
            enabled=False,
            summary="camera execution disabled (flag OFF)",
        )
        return list(visual_descriptions), report

    new_descriptions: list[dict[str, Any]] = []
    decisions: list[CameraExecutionDecision] = []
    applied_count = 0
    skipped_count = 0
    warning_count = 0
    previous_camera: dict[str, Any] | None = None

    for index, desc in enumerate(visual_descriptions):
        planning = None
        if planning_metadatas is not None and index < len(planning_metadatas):
            planning = planning_metadatas[index]
        role = "general"
        if scene_roles is not None and index < len(scene_roles):
            role = scene_roles[index]
        scene_duration: float | None = None
        if durations is not None and index < len(durations):
            scene_duration = durations[index]
        scene_motions: list[Any] | None = None
        if camera_motions is not None and index < len(camera_motions):
            scene_motions = camera_motions[index]

        new_desc, decision = apply_camera_execution(
            desc or {},
            scene_index=index,
            scene_role=role,
            duration=scene_duration,
            planning_metadata=planning,
            previous_camera=previous_camera,
            camera_motions=scene_motions,
        )
        new_descriptions.append(new_desc)
        decisions.append(decision)
        executed_camera = (new_desc or {}).get("camera")
        previous_camera = (
            executed_camera
            if isinstance(executed_camera, dict) and executed_camera
            else None
        )
        if decision.changed:
            applied_count += 1
        else:
            skipped_count += 1
        warning_count += len(decision.warnings)

    report = CameraExecutionReport(
        decisions=tuple(decisions),
        applied_count=applied_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
        enabled=True,
        summary=f"camera execution applied to {applied_count}/{total} scenes",
    )
    return new_descriptions, report