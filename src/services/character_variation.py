"""Character Staging & Pose Variation Layer (V1.6-B).

Deterministic, pure, standalone service that reduces *unnecessary* repetition
in character staging and pose presentation across scenes.

Root cause addressed: authored scenes commonly give characters only a name
and (sometimes) a position, so every character renders with the renderer
defaults -- ``pose="idle"``, ``scale=1.0`` -- producing visually identical
character presentation scene after scene.  Measured on the V1.5 validation
scenario: 6/6 characters idle, 6/6 default scale.

This layer varies character *intent* fields (pose, scale, position) only
where they were not explicitly authored, using the existing renderer
vocabulary (``SUPPORTED_POSES``) and the existing V1.2 presentation staging
(clamping, framing, object clearance) which runs afterwards and stays
authoritative.

This is a *read-only* layer with respect to scene intent: it never mutates
ScenePlan, VisualScene, V1.3 semantic results, V1.4 planner results, V1.5
application results, or V1.6-A decisions.  It returns a new character list;
the pipeline applies it to a shallow copy of the scene's VisualScene.

Precedence (highest to lowest):
    1. Explicit scene/character intent -- a character dict key that is
       present (``pose``/``scale``/``x``) is never overwritten.
    2. Existing V1.4 focus decision -- the attention/camera focus character
       keeps priority in anchor assignment and receives the primary scale.
    3. Existing scene constraints -- objects and already-staged characters
       deterministically block conflicting anchors.
    4. V1.6-B variation (role-driven pose, structural scale, hashed anchor).
    5. Existing renderer defaults.

Determinism: no ``random``, no timestamps, no UUIDs, no environment
hashing.  Anchors hash ``(character name, scene role)``; everything else is
rule-based.  Identical inputs always produce identical outputs.

Continuity: because anchors hash identity+role (not scene position), the
same character in the same scene role keeps the same staging across
consecutive scenes; a role change is the only thing that moves it.

Orientation/facing: the renderer has no facing concept (limb drawing is
symmetric or fixed), so orientation variation is intentionally NOT
attempted; adding it would require modifying the protected renderer.
"""

from __future__ import annotations

import zlib
from dataclasses import asdict, dataclass
from typing import Any

from src.services.scene_composition import SUPPORTED_POSES


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

VISUAL_CHARACTER_VARIATION_ENABLED = False


# ---------------------------------------------------------------------------
# Variation vocabulary
# ---------------------------------------------------------------------------

# Deterministic left/right staging anchors for characters whose position was
# not explicitly authored.  Narrow on purpose: V1.2 presentation staging
# (applied after this layer) clamps and re-frames positions anyway.
POSITION_ANCHORS: tuple[float, ...] = (0.3, 0.7)

# Scene-role -> pose mapping.  Values are restricted to SUPPORTED_POSES and
# mirror the semantic choices proven in examples/plan_visual_quality_v1.json
# (hook -> surprised, object_interaction -> point, explanation family ->
# talk).  Roles not listed keep the renderer default ("idle").
ROLE_POSES: dict[str, str] = {
    "hook": "surprised",
    "problem": "talk",
    "solution": "talk",
    "explanation": "talk",
    "comparison": "talk",
    "camera_focus": "talk",
    "object_interaction": "point",
    "cta": "wave",
}

# Scale assignments for multi-character scenes only: the focus (or first)
# character reads larger, supporting characters recede for a depth
# impression.  V1.2 staging multiplies staged scale by 1.25 afterwards.
# Single-character scenes keep the renderer default (no artificial change).
PRIMARY_SCALE = 1.1
SUPPORTING_SCALE = 0.85

# Minimum normalized distance between an assigned anchor and (a) any other
# character's staging x and (b) any object x before the anchor is rejected.
_CHAR_PROXIMITY = 0.12
_OBJECT_PROXIMITY = 0.08


def supported_variation_poses() -> frozenset[str]:
    """Return the poses this layer may assign (subset of SUPPORTED_POSES)."""
    return frozenset(ROLE_POSES.values())


# ---------------------------------------------------------------------------
# Data model (frozen / immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharacterVariationDecision:
    scene_index: int
    scene_role: str = "general"
    focus_character: str | None = None
    pose_variations: tuple[str, ...] = ()
    scale_variations: tuple[str, ...] = ()
    position_variations: tuple[str, ...] = ()
    pose_changed: bool = False
    scale_changed: bool = False
    position_changed: bool = False
    changed: bool = False
    skipped: bool = False
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _norm_name(name: Any) -> str:
    return str(name or "").strip().lower()


def _identity_digest(name: str, scene_role: str) -> int:
    """Stable, process-independent digest of (character identity, role)."""
    seed = f"v1.6-character:{name}:{scene_role}"
    return zlib.crc32(seed.encode("utf-8"))


def _anchor_candidates(name: str, scene_role: str) -> list[float]:
    """Anchor candidates for a character: hashed order first, rotation second."""
    start = _identity_digest(name, scene_role) % len(POSITION_ANCHORS)
    return [
        POSITION_ANCHORS[start],
        POSITION_ANCHORS[(start + 1) % len(POSITION_ANCHORS)],
    ]


def _anchor_conflicts(
    anchor: float,
    occupied_x: list[float],
    object_x: list[float],
) -> bool:
    """True when an anchor would crowd an already-staged character/object."""
    for ox in occupied_x:
        if abs(anchor - float(ox)) < _CHAR_PROXIMITY:
            return True
    for ox in object_x:
        if abs(anchor - float(ox)) < _OBJECT_PROXIMITY:
            return True
    return False


# ---------------------------------------------------------------------------
# Per-scene application
# ---------------------------------------------------------------------------


def apply_character_variation(
    characters: list[dict[str, Any]] | None,
    objects: list[dict[str, Any]] | None,
    *,
    scene_index: int = 0,
    total_scenes: int = 1,
    scene_role: str = "general",
    primary_focus: str = "scene",
    focus_target: str | None = None,
) -> tuple[list[dict[str, Any]], CharacterVariationDecision]:
    """Vary character staging intent that was not explicitly authored.

    Returns ``(new_characters, decision)``.  The input list and dicts are
    never mutated.  Only three intent fields may be added, and only when the
    corresponding key is absent from the character dict:

    - ``pose``   -- from the scene-role table (renderer-supported poses only).
    - ``scale``  -- primary/supporting differentiation, multi-character only.
    - ``x``      -- deterministic anchor hashed from (name, scene role).

    The strategy intentionally does not depend on ``scene_index`` (identity +
    role hashing gives continuity for free); the index is recorded for
    observability only.
    """
    role = str(scene_role or "general").strip().lower() or "general"
    char_list = [c for c in (characters or []) if isinstance(c, dict)]
    object_x = [
        float(o.get("x"))
        for o in (objects or [])
        if isinstance(o, dict) and o.get("x") is not None
    ]
    focus = _norm_name(focus_target)
    char_names = {_norm_name(c.get("name")) for c in char_list}
    if focus not in char_names:
        focus = ""

    if not VISUAL_CHARACTER_VARIATION_ENABLED:
        decision = CharacterVariationDecision(
            scene_index=int(scene_index),
            scene_role=role,
            focus_character=focus or None,
            skipped=True,
            reason="character variation disabled (flag OFF)",
        )
        return list(char_list), decision

    if not char_list:
        decision = CharacterVariationDecision(
            scene_index=int(scene_index),
            scene_role=role,
            skipped=True,
            reason="no characters to stage",
        )
        return [], decision

    warnings: list[str] = []
    pose_variations: list[str] = []
    scale_variations: list[str] = []
    position_variations: list[str] = []
    varied: list[dict[str, Any]] = []
    occupied_x: list[float] = []

    # The focus character (V1.4 attention/camera target, when it names a
    # character in this scene) is processed first: it claims its anchor and
    # receives the primary scale before supporting characters are staged.
    ordered = list(char_list)
    if focus:
        ordered.sort(
            key=lambda c: 0 if _norm_name(c.get("name")) == focus else 1
        )

    multi = len(ordered) > 1
    role_pose = ROLE_POSES.get(role)

    for position_idx, character in enumerate(ordered):
        staged = dict(character)
        name = _norm_name(staged.get("name"))
        is_first = position_idx == 0

        # --- Pose (only when not explicitly authored) ---
        if "pose" not in staged and role_pose is not None and role_pose in SUPPORTED_POSES:
            staged["pose"] = role_pose
            pose_variations.append(name)

        # --- Scale (only when not explicitly authored; multi-character only) ---
        if "scale" not in staged and multi:
            staged["scale"] = PRIMARY_SCALE if is_first else SUPPORTING_SCALE
            scale_variations.append(name)

        # --- Position (only when not explicitly authored) ---
        if "x" not in staged:
            anchor = None
            for candidate in _anchor_candidates(name, role):
                if _anchor_conflicts(candidate, occupied_x, object_x):
                    continue
                anchor = candidate
                break
            if anchor is not None:
                staged["x"] = anchor
                position_variations.append(name)
            else:
                warnings.append(f"no free anchor for character: {name}")

        occupied_x.append(float(staged.get("x", 0.5)))
        varied.append(staged)

    changed = bool(pose_variations or scale_variations or position_variations)
    parts: list[str] = []
    if pose_variations:
        parts.append(f"pose for {len(pose_variations)}")
    if scale_variations:
        parts.append(f"scale for {len(scale_variations)}")
    if position_variations:
        parts.append(f"position for {len(position_variations)}")
    reason = (
        "varied " + ", ".join(parts) if parts else "no variation applied (explicit intent or defaults kept)"
    )

    decision = CharacterVariationDecision(
        scene_index=int(scene_index),
        scene_role=role,
        focus_character=focus or None,
        pose_variations=tuple(pose_variations),
        scale_variations=tuple(scale_variations),
        position_variations=tuple(position_variations),
        pose_changed=bool(pose_variations),
        scale_changed=bool(scale_variations),
        position_changed=bool(position_variations),
        changed=changed,
        warnings=tuple(warnings),
        reason=reason,
    )
    return varied, decision