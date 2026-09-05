"""Scene Choreography Coordination Layer (V1.6-E).

Deterministic, pure, standalone staging layer that coordinates the existing
motion primitives, camera/attention decisions, scene cast changes, timing,
and transitions into coherent per-scene choreography without changing the
renderer or any planning layer.

Scope (what this layer does):

- Detects cast changes across adjacent scenes (``character``/``object`` names)
  from the previous and next scene casts.
- Schedules deterministic ``enter`` motions for newly introduced elements
  (respecting the element's authored position and the camera focus side).
- Schedules deterministic ``exit`` motions for departed elements **only when**
  the transition to the next scene is non-cut (``crossfade``/``fade``/slide
  family), so elements leave cleanly instead of freezing mid-frame.
- Schedules one short attention-aware ``scale`` emphasis on the V1.4-E
  attention / V1.4-D camera focus target when that target has no existing
  motion overlapping the emphasis window.
- Detects motion-window conflicts for every generated primitive (an existing
  motion on the same target/window suppresses the V1.6-E action with a
  warning).
- Maintains timeline bounds for every generated motion (``Motion.validate``
  against the scene duration).
- Applies transition-aware settling: with a non-cut transition, retained
  elements are kept static in the tail and any motion that would still be
  active at the tail is reported as an observable warning (never rewritten).
- Emits audit-friendly ``ChoreographyDecision`` (per scene) and
  ``ChoreographyReport`` (sequence) metadata.

Constraints (V1.6-E):

- Append-only: existing ``Motion`` objects are never mutated, re-timed, or
  re-ordered; only new ``Motion`` entries are appended at the end.
- Every generated motion carries ``label`` beginning with exactly ``v1.6-e:``.
- Nothing is emitted for targets already covered by an existing motion window.
- No ``random``, no UUIDs, no timestamps, no global mutable state.
- ``visual_description["camera"]`` is read-only (V1.6-D owns it).
- The feature flag defaults to OFF; when OFF the input motion list is returned
  unchanged and no choreography metadata is produced.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from src.models.content_package import Motion


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

VISUAL_CHOREOGRAPHY_ENABLED = False

# Required label prefix for every generated V1.6-E motion.
LABEL_PREFIX = "v1.6-e:"

# Element kinds this layer choreographs. Text/scene/layer are explicitly out
# of scope (no scene-graph changes), matching the existing renderer vocabulary.
_CHOREO_KINDS = frozenset({"character", "object"})

# --- Timing window constants (fractions of scene duration) ------------------
_LEAD_FRACTION = 0.22          # entrance completes within the lead-in band
_LEAD_MAX_SECONDS = 2.0
_LEAD_MIN_SECONDS = 0.4
_EMPH_START_FRACTION = 0.50    # emphasis window starts at half the scene
_EMPH_MIN_SECONDS = 0.35
_EMPH_MAX_SECONDS = 1.0
_EMPH_SCALE_TO = 1.10          # short, bounded emphasis scale
_TAIL_FRACTION = 0.20          # non-cut transition tail band
_TAIL_MAX_SECONDS = 1.6
_MAX_SCENE_SHARE = 0.30         # no generated primitive dominates the scene
_MIN_MOTION_SECONDS = 0.20     # below this, skip the short primitive entirely
_EPS = 1e-6

_OFFSCREEN_MARGIN = 0.15
# ---------------------------------------------------------------------------
# Data model (frozen / immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChoreographyAction:
    """One deterministic choreography decision for a scene element."""

    kind: str                 # enter | exit | emphasis | settle
    target: str               # character | object
    target_id: str
    window_start: float
    window_end: float
    direction: str = ""
    motion_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _jsonify(asdict(self))


@dataclass(frozen=True)
class ChoreographyDecision:
    """What the V1.6-E choreography layer decided for one scene."""

    scene_index: int
    introduced: tuple[str, ...] = ()
    departed: tuple[str, ...] = ()
    actions: tuple[ChoreographyAction, ...] = ()
    emphasis_target: str | None = None
    transition_non_cut: bool = False
    transition_safe: bool = True
    changed: bool = False
    skipped: bool = False
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _jsonify(asdict(self))


@dataclass(frozen=True)
class ChoreographyResult:
    """The per-scene output: existing motions (unchanged) + appended motions."""

    motions: tuple[Motion, ...] = ()
    decision: ChoreographyDecision = field(
        default_factory=lambda: ChoreographyDecision(scene_index=0)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "motions": [motion.to_dict() for motion in self.motions],
            "decision": self.decision.to_dict(),
        }


@dataclass(frozen=True)
class ChoreographyReport:
    """Sequence-level choreography application report."""

    decisions: tuple[ChoreographyDecision, ...] = ()
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


def _jsonify(value: Any) -> Any:
    """Convert tuples to lists recursively so metadata is JSON-native."""
    if isinstance(value, tuple):
        return [_jsonify(item) for item in value]
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    return value


def _normalize_name(value: Any) -> str:
    """Normalize an element name for deterministic comparison."""
    return str(value or "").strip().lower()


def _clamp(value: Any, minimum: float, maximum: float) -> float:
    """Deterministic bounded clamp that also neutralizes NaN/infinite input."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return minimum
    if math.isnan(number):
        return minimum
    if math.isinf(number):
        return maximum if number > 0 else minimum
    return max(minimum, min(maximum, number))


def _safe_duration(duration: Any) -> float:
    """Coerce a scene duration to a finite, positive float (0.0 when invalid)."""
    try:
        value = float(duration)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(value) or math.isinf(value) or value <= 0.0:
        return 0.0
    return value


def _member_name(member: Any) -> str:
    """Read a name from a dict or object member."""
    if isinstance(member, dict):
        return _normalize_name(member.get("name"))
    return _normalize_name(getattr(member, "name", ""))


def _member_x(member: Any) -> float | None:
    """Read a normalized x coordinate from a dict or object member."""
    if isinstance(member, dict):
        value = member.get("x")
    else:
        value = getattr(member, "x", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _member_y(member: Any) -> float:
    """Read a normalized y coordinate from a dict or object member."""
    if isinstance(member, dict):
        value = member.get("y")
    else:
        value = getattr(member, "y", None)
    if value is None:
        return 0.75
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.75


def collect_cast_names(visual: Any) -> frozenset[tuple[str, str]]:
    """Collect the cast of a scene as a set of (kind, name) pairs.

    ``visual`` may be a ``visual_description`` dict (with ``characters`` and
    ``objects`` list keys) or any object exposing ``characters``/``objects``
    members (e.g. ``VisualScene``). Names are normalized to lowercase.
    """
    if visual is None:
        return frozenset()
    if isinstance(visual, dict):
        characters = visual.get("characters") or ()
        objects = visual.get("objects") or ()
    else:
        characters = getattr(visual, "characters", None) or ()
        objects = getattr(visual, "objects", None) or ()

    cast: list[tuple[str, str]] = []
    for member in characters:
        name = _member_name(member)
        if name:
            cast.append(("character", name))
    for member in objects:
        name = _member_name(member)
        if name:
            cast.append(("object", name))
    return frozenset(cast)


def _find_member(
    visual: dict[str, Any], kind: str, name: str
) -> dict[str, Any] | None:
    """Return the (shallow-copied) staged member dict for (kind, name)."""
    key = "characters" if kind == "character" else "objects"
    for member in visual.get(key) or ():
        if _member_name(member) == name:
            if isinstance(member, dict):
                return dict(member)
            return {
                "name": getattr(member, "name", name),
                "x": getattr(member, "x", None),
                "y": getattr(member, "y", None),
            }
    return None


def _real_motions(motions: Any) -> tuple[Motion, ...]:
    """Filter to actual Motion instances, preserving order."""
    if motions is None:
        return ()
    return tuple(motion for motion in motions if isinstance(motion, Motion))


def _motion_slot(motion: Motion) -> tuple[str, str] | None:
    """Return the (kind, name) a motion targets, if it is a cast member."""
    if motion.target in _CHOREO_KINDS and str(motion.target_id or "").strip():
        return motion.target, _normalize_name(motion.target_id)
    return None


def _window_overlaps(
    start: float, end: float, other_start: float, other_end: float
) -> bool:
    """True when [start, end] and [other_start, other_end] overlap."""
    return max(0.0, min(end, other_end) - max(start, other_start)) > _EPS


def _has_conflict(
    motions: tuple[Motion, ...], kind: str, name: str, start: float, end: float
) -> bool:
    """True when any existing motion targets (kind, name) in the window."""
    for motion in motions:
        slot = _motion_slot(motion)
        if slot == (kind, name) and _window_overlaps(
            start, end, float(motion.start_time), float(motion.start_time) + float(motion.duration)
        ):
            return True
    return False


def _is_non_cut_transition(transition: Any) -> bool:
    """True when the transition to the next scene is not a hard cut."""
    if transition is None:
        return False
    if isinstance(transition, dict):
        transition_type = transition.get("type")
    else:
        transition_type = getattr(transition, "type", None)
    return str(transition_type or "").strip().lower() not in ("", "cut", "none")


def _attention_target(planning_metadata: dict[str, Any] | None) -> tuple[str, str] | None:
    """Resolve the V1.4-E attention primary target (kind, name) when present."""
    if not isinstance(planning_metadata, dict):
        return None
    attention = planning_metadata.get("attention")
    if not isinstance(attention, dict):
        return None
    kind = str(attention.get("target_kind") or "").strip().lower()
    name = _normalize_name(attention.get("primary_target"))
    if kind in _CHOREO_KINDS and name and name != "scene":
        return kind, name
    return None


def _camera_focus_target(
    planning_metadata: dict[str, Any] | None, camera: dict[str, Any] | None
) -> tuple[str, str] | None:
    """Resolve the V1.4-D camera focus target (kind, name) when present."""
    if isinstance(camera, dict):
        pattern = str(camera.get("pattern") or "").strip().lower()
        focus = _normalize_name(camera.get("focus_target"))
        if pattern in ("focus_on_character", "focus_on_object") and focus:
            kind = "character" if pattern == "focus_on_character" else "object"
            return kind, focus
    if isinstance(planning_metadata, dict):
        camera_meta = planning_metadata.get("camera")
        if isinstance(camera_meta, dict):
            pattern = str(camera_meta.get("recommended_pattern") or "").strip().lower()
            focus = _normalize_name(camera_meta.get("focus_target"))
            if pattern in ("focus_on_character", "focus_on_object") and focus:
                kind = "character" if pattern == "focus_on_character" else "object"
                return kind, focus
    return None


def _entrance_direction(
    visual: dict[str, Any], kind: str, name: str, camera: dict[str, Any] | None
) -> str:
    """Pick the deterministic side an introduced element enters from.

    Priority: the element's authored x (left of center -> enter from left),
    then the camera-focus side (enter opposite the focus so the element does
    not cross the attention zone), then a safe ``left`` default.
    """
    member = _find_member(visual, kind, name)
    if member is not None:
        x = _member_x(member)
        if x is not None:
            return "left" if float(x) < 0.5 else "right"

    focus = str((camera or {}).get("focus_target") or "").strip().lower()
    if focus:
        for candidate_kind in ("character", "object"):
            focus_member = _find_member(visual, candidate_kind, focus)
            if focus_member is not None:
                fx = _member_x(focus_member)
                if fx is not None:
                    return "right" if float(fx) < 0.5 else "left"
    return "left"


def _exit_direction(visual: dict[str, Any], kind: str, name: str) -> str:
    """Pick the deterministic side a departing element exits toward."""
    member = _find_member(visual, kind, name)
    if member is not None:
        x = _member_x(member)
        if x is not None:
            return "left" if float(x) < 0.5 else "right"
    return "left"


def _offscreen_position(
    direction: str, x: float, y: float
) -> dict[str, float]:
    """Mirror the renderer's off-screen margins for enter/exit endpoints."""
    name = direction.strip().lower()
    if name == "right":
        return {"x": 1.0 + _OFFSCREEN_MARGIN, "y": y}
    if name == "top":
        return {"x": x, "y": -_OFFSCREEN_MARGIN}
    if name == "bottom":
        return {"x": x, "y": 1.0 + _OFFSCREEN_MARGIN}
    return {"x": -_OFFSCREEN_MARGIN, "y": y}


def _lead_window(duration: float) -> tuple[float, float]:
    """Lead-in band where entrances complete (fractions bounded).

    Returns an empty band when the scene is too short for a meaningful
    entrance: no generated primitive may occupy more than ``_MAX_SCENE_SHARE``
    of the scene timeline.
    """
    end = min(duration, max(_LEAD_MIN_SECONDS, duration * _LEAD_FRACTION))
    if end < _MIN_MOTION_SECONDS or end > duration * _MAX_SCENE_SHARE + _EPS:
        return 0.0, 0.0
    return 0.0, round(end, 3)


def _emphasis_window(duration: float) -> tuple[float, float]:
    """Attention emphasis band (starts mid-scene, bounded width)."""
    start = round(min(duration, max(0.0, duration * _EMPH_START_FRACTION)), 3)
    width = _clamp(duration * 0.25, _EMPH_MIN_SECONDS, _EMPH_MAX_SECONDS)
    end = round(min(duration, start + width), 3)
    span = end - start
    if span < _MIN_MOTION_SECONDS or span > duration * _MAX_SCENE_SHARE + _EPS:
        return 0.0, 0.0
    return start, end


def _tail_window(duration: float) -> tuple[float, float] | None:
    """Tail band before a non-cut transition; None when too short to matter."""
    tail = min(duration * _TAIL_FRACTION, _TAIL_MAX_SECONDS)
    start = round(max(0.0, duration - tail), 3)
    if duration - start < _MIN_MOTION_SECONDS:
        return None
    return start, round(duration, 3)


# ---------------------------------------------------------------------------
# Motion builders
# ---------------------------------------------------------------------------


def _build_enter_motion(
    visual: dict[str, Any],
    kind: str,
    name: str,
    direction: str,
    lead_end: float,
) -> tuple[Motion, str]:
    """Build an enter motion that ends at the element's authored position."""
    member = _find_member(visual, kind, name)
    to_x = float(member.get("x", 0.5)) if member is not None else 0.5
    to_y = _member_y(member) if member is not None else 0.75
    to = {"x": to_x, "y": to_y}
    from_pos = _offscreen_position(direction, to_x, to_y)
    motion = Motion(
        type="enter",
        target=kind,
        target_id=name,
        start_time=0.0,
        duration=lead_end,
        easing="ease_in_out",
        parameters={"from": from_pos, "to": to, "direction": direction},
        label=f"{LABEL_PREFIX}enter",
    )
    return motion, direction


def _build_exit_motion(
    visual: dict[str, Any],
    kind: str,
    name: str,
    direction: str,
    start_time: float,
    duration: float,
) -> tuple[Motion, str]:
    """Build an exit motion that leaves from the element's authored position."""
    member = _find_member(visual, kind, name)
    from_x = float(member.get("x", 0.5)) if member is not None else 0.5
    from_y = _member_y(member) if member is not None else 0.75
    from_pos = {"x": from_x, "y": from_y}
    to_pos = _offscreen_position(direction, from_x, from_y)
    motion = Motion(
        type="exit",
        target=kind,
        target_id=name,
        start_time=start_time,
        duration=duration,
        easing="ease_in_out",
        parameters={"from": from_pos, "to": to_pos, "direction": direction},
        label=f"{LABEL_PREFIX}exit",
    )
    return motion, direction


def _build_emphasis_motion(
    kind: str, name: str, start_time: float, duration: float
) -> Motion:
    """Build a single short emphasis scale on a cast member."""
    return Motion(
        type="scale",
        target=kind,
        target_id=name,
        start_time=start_time,
        duration=duration,
        easing="ease_in_out",
        parameters={"from": 1.0, "to": _EMPH_SCALE_TO},
        label=f"{LABEL_PREFIX}emphasis",
    )


# ---------------------------------------------------------------------------
# Per-scene choreography application
# ---------------------------------------------------------------------------


def apply_scene_choreography(
    motions: list[Motion] | None = None,
    *,
    visual_description: dict[str, Any] | None = None,
    cast: frozenset[tuple[str, str]] | None = None,
    previous_cast: frozenset[tuple[str, str]] | None = None,
    next_cast: frozenset[tuple[str, str]] | None = None,
    scene_index: int = 0,
    scene_role: str = "general",
    duration: float = 1.0,
    planning_metadata: dict[str, Any] | None = None,
    camera: dict[str, Any] | None = None,
    transition_to_next: Any | None = None,
) -> ChoreographyResult:
    """Coordinate a single scene into deterministic, append-only choreography.

    Existing ``Motion`` objects are never mutated or re-ordered; the returned
    ``ChoreographyResult.motions`` is (existing motions in order) + (new V1.6-E
    motions in a fixed order: enters, exits, emphasis). Every generated motion
    has a ``label`` that starts with ``v1.6-e:`` and validates against the
    scene duration.

    Args:
        motions: The scene's existing motions (explicit + V1.3 + V1.6-C).
        visual_description: Staged visual scene dict (element positions/cast).
        cast: Current scene cast; defaults to ``collect_cast_names`` on the
            visual description.
        previous_cast: Cast of the previous scene (for entrance detection).
        next_cast: Cast of the next scene (for departure detection).
        scene_index: Zero-based scene index.
        scene_role: Narrative scene role (informational only).
        duration: Scene duration in seconds.
        planning_metadata: V1.4 ``visual_planning`` metadata dict, when present.
        camera: Executed V1.6-D camera spec dict (read-only).
        transition_to_next: The scene's transition to the next scene.

    Returns:
        A ``ChoreographyResult``. When the feature flag is OFF the result
        carries the original motions unchanged and ``decision.skipped=True``.
    """
    existing = _real_motions(motions)
    scene_idx = int(scene_index)
    role = str(scene_role or "general").strip().lower() or "general"
    scene_duration = _safe_duration(duration)

    if not VISUAL_CHOREOGRAPHY_ENABLED:
        decision = ChoreographyDecision(
            scene_index=scene_idx,
            skipped=True,
            reason="scene choreography disabled (flag OFF)",
        )
        return ChoreographyResult(existing, decision)

    desc = visual_description or {}
    if not isinstance(desc, dict):
        desc = {}
    if not desc:
        decision = ChoreographyDecision(
            scene_index=scene_idx,
            skipped=True,
            reason="no structured visual scene to choreograph",
        )
        return ChoreographyResult(existing, decision)

    current_cast = cast if cast is not None else collect_cast_names(desc)
    if not current_cast:
        decision = ChoreographyDecision(
            scene_index=scene_idx,
            skipped=True,
            reason="no choreographable cast members",
        )
        return ChoreographyResult(existing, decision)

    if scene_duration <= 0.0:
        decision = ChoreographyDecision(
            scene_index=scene_idx,
            skipped=True,
            reason="invalid or non-positive scene duration",
        )
        return ChoreographyResult(existing, decision)

    prev_known = previous_cast is not None
    next_known = next_cast is not None
    # Unknown continuity context (None) is treated conservatively: without
    # reliable previous/next cast information V1.6-E invents no entrances or
    # exits. Sequence-level callers decide the cold open explicitly by
    # passing an empty frozenset for the first scene.
    prev_cast = previous_cast if prev_known else frozenset()
    nextc = next_cast if next_known else frozenset()

    warnings: list[str] = []
    actions: list[ChoreographyAction] = []
    appended: list[Motion] = []
    all_motions = list(existing)
    # --- Entrances (newly introduced elements, when they have no conflict) ---
    introduced = sorted(current_cast - prev_cast) if prev_known else []
    lead_start, lead_end = _lead_window(scene_duration)
    for kind, name in introduced:
        if kind not in _CHOREO_KINDS or lead_end <= 0.0:
            continue
        if _has_conflict(tuple(all_motions), kind, name, lead_start, lead_end):
            warnings.append(f"enter_conflict:{kind}:{name}")
            continue
        direction = _entrance_direction(desc, kind, name, camera)
        try:
            motion, direction = _build_enter_motion(
                desc, kind, name, direction, lead_end
            )
            motion.validate(scene_duration)
        except ValueError:
            warnings.append(f"enter_invalid:{kind}:{name}")
            continue
        appended.append(motion)
        all_motions.append(motion)
        actions.append(
            ChoreographyAction(
                kind="enter",
                target=kind,
                target_id=name,
                window_start=round(lead_start, 3),
                window_end=round(lead_end, 3),
                direction=direction,
                motion_type="enter",
            )
        )

    # --- Exits (departed elements under a non-cut transition) ----------------
    departed = sorted(current_cast - nextc) if next_known else []
    non_cut = _is_non_cut_transition(transition_to_next)
    tail = _tail_window(scene_duration)
    for kind, name in departed:
        if kind not in _CHOREO_KINDS or not non_cut or tail is None:
            continue
        tail_start, tail_end = tail
        if _has_conflict(tuple(all_motions), kind, name, tail_start, tail_end):
            warnings.append(f"exit_conflict:{kind}:{name}")
            continue
        direction = _exit_direction(desc, kind, name)
        try:
            motion, direction = _build_exit_motion(
                desc, kind, name, direction, tail_start, round(tail_end - tail_start, 3)
            )
            motion.validate(scene_duration)
        except ValueError:
            warnings.append(f"exit_invalid:{kind}:{name}")
            continue
        appended.append(motion)
        all_motions.append(motion)
        actions.append(
            ChoreographyAction(
                kind="exit",
                target=kind,
                target_id=name,
                window_start=round(tail_start, 3),
                window_end=round(tail_end, 3),
                direction=direction,
                motion_type="exit",
            )
        )

    # --- Attention-aware emphasis (one short scale, when the window is free) -
    emphasis_key: str | None = None
    emph_start, emph_end = _emphasis_window(scene_duration)
    if emph_end - emph_start >= _MIN_MOTION_SECONDS:
        emphasis_target = _attention_target(planning_metadata) or _camera_focus_target(
            planning_metadata, camera
        )
        if emphasis_target is not None:
            emphasis_key = f"{emphasis_target[0]}:{emphasis_target[1]}"
            if emphasis_target not in current_cast:
                warnings.append(f"emphasis_target_not_in_cast:{emphasis_key}")
            elif _has_conflict(
                tuple(all_motions), emphasis_target[0], emphasis_target[1], emph_start, emph_end
            ):
                warnings.append(f"emphasis_conflict:{emphasis_key}")
            else:
                motion = _build_emphasis_motion(
                    emphasis_target[0],
                    emphasis_target[1],
                    emph_start,
                    round(emph_end - emph_start, 3),
                )
                try:
                    motion.validate(scene_duration)
                except ValueError:
                    warnings.append(f"emphasis_invalid:{emphasis_key}")
                else:
                    appended.append(motion)
                    all_motions.append(motion)
                    actions.append(
                        ChoreographyAction(
                            kind="emphasis",
                            target=emphasis_target[0],
                            target_id=emphasis_target[1],
                            window_start=emph_start,
                            window_end=emph_end,
                            motion_type="scale",
                        )
                    )

    # --- Transition-aware settling (observability only; never rewrites) ------
    # Under a non-cut transition retained elements should be static in the
    # tail; any motion still active there is reported (existing motions are
    # never rewritten by V1.6-E).
    transition_safe = True
    if non_cut and tail is not None:
        tail_start = tail[0]
        for kind, name in sorted(current_cast & nextc):
            for motion in all_motions:
                if _motion_slot(motion) != (kind, name):
                    continue
                motion_end = float(motion.start_time) + float(motion.duration)
                if motion_end > tail_start + _EPS:
                    warnings.append(f"unsettled_tail_motion:{kind}:{name}")
                    transition_safe = False
                    break

    decision = ChoreographyDecision(
        scene_index=scene_idx,
        introduced=tuple(f"{kind}:{name}" for kind, name in introduced),
        departed=tuple(f"{kind}:{name}" for kind, name in departed),
        actions=tuple(actions),
        emphasis_target=emphasis_key,
        transition_non_cut=bool(non_cut),
        transition_safe=transition_safe,
        changed=bool(appended),
        skipped=not appended,
        warnings=tuple(warnings),
        reason="choreography applied" if appended else "no unoccupied choreography windows",
    )
    return ChoreographyResult(tuple(all_motions), decision)


# ---------------------------------------------------------------------------
# Sequence application (continuity threading)
# ---------------------------------------------------------------------------


def build_choreography_report(
    decisions: list[ChoreographyDecision] | tuple[ChoreographyDecision, ...],
    *,
    enabled: bool = True,
) -> ChoreographyReport:
    """Aggregate per-scene decisions into the sequence-level report."""
    decision_tuple = tuple(decisions)
    applied = sum(1 for decision in decision_tuple if decision.changed)
    skipped = sum(1 for decision in decision_tuple if not decision.changed)
    warning_count = sum(len(decision.warnings) for decision in decision_tuple)
    summary = (
        f"{applied}/{len(decision_tuple)} scenes choreographed; "
        f"{warning_count} warning(s)"
    )
    return ChoreographyReport(
        decisions=decision_tuple,
        applied_count=applied,
        skipped_count=skipped,
        warning_count=warning_count,
        enabled=enabled,
        summary=summary,
    )


def apply_scene_choreography_sequence(
    motion_lists: list[list[Motion]] | None,
    visual_descriptions: list[dict[str, Any] | None],
    *,
    scene_roles: list[str] | None = None,
    durations: list[float] | None = None,
    planning_metadatas: list[dict[str, Any] | None] | None = None,
    cameras: list[dict[str, Any] | None] | None = None,
    transitions_to_next: list[Any] | None = None,
    casts: list[frozenset[tuple[str, str]]] | None = None,
) -> tuple[list[list[Motion]], ChoreographyReport]:
    """Apply V1.6-E across a scene sequence with continuity threading.

    Threads ``previous_cast`` (scene i-1 cast) and ``previous_camera`` (the
    camera context available to scene i-1) into each scene so entrances,
    exits, and entrance sides stay deterministic across the sequence. When
    the flag is OFF the input motion lists are returned unchanged (same list
    objects) and the report is an all-skipped report with ``enabled=False``.
    """
    if motion_lists is None:
        motion_lists = []
    if visual_descriptions is None:
        visual_descriptions = []
    count = min(len(motion_lists), len(visual_descriptions))
    length_mismatch = len(motion_lists) != len(visual_descriptions)

    if not VISUAL_CHOREOGRAPHY_ENABLED:
        decisions = [
            ChoreographyDecision(
                scene_index=index,
                skipped=True,
                reason="scene choreography disabled (flag OFF)",
            )
            for index in range(count)
        ]
        return motion_lists, build_choreography_report(decisions, enabled=False)

    if length_mismatch:
        decisions = [
            ChoreographyDecision(
                scene_index=index,
                skipped=True,
                reason="motion/scene list length mismatch",
            )
            for index in range(count)
        ]
        return motion_lists, build_choreography_report(decisions, enabled=True)

    result_lists: list[list[Motion]] = []
    decisions: list[ChoreographyDecision] = []
    previous_cast: frozenset[tuple[str, str]] | None = None
    previous_camera: dict[str, Any] | None = None

    for index in range(count):
        scene_camera: dict[str, Any] | None = None
        if cameras is not None and index < len(cameras):
            scene_camera = cameras[index]
        if scene_camera is None:
            scene_camera = previous_camera

        role: str | None = None
        if scene_roles is not None and index < len(scene_roles):
            role = scene_roles[index]
        duration: float | None = None
        if durations is not None and index < len(durations):
            duration = durations[index]
        planning: dict[str, Any] | None = None
        if planning_metadatas is not None and index < len(planning_metadatas):
            planning = planning_metadatas[index]
        transition: Any = None
        if transitions_to_next is not None and index < len(transitions_to_next):
            transition = transitions_to_next[index]

        scene_cast: frozenset[tuple[str, str]] | None = None
        if casts is not None and index < len(casts):
            scene_cast = casts[index]
        next_cast: frozenset[tuple[str, str]] | None = None
        if casts is not None and index + 1 < len(casts):
            next_cast = casts[index + 1]
        elif index + 1 < len(visual_descriptions):
            next_desc = visual_descriptions[index + 1]
            if isinstance(next_desc, dict):
                next_cast = collect_cast_names(next_desc)

        result = apply_scene_choreography(
            motion_lists[index],
            visual_description=visual_descriptions[index],
            cast=scene_cast,
            # The sequence knows the video starts here: an empty previous
            # cast for scene 0 is a deliberate cold open (characters enter).
            previous_cast=previous_cast if previous_cast is not None else frozenset(),
            next_cast=next_cast,
            scene_index=index,
            scene_role=role if role is not None else "general",
            duration=duration if duration is not None else 1.0,
            planning_metadata=planning,
            camera=scene_camera,
            transition_to_next=transition,
        )
        result_lists.append(list(result.motions))
        decisions.append(result.decision)

        if scene_cast is not None:
            previous_cast = scene_cast
        else:
            current_desc = visual_descriptions[index]
            previous_cast = (
                collect_cast_names(current_desc)
                if isinstance(current_desc, dict)
                else frozenset()
            )
        if scene_camera is not None:
            previous_camera = scene_camera

    return result_lists, build_choreography_report(decisions, enabled=True)