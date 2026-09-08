"""V1.6-G — Camera Diversity, Scene Activity & Attention-Target Safety.

An additive, deterministic execution layer that sits between scene
choreography (V1.6-E) and RenderJobSpec construction. It does NOT replace or
rewrite any earlier V1.6 service. It performs three narrowly-scoped jobs:

* G1  — reduce excessive repetition of the same camera pattern across a
        sequence when semantically valid alternatives exist.
* G4  — ensure the camera spec never carries a placeholder/empty
        ``focus_target`` that downstream code could interpret as a fake
        character target (e.g. ``"character"`` / ``""``).
* G3  — surface scene-activity observations as advisory metadata only.

G2 (weaker pan/zoom-then-pan rendering) is addressed directly in the
renderer's ``_apply_camera_pattern`` by widening the interpolation ranges
that were previously too narrow to be visually observable.

The layer is feature-flagged (``VISUAL_CAMERA_DIVERSITY_ENABLED``) and
defaults to OFF. When OFF the supplied ``visual_description`` is returned
unchanged (same dict), with no metadata and no pipeline side effects.
"""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Any

# The single feature flag for the whole milestone, matching the V1.6-A/B/C/D/E
# naming convention. G2 (renderer tuning) is tied to this flag as well: when it
# is OFF, the widened pan ranges are not applied so the renderer behaves
# exactly as at the current committed baseline.
VISUAL_CAMERA_DIVERSITY_ENABLED = False

# Deterministic widening of the camera pan/zoom-then-pan ranges so a rendered
# pan_* movement is observably visible (G2). At the previous values only
# +/-0.06*width was travelled, which at 720p is ~+/-6 px -- imperceptible.
PAN_RANGE_RATIO = 0.15          # +/-0.15 * width  (~288 px @ 1080p, bounded)
ZOOM_THEN_PAN_RANGE_RATIO = 0.08  # +/-0.08 * width  (~192 px @ 1080p, bounded)
SAFE_PAN_RATIO = 0.20           # keep pan centre within 20% bounds

# Maximum times the same non-static camera pattern may appear before the
# diversity scorer is allowed to prefer an alternative.
_MAX_REPEAT = 2


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraDiversityAction:
    """A single camera-pattern change recommended by the diversity scorer."""

    scene_index: int
    before: str
    after: str
    reason: str


@dataclass(frozen=True)
class CameraDiversityDecision:
    """Per-scene camera diversity outcome for one scene."""

    scene_index: int
    pattern: str
    focus_target: str
    executed_changed: bool
    actions: tuple[CameraDiversityAction, ...] = ()
    changed: bool = False
    skipped: bool = False
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CameraDiversityReport:
    """Sequence-level report for V1.6-G."""

    scenes: tuple[CameraDiversityDecision, ...] = ()
    applied_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0
    enabled: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenes": [scene.to_dict() for scene in self.scenes],
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "warning_count": self.warning_count,
            "enabled": self.enabled,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class CameraDiversityResult:
    """Output of ``apply_camera_diversity`` for one scene."""

    visual_description: dict[str, Any]
    decision: CameraDiversityDecision


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_EPS = 1e-9

# Candidate alternative camera patterns grouped by scene role. These are the
# renderer-supported patterns (see scene_composition.SUPPORTED_CAMERA_PATTERNS).
_ROLE_PATTERN_LADDERS: dict[str, tuple[str, ...]] = {
    "hook": ("slow_zoom_in", "zoom_then_pan", "focus_on_character"),
    "problem": ("pan_right", "slow_zoom_out", "focus_on_character"),
    "contrast": ("pan_left", "zoom_then_pan", "focus_on_character"),
    "explanation": ("slow_zoom_in", "pan_right", "focus_on_character"),
    "example": ("pan_left", "slow_zoom_in", "focus_on_character"),
    "solution": ("slow_zoom_out", "zoom_then_pan", "focus_on_character"),
    "cta": ("zoom_then_pan", "slow_zoom_in", "focus_on_character"),
    "conclusion": ("slow_zoom_out", "focus_on_character", "static"),
}


def _is_placeholder_target(name: Any, cast: Any) -> bool:
    """True when a camera focus_target is a placeholder/fake character target.

    The V1.4-D planner sometimes emits ``focus_target`` values of ``"character"``
    or an empty string when no concrete target resolves. Downstream code must
    never interpret such a value as a real cast member.
    """
    candidate = str(name or "").strip()
    if candidate == "":
        return True
    if candidate.lower() in {"character", "object", "text", "background", "none"}:
        return True
    normalized = candidate.lower()
    if cast is not None and normalized not in {str(item).lower() for item in cast}:
        return True
    return False


def _safe_camera_spec(camera: Any, cast: Any) -> dict[str, Any]:
    """Return a sanitized copy of a camera spec (never mutates the caller's)."""
    if not isinstance(camera, dict):
        return {}
    cleaned = dict(camera)
    pattern = str(cleaned.get("pattern") or "").strip().lower()
    if pattern in ("focus_on_character", "focus_on_object") and _is_placeholder_target(
        cleaned.get("focus_target"), cast
    ):
        cleaned["focus_target"] = ""
        cleaned["focus_target_warning"] = "resolved_placeholder_focus_target"
    return cleaned


def _activity_hint(scene_role: str, character_count: int) -> str:
    """Advisory activity classification (G3 observability only)."""
    role = (scene_role or "general").strip().lower()
    if role in ("hook", "cta", "contrast", "solution", "conclusion"):
        return "high" if character_count >= 2 else "medium"
    if role in ("problem", "explanation", "example"):
        return "medium"
    return "low"


# Role-aware candidate patterns for diversity (most-preferred first per role).
_ROLE_DIVERSITY_ORDER: dict[str, tuple[str, ...]] = {
    "hook": ("slow_zoom_in", "pan_right", "pan_left", "zoom_then_pan"),
    "problem": ("pan_left", "pan_right", "slow_zoom_in", "zoom_then_pan"),
    "contrast": ("pan_right", "pan_left", "zoom_then_pan", "slow_zoom_in"),
    "explanation": ("slow_zoom_in", "pan_left", "pan_right", "zoom_then_pan"),
    "example": ("pan_left", "pan_right", "slow_zoom_in", "zoom_then_pan"),
    "solution": ("slow_zoom_out", "pan_right", "pan_left", "slow_zoom_in"),
    "cta": ("slow_zoom_in", "zoom_then_pan", "pan_right", "pan_left"),
}
_FALLBACK_DIVERSITY_ORDER: tuple[str, ...] = (
    "pan_right", "pan_left", "slow_zoom_in", "zoom_then_pan",
)


def _pick_diverse_pattern(
    current: str,
    previous: tuple[str, ...],
    scene_role: str,
) -> str:
    """Deterministically pick a camera pattern that avoids over-repetition.

    If ``current`` has already appeared at least ``_MAX_REPEAT`` times in
    ``previous``, prefer the first role-aware alternative that differs from
    ``current``. Otherwise return ``current`` unchanged.
    """
    if not current or current == "static":
        return current
    recent = tuple(previous[-_MAX_REPEAT:])
    if recent.count(current) < _MAX_REPEAT:
        return current
    role = (scene_role or "general").strip().lower()
    candidates = _ROLE_DIVERSITY_ORDER.get(role, _FALLBACK_DIVERSITY_ORDER)
    for candidate in candidates:
        if candidate != current:
            return candidate
    return current


def _sanitized_sequence_camera(
    specs: list[dict[str, Any] | None],
    scene_roles: list[str | None],
) -> list[CameraDiversityAction]:
    """Compute deterministic camera-pattern changes for a scene sequence (G1)."""
    actions: list[CameraDiversityAction] = []
    counts: dict[str, int] = {}
    for index, spec in enumerate(specs):
        pattern = (
            str(spec.get("pattern") or "static").strip().lower() if spec else "static"
        )
        role = (
            (scene_roles[index] or "general").strip().lower()
            if index < len(scene_roles)
            else "general"
        )
        # Respect semantic repetition: focus_on_* and static are never forced
        # away even if they repeat; the rule only applies to movement patterns.
        if pattern not in ("static", "focus_on_character", "focus_on_object"):
            counts[pattern] = counts.get(pattern, 0) + 1
            if counts[pattern] > _MAX_REPEAT:
                ladder = _ROLE_PATTERN_LADDERS.get(role)
                if ladder:
                    for candidate in ladder:
                        if candidate == pattern:
                            continue
                        if counts.get(candidate, 0) < counts[pattern]:
                            actions.append(
                                CameraDiversityAction(
                                    scene_index=index,
                                    before=pattern,
                                    after=candidate,
                                    reason=(
                                        f"exceeded repeat limit ({counts[pattern]}) "
                                        f"for {pattern}; selected {candidate} "
                                        f"for role '{role}'"
                                    ),
                                )
                                                        )
                        break
    return actions


def apply_camera_diversity(
    visual_description: dict[str, Any] | None,
    *,
    scene_index: int = 0,
    scene_role: str = "general",
    cast: list[str] | tuple[str, ...] | set[str] | None = None,
    previous_camera_patterns: tuple[str, ...] = (),
    camera_actions: tuple[CameraDiversityAction, ...] = (),
) -> CameraDiversityResult:
    """Apply V1.6-G camera diversity/safety for one scene (G1 + G4 + G3).

    * G4: sanitize a placeholder ``focus_target`` (e.g. ``"character"``/``""``)
      so it can never be misread downstream as a fake character target.
    * G1: apply any precomputed pattern-change action for this scene.
    * G3: record advisory metadata only (never mutates V1.6-D/F output).

    Pure / append-only on the description: returns a shallow-copied
    description with a new camera sub-dict when changes occur; otherwise
    returns the same description object unchanged.
    """
    if not VISUAL_CAMERA_DIVERSITY_ENABLED or not isinstance(visual_description, dict):
        camera = (
            visual_description.get("camera")
            if isinstance(visual_description, dict)
            else None
        )
        pattern = (
            str(camera.get("pattern", "") or "static")
            if isinstance(camera, dict)
            else "static"
        )
        focus = (
            str(camera.get("focus_target", "") or "")
            if isinstance(camera, dict)
            else ""
        )
        executed_changed = bool(
            isinstance(camera, dict)
            and bool(camera.get("executed_pattern"))
            and pattern != "static"
        )
        decision = CameraDiversityDecision(
            scene_index=scene_index,
            pattern=pattern,
            focus_target=focus,
            executed_changed=executed_changed,
            changed=False,
            skipped=True,
            reason="camera diversity disabled (flag OFF)",
        )
        return CameraDiversityResult(visual_description, decision)


    warnings: list[str] = []
    camera = visual_description.get("camera")
    cast_list = cast if cast is not None else ()

    # G4: sanitize a placeholder focus_target without touching the pattern.
    cleaned_camera = _safe_camera_spec(camera, cast_list) if camera else {}
    focus_target = str(cleaned_camera.get("focus_target", ""))
    pattern = str(cleaned_camera.get("pattern") or "static").strip().lower()
    executed_changed = bool(
        bool(cleaned_camera.get("focus_target")) and pattern not in ("static", "")
    )

    applied_action = None
    for action in camera_actions:
        if action.scene_index == scene_index:
            applied_action = action
            break

    if applied_action is not None and applied_action.after != pattern:
        cleaned_camera = dict(cleaned_camera)
        cleaned_camera["pattern"] = applied_action.after
        cleaned_camera["diversity_reason"] = applied_action.reason
        pattern = applied_action.after
        executed_changed = True

    # G1: inline diversity scoring when no precomputed action exists.
    # Uses the previous scenes' executed patterns to avoid repeating the
    # same non-static pattern more than _MAX_REPEAT times in a row.
    diverse_pattern = _pick_diverse_pattern(
        pattern, previous_camera_patterns, scene_role
    )
    if diverse_pattern != pattern:
        cleaned_camera = dict(cleaned_camera)
        cleaned_camera["pattern"] = diverse_pattern
        cleaned_camera["diversity_reason"] = (
            f"diversity: {pattern} repeated, switched to {diverse_pattern}"
        )
        pattern = diverse_pattern
        executed_changed = True

    # G3: advisory activity hint (observability only).
    _ = _activity_hint(scene_role, len(list(cast_list)))

    decision = CameraDiversityDecision(
        scene_index=scene_index,
        pattern=pattern,
        focus_target=focus_target,
        executed_changed=executed_changed,
        actions=(applied_action,) if applied_action else (),
        changed=bool(applied_action) or bool(cleaned_camera.get("diversity_reason")),
        skipped=not (bool(applied_action) or bool(cleaned_camera.get("diversity_reason"))),
        warnings=tuple(warnings),
        reason=(
            f"applied {pattern}"
            if applied_action
            else (
                cleaned_camera.get("diversity_reason", "no diversity action needed")
            )
        ),
    )

    # Append-only / non-mutating: build a new description dict referencing the
    # same values for unchanged keys, replacing only the camera sub-dict.
    result_description = dict(visual_description)
    result_description["camera"] = cleaned_camera
    result_description["camera_diversity"] = decision.to_dict()
    return CameraDiversityResult(result_description, decision)


def apply_camera_diversity_sequence(
    descriptions: list[dict[str, Any] | None],
    *,
    scene_roles: list[str | None] | None = None,
    casts: list[tuple[str, ...] | list[str] | None] | None = None,
) -> tuple[list[dict[str, Any] | None], CameraDiversityReport]:
    """Apply V1.6-G across a scene sequence with continuity.

    Computes each scene's camera pattern (read from
    ``visual_description["camera"]["pattern"]``), then deterministically scores
    and ranks alternative patterns to reduce repetition while respecting
    narrative role. When the flag is OFF the input description list is
    returned unchanged (same list / same objects) and the report is an
    all-skipped report with ``enabled=False``.
    """
    if not descriptions:
        return [], CameraDiversityReport(enabled=False, summary="no scenes")

    if not VISUAL_CAMERA_DIVERSITY_ENABLED:
        decisions = [
            CameraDiversityDecision(
                scene_index=index,
                pattern="static",
                focus_target="",
                executed_changed=False,
                changed=False,
                skipped=True,
                reason="camera diversity disabled (flag OFF)",
            )
            for index in range(len(descriptions))
        ]
        return descriptions, CameraDiversityReport(
            scenes=tuple(decisions),
            applied_count=0,
            skipped_count=len(decisions),
            warning_count=0,
            enabled=False,
            summary="disabled",
        )

    roles = scene_roles if scene_roles is not None else [None] * len(descriptions)
    cast_lists = casts if casts is not None else [() for _ in descriptions]

    # Snapshot existing camera specs (read-only on input).
    specs: list[dict[str, Any] | None] = []
    for desc in descriptions:
        if isinstance(desc, dict):
            cam = desc.get("camera")
            specs.append(cam if isinstance(cam, dict) else None)
        else:
            specs.append(None)

    actions = _sanitized_sequence_camera(specs, roles)

    results: list[dict[str, Any] | None] = []
    decisions: list[CameraDiversityDecision] = []
    for index, desc in enumerate(descriptions):
        if not isinstance(desc, dict):
            decisions.append(
                CameraDiversityDecision(
                    scene_index=index,
                    pattern="static",
                    focus_target="",
                    executed_changed=False,
                    skipped=True,
                    reason="non-dict visual description",
                )
            )
            results.append(desc)
            continue
        result = apply_camera_diversity(
            desc,
            scene_index=index,
            scene_role=roles[index] or "general",
            cast=cast_lists[index] if index < len(cast_lists) else None,
            camera_actions=tuple(actions),
        )
        results.append(result.visual_description)
        decisions.append(result.decision)

    applied = sum(1 for decision in decisions if decision.changed)
    skipped = sum(1 for decision in decisions if decision.skipped)
    warnings = sum(len(decision.warnings) for decision in decisions)
    return results, CameraDiversityReport(
        scenes=tuple(decisions),
        applied_count=applied,
        skipped_count=skipped,
        warning_count=warnings,
        enabled=True,
        summary=f"{applied}/{len(decisions)} scenes re-framed; {warnings} warning(s)",
    )