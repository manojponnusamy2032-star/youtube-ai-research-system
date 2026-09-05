# V1.6-D - Camera Execution

V1.6-D is a deterministic execution layer that translates camera intent and
planning decisions (explicit `camera_spec`, V1.4 camera/story decisions, V1.4-E
attention targets, or scene semantics) into an *executable* camera spec the
existing renderer already understands. It closes the gap where V1.4/V1.5 camera
planning produced decisions that never reached the renderer.

This is an **execution layer**, not a planning replacement: V1.4 decides WHAT
the camera should do; V1.6-D makes that decision visibly happen. It never
modifies V1.4/V1.5 planner results, never mutates ScenePlan/VisualScene, and
does not change the renderer (no renderer integration was required).

## Feature flag

```python
VISUAL_CAMERA_EXECUTION_ENABLED = False
```

The flag is defined in `src/services/camera_execution.py` and defaults to
`False`. With the flag OFF, the original camera behavior (renderer defaults /
explicit camera specs / explicit camera motions) is completely unchanged.

## Supported behaviors

Only behaviors the existing renderer can safely execute are produced, all drawn
from the existing `SUPPORTED_CAMERA_PATTERNS` vocabulary:

- Static framing (`static`) - no camera movement.
- Zoom in (`slow_zoom_in`) - gradual scale increase around a focal point.
- Zoom out (`slow_zoom_out`) - gradual scale decrease.
- Pan left / pan right (`pan_left`, `pan_right`) - controlled horizontal framing.
- Vertical framing shift - via the renderer-supported focus patterns
  (`focus_on_character` / `focus_on_object`); the camera pans vertically to
  keep the focus target centered.
- Emphasis - short controlled zoom/focus movement (focus patterns cap the
  movement at 1.6 s and hold).

Fake camera behavior (e.g. randomly moving characters) is never used. Camera
movement always represents real framing behavior.

## Precedence

Highest to lowest:

1. **Explicit camera motion primitives** (`Motion` with `target == "camera"`) --
   the renderer executes these directly and suppresses the declarative spec;
   V1.6-D defers without writing anything.
2. **Explicit executable camera spec** (author-authored or V1.5-applied pattern
   in `SUPPORTED_CAMERA_PATTERNS`) -- preserved exactly as authored.
3. **V1.4 camera decision** (`visual_planning.camera.recommended_pattern`) and
   **V1.4-A story camera recommendation** (`visual_planning.recommended_camera`).
4. **Scene-aware fallback** derived deterministically from the scene role.
5. **Safe fallback** -- static framing (identical to today's renderer default).

Focal point priority for focus patterns: explicit `focus_target` (resolved
against real scene elements, never invented) --> the V1.4 camera-decision focus
target --> the V1.4-E attention `primary_target`. If no focus subject can be
resolved, the pattern safely downgrades to `slow_zoom_in` (a zoom that needs no
subject), never crashing and never inventing an element.

## Execution model

The produced `camera` dict is a `CameraSpec`-compatible dict using the
renderer's existing coordinate conventions:

```python
{"pattern": "slow_zoom_in", "easing": "ease_in_out", "duration": 2.0}
```

Temporal smoothing is handled by the existing renderer interpolation
(`apply_easing` / `interpolate_value`); this layer only supplies the bounded
pattern, finite positive duration and easing. No second animation framework is
introduced.

## Determinism

No `random`, no timestamps, no UUIDs, no global state. Scene-role fallbacks use
fixed option tuples rotated by the scene index. Identical inputs always produce
identical decisions.

## Continuity

Sequence-level execution threads the previous scene's executed camera into the
next scene so the fallback path avoids direct direction reversals
(`pan_left` <-> `pan_right`, `slow_zoom_in` <-> `slow_zoom_out`). Planner
decisions are authoritative and are never rewritten for continuity.

## Pipeline integration

V1.6-D runs inside `_render_visual_scene` after V1.6-C motion variation and
before `RenderJobSpec` is built:

```text
V1.4 planning
    ->
V1.5 planning application
    ->
V1.6-A background variation
    ->
V1.6-B character variation
    ->
V1.6-C motion variation
    ->
V1.6-D camera execution
    ->
RenderJobSpec
    ->
renderer
```

The decision is exposed as `visual_description["camera_execution"]`, on the
render record (at per-scene level), and at pipeline stage level
(`stage_result["camera_execution"] = True`) when the flag is enabled. When the
flag is OFF none of these keys appear and the render job is byte-for-byte
unchanged.

## Compatibility

V1.6-D runs after V1.6-A/B/C, writes separate metadata (`camera_execution` and
the executed `camera` spec), and is independent of them. It preserves all
`environment` / `character_variation` / `motion_variation` keys written by the
earlier layers. Explicit camera motions and explicit camera specs always win,
regardless of the other V1.6 layers.

## Validation

- `tests/test_camera_execution.py` -- 38 focused unit tests.
- `tests/test_camera_execution_integration.py` -- 5 pipeline integration tests.
- `output/v16d_validation/validate_camera_render.py` -- minimal OFF/ON real
  render that decodes both MP4s and proves the executed camera movement caused
  a visible frame difference (first frames nearly identical, final frames
  strongly divergent).