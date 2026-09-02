# V1.5 — Visual Planning Application Layer

## Purpose

V1.4 (VisualPlanning A–G) produces **advisory** per-scene visual planning
metadata: story treatment, diversity flags, composition type, camera pattern,
and attention target. By design V1.4 never changes render inputs; the
recommendations only *describe* what the plans would do.

V1.5 is a small, deterministic, feature-flagged **application layer** that sits
between the V1.4 planning stack and the existing V1.2/V1.3 staging/rendering
path. It consumes the V1.4 advisory plans and **selectively** applies a safe
subset of those recommendations to the staged visual description *before*
`RenderJobSpec` construction.

The V1.5 layer modifies **planning/staging inputs only** — it never changes
renderer behavior, never creates a second rendering architecture, and never
touches `video_assembler.py`, `content_package.py`, or the V1.4 planners.

## Relationship to V1.4-A through G

| Component | Role | Consumed by V1.5 |
|---|---|---|
| V1.4-A `VisualStoryPlanner` | story treatment per scene | `visual_planning.camera` via top-level hints |
| V1.4-B `VisualDiversityPolicy` | diversity flags / recommendations | informational (`visual_planning.diversity`) |
| V1.4-C `CompositionPlanner` | composition type | `visual_planning.composition.composition_type` |
| V1.4-D `CameraPlanner` | camera pattern + focus target | `visual_planning.camera.recommended_pattern/focus_target` |
| V1.4-E `AttentionPlanner` | attention target | `visual_planning.attention.primary_target` |
| V1.4-F | pipeline integration (advisory metadata) | provides the `visual_planning` dict per scene |
| V1.4-G | visual validation harness | unchanged; V1.5 adds its own harness |

## Architecture

```
ScenePlan[]
  → V1.3 semantic analysis (beats + focus, once per phase)
  → V1.4 planning stack (A–E, feature-flagged)
  → V1.5 application layer  (this service)
  → existing V1.3 lowering / staging (_stage_structured_visual)
  → RenderJobSpec
  → existing renderer
```

### New files

- `src/services/visual_planning_application.py` — the application service:
  - `VisualPlanningApplicationDecision` (frozen dataclass)
  - `VisualPlanningApplicationReport` (frozen dataclass, `to_dict()`)
  - `apply_visual_planning(visual_description, visual_planning, scene_index)`
    — per-scene entry point.
  - `apply_visual_planning_sequence(visual_descriptions, visual_plannings)`
    — sequence-level entry point producing a report.
- `tests/test_visual_planning_application.py` — unit tests (25 tests).
- `tests/test_visual_planning_application_integration.py` — pipeline-level
  integration tests (7 tests).
- `docs/visual_planning_application.md` — this document.
- `output/v15_validation/run_validation.py` — real-render A/B validation
  harness (gitignored under `output/`).

### Pipeline integration boundary

In `AutoPublishPipeline._render_visual_scene`, immediately after V1.4-F attaches
`visual_description["visual_planning"]` and **before** `RenderJobSpec` is
built, the V1.5 layer runs:

```python
if vpa_mod.VISUAL_PLANNING_APPLICATION_ENABLED:
    applied_desc, vpa_decision = vpa_mod.apply_visual_planning(
        visual_description, semantic_context["visual_planning"], scene_index=...)
    visual_description = applied_desc
    visual_description["visual_planning_application"] = vpa_decision.to_dict()
```

The returned render record also gains `visual_planning_application`, and
`_render_scenes()` surfaces `visual_planning_application: True` when at least
one scene was actually changed.

## Feature flag

Independent flag (module-level in `src/services/visual_planning_application.py`):

```python
VISUAL_PLANNING_APPLICATION_ENABLED = False
```

Semantics:

| V1.4 | V1.5 application | Behavior |
|---|---|---|
| OFF | any | existing V1.2/V1.3 path; V1.5 never executes |
| ON | OFF | V1.4 advisory metadata only (unchanged V1.4-F) |
| ON | ON | V1.4 recommendations may be applied through the V1.5 layer |

V1.5 **never executes when V1.4 is disabled**: the pipeline only invokes the
application layer when `visual_planning` metadata is present (which requires
the V1.4 stack), and `apply_visual_planning_sequence` no-ops on an empty
`visual_plannings` list. V1.4 OFF + V1.5 ON behaves exactly like the existing
pipeline.

## Application precedence

For every decision, this precedence is enforced (highest first):

1. **Explicit scene intent** — author-provided `camera_spec.pattern`,
   `focus_target`, motions, transitions, positions.
2. **Existing V1.3 semantic decision** representing explicit intent.
3. **Existing scene constraints** — available characters/objects.
4. **V1.4 recommendation**.
5. **Existing V1.2/V1.3 fallback**.

Explicit intent always wins. When a recommendation cannot be safely applied,
the existing behavior is retained and an application warning is recorded.

## Camera application (V1.4-D)

A camera recommendation is applied only when **all** of:

- the scene has a valid target for the selected camera pattern,
- the recommended pattern is in the existing `SUPPORTED_CAMERA_PATTERNS`
  vocabulary (no invented vocabulary),
- the scene has no explicit camera intent (`camera_spec.pattern` is a real
  supported pattern),
- applying it does not violate scene constraints.

`focus_on_character` / `focus_on_object` are applied only when the recommended
focus target resolves to an actual character/object in the scene — never
invented. Non-focus patterns (`slow_zoom_in`, `pan_left`, …) are applied
without a target. Explicit scale/motion instructions are never modified to
make a recommendation fit.

If a camera recommendation cannot be safely applied, the existing camera is
retained and a warning/reason is recorded.

## Composition application (V1.4-C)

Composition recommendations are compatibility-checked against the actual scene
contents and recorded as additive metadata (`recommended_composition`):

- `single_subject` requires ≥ 1 subject.
- `comparison` requires ≥ 2 subjects (never collapses distinct subjects).
- `object_led` requires ≥ 1 object.
- text-led compositions require actual text elements.

V1.5 never fabricates scene elements, never deletes explicit scene positions,
and never rearranges explicitly positioned elements. Incompatible
recommendations preserve the original composition.

## Attention application (V1.4-E)

Attention recommendations are applied only when the target resolves against
the actual scene (characters/objects). Explicit focus and any camera focus
target already applied by V1.4-D are respected — attention never overrides an
explicit `focus_target`, and never invents a target. Attention transitions are
not forced; they are honored only where they do not conflict with explicit
intent or camera targets.

## Motion / transition safety

V1.5 does **not** invent motion primitives or transitions, and does **not**
alter explicit motions or transitions. This task focuses on safely applying the
existing V1.4 camera/composition/attention decisions. Future motion/transition
decisions must reuse the existing supported vocabulary and existing APIs.

## Data model

```python
@dataclass(frozen=True)
class VisualPlanningApplicationDecision:
    scene_index: int
    applied_camera: str | None
    applied_composition: str | None
    applied_attention: str | None
    camera_changed: bool
    composition_changed: bool
    attention_changed: bool
    changed: bool
    warnings: tuple[str, ...]
    original_camera: dict[str, Any]
    original_composition_type: str | None
    original_attention_target: str | None
    reason: str
    # to_dict() -> JSON-serializable dict

@dataclass(frozen=True)
class VisualPlanningApplicationReport:
    decisions: tuple[VisualPlanningApplicationDecision, ...]
    applied_count: int
    skipped_count: int
    warning_count: int
    enabled: bool
    v14_required: bool
    summary: str
    # to_dict() -> JSON-serializable dict
```

## Safety rules

- **No fabrication** — a character/object/target must already exist in the
  scene to be referenced; nothing is ever invented.
- **Explicit intent is immutable** — author-provided camera patterns, focus
  targets, scale, motion, transition, position, and composition directives are
  never overwritten.
- **Vocabulary validation** — only patterns present in the existing
  `SUPPORTED_CAMERA_PATTERNS` vocabulary are applied; unknown recommendations
  are skipped with a warning.
- **Read-only inputs** — `ScenePlan`, `VisualScene`, V1.4 planner results, and
  V1.3 semantic results are never mutated; application works on shallow dict
  copies of the staged visual description only.
- **Warn-and-continue** — every skipped recommendation records a deterministic
  warning/reason; processing always continues.
- **No new render architecture** — the renderer, `video_assembler.py`, and
  `content_package.py` are untouched.

## Explicit intent behavior

A scene with explicit `camera_spec.pattern` keeps it verbatim — the camera
recommendation is skipped with reason `explicit_camera_intent`. A scene with
explicit `focus_target` keeps it — attention recommendations that would replace
it are skipped with a warning. Explicit positions are never removed or
rearranged; scale instructions are never modified to make a recommendation fit.

## Fallback behavior

When a recommendation cannot be applied (missing target, unsupported
vocabulary, explicit intent conflict, constraint violation), the pre-existing
V1.2/V1.3 value is retained unchanged and the decision records
`changed=False` plus the skip reason. The pipeline then lowers the visual
description exactly as it would have without V1.5.

## Determinism

The application layer is a pure function of its inputs:

- no randomness, time, UUIDs, network, or LLM/API calls,
- stable iteration order (scene order, insertion order),
- frozen dataclass outputs with JSON-serializable `to_dict()`,
- identical inputs produce byte-identical reports (covered by a repeated-
  execution test and by `report.to_dict()` round-trip tests).

## Limitations

- V1.5 applies **camera pattern + focus target** (V1.4-D), **attention
  target** (V1.4-E), and records **composition compatibility metadata**
  (V1.4-C). Composition *layout* changes (repositioning elements) are
  deliberately out of scope in V1.5.
- Recommendations that would require new motion primitives, transitions, or
  renderer features are not applied (none exist in V1.4).
- Application is per-scene and stateless; sequence-level diversity is inherited
  from the V1.4-B policy, not re-enforced by V1.5.
- `job_specs.json` / render records expose
  `visual_description.visual_planning_application` for observability; this key
  is additive metadata and does not affect rendering.

## Future integration points

- Applying composition recommendations to actual element placement
  (positions/scale) once a safe staging vocabulary for it exists.
- Motion/transition recommendations if V1.4 grows them — reusing the existing
  supported vocabulary only.
- Feeding the application report into analytics/telemetry (deterministic JSON
  already supported).
- A UI/review pass that inspects `VisualPlanningApplicationReport` before
  rendering.
