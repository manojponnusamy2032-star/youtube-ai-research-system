"""Visual Planning Application Layer (V1.5).

Deterministic, pure, standalone application service that consumes V1.4 advisory
planning metadata and selectively applies safe recommendations to staging
inputs before the existing V1.3/V1.2 rendering layer produces RenderJobSpec.

This is a *read-only* layer with respect to planning inputs: it never mutates
ScenePlan, VisualScene, V1.4 planner results, or V1.3 semantic results.  It
produces a new/modified staging dict (``visual_description``) and an immutable
application report.

Application precedence (highest to lowest):
    1. Explicit scene intent (camera_spec, primary_focus, motions, transitions)
    2. Existing V1.3 semantic decision representing explicit intent
    3. Existing scene constraints
    4. V1.4 recommendation
    5. Existing V1.2/V1.3 fallback

The layer is feature-flagged (``VISUAL_PLANNING_APPLICATION_ENABLED``) and
never executes unless V1.4 planning actually ran for the scene.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

VISUAL_PLANNING_APPLICATION_ENABLED = False


# ---------------------------------------------------------------------------
# Data model (frozen / immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VisualPlanningApplicationDecision:
    scene_index: int
    applied_camera: str | None = None
    applied_composition: str | None = None
    applied_attention: str | None = None
    camera_changed: bool = False
    composition_changed: bool = False
    attention_changed: bool = False
    changed: bool = False
    warnings: tuple[str, ...] = ()
    original_camera: dict[str, Any] = field(default_factory=dict)
    original_composition_type: str | None = None
    original_attention_target: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualPlanningApplicationReport:
    decisions: tuple[VisualPlanningApplicationDecision, ...] = ()
    applied_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0
    enabled: bool = False
    v14_required: bool = True
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [d.to_dict() for d in self.decisions],
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "warning_count": self.warning_count,
            "enabled": self.enabled,
            "v14_required": self.v14_required,
            "summary": self.summary,
        }

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _norm_pattern(pattern: Any) -> str:
    """Normalize a camera/composition pattern for safe comparison."""
    return str(pattern or "").strip().lower()


def _norm_name(name: Any) -> str:
    """Normalize an element name for safe comparison."""
    return str(name or "").strip().lower()


def _collect_names(visual_description: dict[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    """Collect normalized character and object names from a staged visual description."""
    characters = visual_description.get("characters") or ()
    objects = visual_description.get("objects") or ()
    char_names: set[str] = set()
    for ch in characters:
        if isinstance(ch, dict):
            n = _norm_name(ch.get("name"))
            if n:
                char_names.add(n)
    obj_names: set[str] = set()
    for ob in objects:
        if isinstance(ob, dict):
            n = _norm_name(ob.get("name"))
            if n:
                obj_names.add(n)
    return frozenset(char_names), frozenset(obj_names)


def _has_explicit_camera(staged_camera: dict[str, Any]) -> bool:
    """Return True if the staged camera already carries an explicit pattern."""
    p = _norm_pattern(staged_camera.get("pattern"))
    return p != "" and p in SUPPORTED_CAMERA_PATTERNS


def _has_explicit_focus(staged_camera: dict[str, Any]) -> bool:
    """Return True if the staged camera already carries an explicit focus target."""
    f = _norm_name(staged_camera.get("focus_target"))
    return f != "" and f != "scene"


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Read an attribute from either a dict or an object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _resolve_target(target: Any, char_names: frozenset[str], obj_names: frozenset[str]) -> str | None:
    """Resolve a target name against actual scene element names. Never invents."""
    n = _norm_name(target)
    if not n or n == "scene":
        return None
    if n in char_names or n in obj_names:
        return n
    return None

# ---------------------------------------------------------------------------
# Camera application
# ---------------------------------------------------------------------------


def _apply_camera(
    staged_camera: dict[str, Any],
    camera_decision: Any,
    char_names: frozenset[str],
    obj_names: frozenset[str],
) -> tuple[dict[str, Any], bool, str, tuple[str, ...]]:
    """Apply a V1.4-D camera recommendation to a staged camera dict.

    Returns (new_camera, changed, reason, warnings).
    """
    warnings: list[str] = []
    rec = _get_attr(camera_decision, "recommended_pattern", None)
    rec_norm = _norm_pattern(rec)

    if not rec_norm:
        return dict(staged_camera), False, "no camera recommendation", tuple(warnings)

    if rec_norm not in SUPPORTED_CAMERA_PATTERNS:
        warnings.append(f"unsupported camera pattern: {rec_norm}")
        return dict(staged_camera), False, "unsupported camera pattern", tuple(warnings)

    if _has_explicit_camera(staged_camera):
        warnings.append("explicit camera preserved")
        return dict(staged_camera), False, "explicit camera preserved", tuple(warnings)

    focus_target = _get_attr(camera_decision, "focus_target", None)
    resolved_focus = _resolve_target(focus_target, char_names, obj_names)

    if rec_norm in ("focus_on_character", "focus_on_object"):
        if not resolved_focus:
            warnings.append(f"focus target not resolvable: {_norm_name(focus_target)}")
            return dict(staged_camera), False, "focus target not resolvable", tuple(warnings)
        new_cam = dict(staged_camera)
        new_cam["pattern"] = rec_norm
        new_cam["focus_target"] = resolved_focus
        return new_cam, True, "camera applied", tuple(warnings)

    new_cam = dict(staged_camera)
    new_cam["pattern"] = rec_norm
    return new_cam, True, "camera applied", tuple(warnings)

# ---------------------------------------------------------------------------
# Composition application
# ---------------------------------------------------------------------------


def _apply_composition(
    visual_description: dict[str, Any],
    composition_decision: Any,
    char_names: frozenset[str],
    obj_names: frozenset[str],
) -> tuple[dict[str, Any], bool, str, tuple[str, ...]]:
    """Apply a V1.4-C composition recommendation to a staged visual description.

    Composition is recorded as metadata only.
    Returns (new_description, changed, reason, warnings).
    """
    warnings: list[str] = []
    comp_type = _norm_pattern(_get_attr(composition_decision, "composition_type", None))
    if not comp_type:
        return dict(visual_description), False, "no composition recommendation", tuple(warnings)

    n_chars = len(char_names)
    n_objs = len(obj_names)

    if comp_type == "single_subject" and n_chars < 1 and n_objs < 1:
        warnings.append("single_subject requires at least one subject")
        return dict(visual_description), False, "no subject for single_subject", tuple(warnings)

    if comp_type == "comparison" and n_chars < 2:
        warnings.append("comparison requires at least two subjects")
        return dict(visual_description), False, "insufficient subjects for comparison", tuple(warnings)

    if comp_type == "object_led" and n_objs < 1:
        warnings.append("object_led requires at least one object")
        return dict(visual_description), False, "no object for object_led", tuple(warnings)

    new_desc = dict(visual_description)
    new_desc["recommended_composition"] = comp_type
    return new_desc, False, "composition recorded (metadata only)", tuple(warnings)

# ---------------------------------------------------------------------------
# Attention application
# ---------------------------------------------------------------------------


def _apply_attention(
    staged_camera: dict[str, Any],
    attention_decision: Any,
    char_names: frozenset[str],
    obj_names: frozenset[str],
    original_camera: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool, str, tuple[str, ...]]:
    """Apply a V1.4-E attention recommendation to a staged camera dict.

    Returns (new_camera, changed, reason, warnings).

    Attention respects the application precedence:
      1. Explicit scene focus (author-provided focus_target) is preserved.
      2. A camera focus target produced by V1.4-D application is respected
         (camera target constraints) -- attention does not override it.
      3. Otherwise the attention target is applied only if it resolves to a
         real scene character/object.
    """
    warnings: list[str] = []

    if _has_explicit_focus(original_camera if original_camera is not None else staged_camera):
        warnings.append("explicit focus preserved")
        return dict(staged_camera), False, "explicit focus preserved", tuple(warnings)

    if _has_explicit_focus(staged_camera):
        warnings.append("camera focus already applied")
        return dict(staged_camera), False, "camera focus already applied", tuple(warnings)

    primary = _get_attr(attention_decision, "primary_target", None)
    resolved = _resolve_target(primary, char_names, obj_names)

    if not resolved:
        warnings.append(f"attention target not resolvable: {_norm_name(primary)}")
        return dict(staged_camera), False, "attention target not resolvable", tuple(warnings)

    new_cam = dict(staged_camera)
    new_cam["focus_target"] = resolved
    return new_cam, True, "attention applied", tuple(warnings)

# ---------------------------------------------------------------------------
# Per-scene application
# ---------------------------------------------------------------------------


def apply_visual_planning(
    visual_description: dict[str, Any],
    visual_planning: dict[str, Any],
    scene_index: int = 0,
) -> tuple[dict[str, Any], VisualPlanningApplicationDecision]:
    """Apply V1.4 planning recommendations to a single staged visual description.

    This is the main per-scene entry point.  It consumes the visual_planning
    metadata dict and returns a *new* staged visual description along with an
    immutable application decision.

    When the feature flag VISUAL_PLANNING_APPLICATION_ENABLED is False the
    staging description is returned unchanged (same object) with a decision
    that carries ``changed=False``.

    Args:
        visual_description: The staged visual description dict.
        visual_planning: The V1.4 planning metadata dict for this scene.
        scene_index: The zero-based scene index (for reporting only).

    Returns:
        A (new_visual_description, decision) tuple.
    """
    if not VISUAL_PLANNING_APPLICATION_ENABLED:
        decision = VisualPlanningApplicationDecision(
            scene_index=scene_index,
            reason="application disabled (flag OFF)",
        )
        return visual_description, decision

    staged_camera = dict(visual_description.get("camera") or {})
    char_names, obj_names = _collect_names(visual_description)

    original_camera = dict(staged_camera)
    original_composition = None
    original_attention = staged_camera.get("focus_target")

    warnings: list[str] = []
    applied_camera: str | None = None
    applied_composition: str | None = None
    applied_attention: str | None = None
    camera_changed = False
    composition_changed = False
    attention_changed = False

    # --- Camera (V1.4-D) ---
    camera_decision = visual_planning.get("camera")
    if camera_decision is not None:
        new_cam, changed, reason, cam_warnings = _apply_camera(
            staged_camera, camera_decision, char_names, obj_names
        )
        warnings.extend(cam_warnings)
        if changed:
            staged_camera = new_cam
            applied_camera = _norm_pattern(new_cam.get("pattern"))
            camera_changed = True

    # --- Composition (V1.4-C) ---
    composition_decision = visual_planning.get("composition")
    if composition_decision is not None:
        original_composition = _norm_pattern(
            _get_attr(composition_decision, "composition_type", None)
        )
        new_desc, changed, reason, comp_warnings = _apply_composition(
            visual_description, composition_decision, char_names, obj_names
        )
        warnings.extend(comp_warnings)
        if changed or "recommended_composition" in new_desc:
            visual_description = new_desc
            applied_composition = _norm_pattern(new_desc.get("recommended_composition"))
            composition_changed = True

    # --- Attention (V1.4-E) ---
    attention_decision = visual_planning.get("attention")
    if attention_decision is not None:
        new_cam, changed, reason, att_warnings = _apply_attention(
            staged_camera,
            attention_decision,
            char_names,
            obj_names,
            original_camera=original_camera,
        )
        warnings.extend(att_warnings)
        if changed:
            staged_camera = new_cam
            applied_attention = _norm_name(new_cam.get("focus_target"))
            attention_changed = True

    new_visual_description = dict(visual_description)
    new_visual_description["camera"] = staged_camera

    changed = camera_changed or composition_changed or attention_changed

    decision = VisualPlanningApplicationDecision(
        scene_index=scene_index,
        applied_camera=applied_camera,
        applied_composition=applied_composition,
        applied_attention=applied_attention,
        camera_changed=camera_changed,
        composition_changed=composition_changed,
        attention_changed=attention_changed,
        changed=changed,
        warnings=tuple(warnings),
        original_camera=original_camera,
        original_composition_type=original_composition,
        original_attention_target=original_attention,
        reason="; ".join(warnings) if warnings else ("applied" if changed else "no change"),
    )

    return new_visual_description, decision

# ---------------------------------------------------------------------------
# Sequence-level application
# ---------------------------------------------------------------------------


def apply_visual_planning_sequence(
    visual_descriptions: list[dict[str, Any]],
    visual_plannings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], VisualPlanningApplicationReport]:
    """Apply V1.4 planning recommendations across a sequence of scenes.

    When the feature flag VISUAL_PLANNING_APPLICATION_ENABLED is False, or
    when visual_plannings is empty (V1.4 did not run), this function returns
    the original visual_descriptions unchanged (as new lists).

    Args:
        visual_descriptions: List of staged visual description dicts.
        visual_plannings: List of V1.4 planning metadata dicts (parallel to
            visual_descriptions).

    Returns:
        A (new_visual_descriptions, report) tuple.
    """
    if not VISUAL_PLANNING_APPLICATION_ENABLED:
        report = VisualPlanningApplicationReport(
            decisions=(),
            applied_count=0,
            skipped_count=len(visual_descriptions),
            warning_count=0,
            enabled=False,
            v14_required=True,
            summary="application disabled (flag OFF)",
        )
        return list(visual_descriptions), report

    if not visual_plannings:
        report = VisualPlanningApplicationReport(
            decisions=(),
            applied_count=0,
            skipped_count=len(visual_descriptions),
            warning_count=0,
            enabled=True,
            v14_required=True,
            summary="application skipped (V1.4 did not run)",
        )
        return list(visual_descriptions), report

    new_descriptions: list[dict[str, Any]] = []
    decisions: list[VisualPlanningApplicationDecision] = []
    applied_count = 0
    skipped_count = 0
    warning_count = 0

    for idx, (desc, vp) in enumerate(zip(visual_descriptions, visual_plannings)):
        new_desc, decision = apply_visual_planning(desc, vp or {}, scene_index=idx)
        new_descriptions.append(new_desc)
        decisions.append(decision)
        if decision.changed:
            applied_count += 1
        else:
            skipped_count += 1
        if decision.warnings:
            warning_count += len(decision.warnings)

    report = VisualPlanningApplicationReport(
        decisions=tuple(decisions),
        applied_count=applied_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
        enabled=VISUAL_PLANNING_APPLICATION_ENABLED,
        v14_required=True,
        summary=f"applied={applied_count}, skipped={skipped_count}, warnings={warning_count}",
    )

    return new_descriptions, report
