"""Background Environment Variation Layer (V1.6-A).

Deterministic, pure, standalone service that fills *empty* scene environment
descriptions with varied, renderer-supported backdrops so that consecutive
scenes stop falling back to the identical outdoor default backdrop.

Root cause addressed: when ``VisualScene.environment`` is empty, the renderer
draws the same sun/sky/grass outdoor backdrop in every scene, making long
videos visually repetitive. This layer assigns each scene a deterministic
environment type and palette from the existing ``SUPPORTED_ENVIRONMENTS``
vocabulary and guarantees that adjacent scenes never share a backdrop.

This is a *read-only* layer with respect to scene intent: it never mutates
ScenePlan, VisualScene, V1.3 semantic results, or V1.4 planner results.  It
produces a new/modified staging dict (``visual_description``) and an immutable
decision report.

Precedence (highest to lowest):
    1. Explicit scene intent -- a non-empty ``environment`` dict is never
       overwritten (the scene is skipped with an observability warning).
    2. Deterministic variation assignment (this layer).

The layer is feature-flagged (``VISUAL_BACKGROUND_VARIATION_ENABLED``) and is
independent of the V1.3 semantic pipeline and the V1.4/V1.5 planning stack:
it only requires a structured ``visual_description`` with an empty (or
missing) environment dict.
"""

from __future__ import annotations

import zlib
from dataclasses import asdict, dataclass, field
from typing import Any

from src.services.scene_composition import SUPPORTED_ENVIRONMENTS


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

VISUAL_BACKGROUND_VARIATION_ENABLED = False


# ---------------------------------------------------------------------------
# Variation vocabulary (subset of SUPPORTED_ENVIRONMENTS)
# ---------------------------------------------------------------------------

# Fixed rotation of backdrop candidates. "default" (the outdoor sun/sky/grass
# fallback) is intentionally excluded: assigning it would reproduce the very
# repetition this layer exists to remove. Each candidate has distinct decor
# in the renderer (board, window, info dots, walls) and/or palette.
VARIATION_CANDIDATES: tuple[str, ...] = (
    "study_desk",
    "abstract_info_space",
    "classroom",
    "workspace",
    "bedroom",
    "office",
)

# Two palettes per candidate type. Primary values come from the proven
# examples/plan_visual_quality_v1.json plans; variants shift hue/ground line
# so the same type recurring later in a video still looks different.
ENVIRONMENT_PALETTES: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "study_desk": (
        {"background_color": [232, 221, 202], "ground_color": [122, 94, 66], "ground_y": 0.78, "accent_color": [255, 214, 120]},
        {"background_color": [220, 232, 235], "ground_color": [110, 80, 60], "ground_y": 0.80, "accent_color": [255, 220, 120]},
    ),
    "abstract_info_space": (
        {"background_color": [26, 32, 48], "ground_color": [18, 22, 34], "ground_y": 0.80, "accent_color": [130, 190, 255]},
        {"background_color": [24, 30, 44], "ground_color": [18, 22, 34], "ground_y": 0.82, "accent_color": [255, 170, 120]},
    ),
    "classroom": (
        {"background_color": [210, 220, 214], "ground_color": [90, 100, 92], "ground_y": 0.78, "accent_color": [245, 245, 230]},
        {"background_color": [214, 224, 226], "ground_color": [96, 108, 104], "ground_y": 0.80, "accent_color": [255, 236, 190]},
    ),
    "workspace": (
        {"background_color": [42, 55, 62], "ground_color": [30, 36, 40], "ground_y": 0.82, "accent_color": [120, 220, 190]},
        {"background_color": [48, 60, 70], "ground_color": [34, 40, 46], "ground_y": 0.84, "accent_color": [140, 200, 255]},
    ),
    "bedroom": (
        {"background_color": [205, 215, 230], "ground_color": [120, 100, 80], "ground_y": 0.80, "accent_color": [255, 224, 178]},
        {"background_color": [214, 206, 228], "ground_color": [110, 92, 76], "ground_y": 0.78, "accent_color": [200, 220, 255]},
    ),
    "office": (
        {"background_color": [222, 226, 230], "ground_color": [100, 96, 88], "ground_y": 0.79, "accent_color": [180, 214, 255]},
        {"background_color": [210, 218, 226], "ground_color": [92, 90, 84], "ground_y": 0.81, "accent_color": [255, 210, 150]},
    ),
}


# ---------------------------------------------------------------------------
# Data model (frozen / immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackgroundVariationDecision:
    scene_index: int
    assigned_type: str | None = None
    palette_variant: int | None = None
    previous_type: str | None = None
    filled: bool = False
    skipped: bool = False
    changed: bool = False
    warnings: tuple[str, ...] = ()
    original_environment: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackgroundVariationReport:
    decisions: tuple[BackgroundVariationDecision, ...] = ()
    applied_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0
    enabled: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [d.to_dict() for d in self.decisions],
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "warning_count": self.warning_count,
            "enabled": self.enabled,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _seed_digest(scene_index: int, total_scenes: int, domain: str) -> int:
    """Stable, process-independent digest for a scene position."""
    seed = f"v1.6-background:{domain}:{int(scene_index)}:{int(total_scenes)}"
    return zlib.crc32(seed.encode("utf-8"))


def resolve_environment_type(scene_index: int, total_scenes: int) -> str:
    """Deterministically resolve the backdrop type for a scene position.

    The base candidate is selected by a stable digest of
    (scene_index, total_scenes); when the base equals the previous scene's
    assignment, the next candidate in the fixed rotation order is used, so
    adjacent scenes never share the same backdrop. Pure function: identical
    inputs always produce identical outputs.
    """
    previous = ""
    chosen = VARIATION_CANDIDATES[0]
    for position in range(0, max(int(scene_index), 0) + 1):
        base = VARIATION_CANDIDATES[
            _seed_digest(position, total_scenes, "type") % len(VARIATION_CANDIDATES)
        ]
        if position > 0 and base == previous:
            base = VARIATION_CANDIDATES[
                (VARIATION_CANDIDATES.index(base) + 1) % len(VARIATION_CANDIDATES)
            ]
        previous = base
        chosen = base
    return chosen


def resolve_environment_palette(
    scene_index: int, total_scenes: int, environment_type: str
) -> tuple[dict[str, Any], int]:
    """Deterministically pick a palette variant for the assigned type."""
    variants = ENVIRONMENT_PALETTES.get(
        environment_type
    ) or ENVIRONMENT_PALETTES[VARIATION_CANDIDATES[0]]
    variant = _seed_digest(scene_index, total_scenes, "palette") % len(variants)
    return dict(variants[variant]), variant


def build_environment(scene_index: int, total_scenes: int) -> dict[str, Any]:
    """Build a complete, renderer-safe environment dict for a scene position.

    The emitted keys are a subset of ``EnvironmentSpec`` fields, so
    ``SceneComposition.from_visual_description`` parses the result unchanged.
    """
    env_type = resolve_environment_type(scene_index, total_scenes)
    palette, _variant = resolve_environment_palette(scene_index, total_scenes, env_type)
    environment: dict[str, Any] = {"type": env_type}
    environment.update(palette)
    return environment


# ---------------------------------------------------------------------------
# Per-scene application
# ---------------------------------------------------------------------------


def apply_background_variation(
    visual_description: dict[str, Any],
    scene_index: int = 0,
    total_scenes: int = 1,
) -> tuple[dict[str, Any], BackgroundVariationDecision]:
    """Fill an empty scene environment with a deterministic varied backdrop.

    Returns ``(new_visual_description, decision)``. The input dict is never
    mutated. When the flag is OFF or the scene carries explicit environment
    intent (non-empty environment dict), the description is returned
    unchanged and the decision records the skip.
    """
    scene_index = max(int(scene_index), 0)
    total_scenes = max(int(total_scenes), scene_index + 1)
    original_environment = dict(visual_description.get("environment") or {})

    if not VISUAL_BACKGROUND_VARIATION_ENABLED:
        decision = BackgroundVariationDecision(
            scene_index=scene_index,
            skipped=True,
            original_environment=original_environment,
            reason="background variation disabled (flag OFF)",
        )
        return dict(visual_description), decision

    if original_environment:
        decision = BackgroundVariationDecision(
            scene_index=scene_index,
            skipped=True,
            warnings=("explicit_environment_preserved",),
            original_environment=original_environment,
            reason="explicit environment intent preserved (non-empty environment dict)",
        )
        return dict(visual_description), decision

    assigned_type = resolve_environment_type(scene_index, total_scenes)
    if assigned_type not in SUPPORTED_ENVIRONMENTS:
        decision = BackgroundVariationDecision(
            scene_index=scene_index,
            skipped=True,
            warnings=("unsupported_environment_type",),
            original_environment=original_environment,
            reason=f"candidate {assigned_type!r} is not in SUPPORTED_ENVIRONMENTS",
        )
        return dict(visual_description), decision

    previous_type = (
        resolve_environment_type(scene_index - 1, total_scenes)
        if scene_index > 0
        else ""
    )
    palette, variant = resolve_environment_palette(
        scene_index, total_scenes, assigned_type
    )
    staged_environment: dict[str, Any] = {"type": assigned_type}
    staged_environment.update(palette)

    new_visual_description = dict(visual_description)
    new_visual_description["environment"] = staged_environment
    decision = BackgroundVariationDecision(
        scene_index=scene_index,
        assigned_type=assigned_type,
        palette_variant=variant,
        previous_type=previous_type or None,
        filled=True,
        changed=True,
        reason="assigned deterministic environment backdrop",
    )
    return new_visual_description, decision


# ---------------------------------------------------------------------------
# Sequence-level application
# ---------------------------------------------------------------------------


def apply_background_variation_sequence(
    visual_descriptions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], BackgroundVariationReport]:
    """Apply deterministic background variation across a sequence of scenes.

    When the feature flag is OFF this returns the original descriptions
    unchanged (as a new list) with a disabled report.
    """
    total = len(visual_descriptions)
    if not VISUAL_BACKGROUND_VARIATION_ENABLED:
        report = BackgroundVariationReport(
            applied_count=0,
            skipped_count=total,
            warning_count=0,
            enabled=False,
            summary="background variation disabled (flag OFF)",
        )
        return list(visual_descriptions), report

    new_descriptions: list[dict[str, Any]] = []
    decisions: list[BackgroundVariationDecision] = []
    applied_count = 0
    skipped_count = 0
    warning_count = 0
    for index, desc in enumerate(visual_descriptions):
        new_desc, decision = apply_background_variation(
            desc or {}, scene_index=index, total_scenes=total
        )
        new_descriptions.append(new_desc)
        decisions.append(decision)
        if decision.changed:
            applied_count += 1
        else:
            skipped_count += 1
        warning_count += len(decision.warnings)

    report = BackgroundVariationReport(
        decisions=tuple(decisions),
        applied_count=applied_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
        enabled=True,
        summary=f"background variation assigned to {applied_count}/{total} scenes",
    )
    return new_descriptions, report