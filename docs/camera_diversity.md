# V1.6-G — Camera Diversity, Scene Activity & Attention-Target Safety

An additive, deterministic execution layer that sits between scene
choreography/emotion (V1.6-E/F) and RenderJobSpec construction. It does NOT
replace or rewrite any earlier V1.6 service.

## Problem

The A→F validation revealed three quality gaps:

1. **Camera repetition** — `slow_zoom_in` appeared 3× in a 7-scene video.
2. **Weak pan rendering** — `pan_*` and `zoom_then_pan` produced only ~±6 px
   of movement at 720p, imperceptible to viewers.
3. **Fake attention target** — V1.6-E emitted
   `emphasis_target_not_in_cast:character:character` for a text-attention
   scene because V1.4-D's placeholder `focus_target: "character"` leaked through.

## Scope

| ID | Change | Location |
|----|--------|----------|
| G1 | Deterministic camera-pattern diversity | `src/services/camera_diversity.py` |
| G2 | Wider pan/zoom-then-pan interpolation ranges | `src/services/stickman_renderer.py` (minimal) |
| G3 | Advisory scene-activity metadata | `src/services/camera_diversity.py` |
| G4 | Placeholder focus_target sanitization | `src/pipeline/auto_publish_pipeline.py` + `camera_diversity.py` |

## Architecture

```
V1.6-D camera execution → V1.6-E choreography → V1.6-F emotion → V1.6-G → RenderJobSpec
```

V1.6-G reads the camera spec V1.6-D produced and refines it. It never
rewrites authored camera intent.

## Feature Flag

`VISUAL_CAMERA_DIVERSITY_ENABLED = False` (default OFF).

When OFF: the description is returned unchanged, no metadata, no side effects.

## G1 — Camera Diversity

Uses `previous_camera_patterns` threaded across scenes. When a non-static
pattern has appeared `_MAX_REPEAT` (2) times in recent history, a role-aware
alternative is selected:

- `hook`: slow_zoom_in → pan_right → pan_left → zoom_then_pan
- `contrast`: pan_right → pan_left → zoom_then_pan → slow_zoom_in
- `solution`: slow_zoom_out → pan_right → pan_left → slow_zoom_in
- etc.

Static patterns are never forced to change. Authored camera instructions are
preserved.

## G2 — Stronger Camera Execution

The renderer's `_apply_camera_pattern` previously used ranges of ±0.06×width
(~±6 px at 720p). These were widened to ±0.15×width (~288 px at 1080p) via
new constants `PAN_RANGE_RATIO` and `ZOOM_THEN_PAN_RANGE_RATIO` in
`scene_composition.py`. The existing safe-area clamp prevents cropping.

This is the one protected-file change, justified because G2 explicitly requires
visible renderer movement and the change is minimal (3 numeric constants).

## G3 — Scene Activity

Advisory metadata only. Classifies each scene as high/medium/low activity based
role + character count. Never mutates motion or camera output.

## G4 — Attention-Target Safety

Two complementary fixes:

1. **Pipeline sanitizer** (`_sanitize_planning_camera_focus`): strips placeholder
   `focus_target` values (`"character"`, `"object"`, `""`) from planning metadata
   before choreography reads it.
2. **Diversity sanitizer** (`_safe_camera_spec`): clears placeholder focus_target
   from the camera spec itself.

Together these prevent any downstream code from manufacturing a fake
`("character", "character")` target.

## Determinism

No random/UUID/timestamps/global state. Role-diversity orderings are fixed
tuples. The same scene sequence always produces the same camera decisions.

## Failure Handling

Invalid input (non-dict description, missing camera, placeholder focus) safely
skips with a recorded warning. Never raises.

## Files

- New: `src/services/camera_diversity.py`, `tests/test_camera_diversity.py`,
  `tests/test_camera_diversity_integration.py`
- Modified: `src/pipeline/auto_publish_pipeline.py` (flag, threading, metadata,
  sanitizer), `src/services/stickman_renderer.py` (G2 pan ranges, minimal),
  `src/services/scene_composition.py` (pan range constants)