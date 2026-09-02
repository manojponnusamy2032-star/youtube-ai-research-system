# V1.6-A — Background Environment Variation

## Purpose

Long rendered videos were visually repetitive: every scene without explicit
environment intent fell back to the identical outdoor sun/sky/grass backdrop.
In the V1.5 validation scenario all 7 scenes had `environment: {}`, so the
renderer drew the same backdrop in all of them.

V1.6-A is a small, deterministic, feature-flagged service that fills *empty*
scene environments with varied backdrops drawn from the existing
`SUPPORTED_ENVIRONMENTS` vocabulary, guaranteeing that adjacent scenes never
share a backdrop.

The layer modifies **staging inputs only** — it never changes renderer code,
never creates a second rendering architecture, and never touches
`stickman_renderer.py`, `scene_composition.py`, `video_assembler.py`,
`content_package.py`, or the V1.3–V1.5 services.

## Relationship to V1.2–V1.5

| Layer | Role | Interaction with V1.6-A |
|---|---|---|
| V1.2/V1.2.1 structured staging | `_stage_structured_visual` | upstream; provides the `visual_description.environment` slot |
| V1.3 semantic visuals | beats/focus/semantics | independent; V1.6-A runs with or without V1.3 |
| V1.4 planning stack | advisory metadata | independent; V1.6-A runs with or without V1.4 |
| V1.5 application layer | applies V1.4 recommendations | independent; V1.6-A hooks after V1.5 on the same staging dict |
| Renderer | `EnvironmentSpec` motifs | untouched; consumes the assigned environment as-is |

## Architecture

```
ScenePlan[]
  → existing staging (_stage_structured_visual)   ← empty environment slot
  → V1.3 semantics (optional)
  → V1.4 planning metadata (optional)
  → V1.5 application (optional)
  → V1.6-A background variation (this service)    ← fills EMPTY environment
  → RenderJobSpec
  → existing renderer
```

### New files

- `src/services/background_variation.py` — the service:
  - `BackgroundVariationDecision` (frozen dataclass, `to_dict()`)
  - `BackgroundVariationReport` (frozen dataclass, `to_dict()`)
  - `apply_background_variation(visual_description, scene_index, total_scenes)`
    — per-scene entry point.
  - `apply_background_variation_sequence(visual_descriptions)`
    — sequence-level entry point producing a report.
  - `resolve_environment_type(scene_index, total_scenes)` /
    `build_environment(scene_index, total_scenes)` — pure helpers.
- `tests/test_background_variation.py` — unit tests.
- `tests/test_background_variation_integration.py` — pipeline-level
  integration tests.
- `docs/background_variation.md` — this document.

### Pipeline integration boundary

In `AutoPublishPipeline._render_visual_scene`, after the V1.5 block and
**before** `RenderJobSpec` is built (runs whenever the staging dict exists —
V1.3/V1.4/V1.5 are optional):

```python
import src.services.background_variation as bgv_mod

if bgv_mod.VISUAL_BACKGROUND_VARIATION_ENABLED:
    staged_desc, bgv_decision = bgv_mod.apply_background_variation(
        visual_description,
        scene_index=max(int(scene_number) - 1, 0),
        total_scenes=total,
    )
    visual_description = staged_desc
    visual_description["background_variation"] = bgv_decision.to_dict()
```

## Feature flag

Independent flag (module-level in `src/services/background_variation.py`):

```python
VISUAL_BACKGROUND_VARIATION_ENABLED = False
```

| V1.6-A flag | Behavior |
|---|---|
| OFF (default) | existing V1.2–V1.5 path, byte-for-byte unchanged |
| ON | empty environments receive a deterministic varied backdrop |

## Assignment policy

1. **Explicit intent wins.** A non-empty `environment` dict is never
   overwritten; the decision records `explicit_environment_preserved`.
2. **Vocabulary safety.** Only `SUPPORTED_ENVIRONMENTS` members are assigned
   (`default` is never assigned — it *is* the repetition being removed).
   Emitted keys are a subset of `EnvironmentSpec` fields
   (`type`, `background_color`, `ground_color`, `ground_y`, `accent_color`),
   so `SceneComposition.from_visual_description` parses them unchanged.
3. **Determinism.** Selection is a pure function of
   `(scene_index, total_scenes)` using `zlib.crc32` — no `random`, no
   timestamps, no hash-order dependence; identical inputs always produce
   identical outputs.
4. **Adjacency guarantee.** The assigned type never equals the previous
   scene's assigned type (fixed rotation with a deterministic bump).
5. **Palette variants.** Each type has two palettes (primary values from
   `examples/plan_visual_quality_v1.json`); the variant is also chosen by the
   stable digest, so a type recurring later in a video still differs.

## Observability

- Per scene: `visual_description["background_variation"]` and the render
  record's `background_variation` key carry the decision (`to_dict()`).
- `_render_scenes()` result gains `background_variation: True` when the layer
  ran for at least one scene.

## Validation

- `tests/test_background_variation.py` — unit tests (determinism, adjacency,
  explicit-intent preservation, vocabulary safety, flag-off no-op).
- `tests/test_background_variation_integration.py` — pipeline-level tests
  (flag OFF parity, independence from V1.3/V1.4/V1.5, explicit intent,
  adjacency, determinism, no input mutation).

## Limitations

1. Assignments are vocabulary-rotation based, not narratively grounded: the
   layer does not read beat/focus semantics on purpose (explicit intent and
   V1.5 contracts stay untouched).
2. Two palettes per type; more variants would increase long-video variety.
3. Only fills *empty* environments; scenes authored with a fixed backdrop are
   never varied (by design).