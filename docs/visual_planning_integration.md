# V1.4-F: Feature-Flagged Visual Planning Integration

Integrates the V1.4 planning stack (A–E) into `AutoPublishPipeline` behind a
new, **disabled-by-default** feature flag.

## Feature flag

```python
# src/pipeline/auto_publish_pipeline.py
SEMANTIC_VISUALS_ENABLED = False        # V1.3 (pre-existing)
VISUAL_STORY_PLANNER_ENABLED = False    # V1.4-F (new)
```

Effective condition:

```python
if SEMANTIC_VISUALS_ENABLED and VISUAL_STORY_PLANNER_ENABLED:
    run_v14_planning()
```

| `SEMANTIC_VISUALS_ENABLED` | `VISUAL_STORY_PLANNER_ENABLED` | Behavior |
|---|---|---|
| `False` | `False` | V1.2 baseline (unchanged) |
| `True` | `False` | V1.3 semantic visuals (unchanged) |
| `True` | `True` | V1.3 + V1.4-A..E planning stack |

The V1.4 flag is independent of, and never replaces, the V1.3 flag. The V1.4
stack never runs without the V1.3 semantic pipeline.

## Integration flow

```text
ScenePlan[]
    ↓
VisualBeatEngine            (_beat_inputs — once per planning phase)
    ↓
VisualFocusResolver         (_focus_results — once per planning phase)
    ↓
V1.4-A VisualStoryPlanner   ┐
V1.4-B VisualDiversityPolicy│  _plan_visual_story:
V1.4-C CompositionPlanner   │  each planner runs exactly once,
V1.4-D CameraPlanner        │  each consumes the previous plans
V1.4-E AttentionPlanner     ┘  (focus_results consumed, never recomputed)
    ↓
existing V1.3 semantic lowering (_semantic_contexts, beats/focus reused)
    ↓
existing staging (_stage_structured_visual, RenderJobSpec)
```

Beat detection and focus resolution run **exactly once** per planning phase
and are shared by the V1.3 lowering and the V1.4 stack.

## Where V1.4 output goes

Purely **advisory metadata**, attached additively:

- Per-scene semantic contexts gain a `visual_planning` key:
  `{scene_index, treatment, recommended_motions, recommended_camera,
  recommended_transition, diversity, composition, camera, attention}`.
- Structured render jobs gain `visual_description["visual_planning"]`
  (mirroring how V1.3 attaches `semantics` and `qa_report`).
- `_render_scenes`/`run()` results gain `visual_planning: True` so enabled
  and disabled runs are distinguishable.

Existing V1.3 keys (`beat`, `focus`, `motion_result`, `transition`) are never
replaced, and no scene model, motion, camera spec, or transition is ever
modified. Explicit scene intent always outranks V1.4 recommendations — that
precedence is encoded inside each planner.

## Determinism & purity

- No randomness, time, network, or renderer access in planning.
- Planner services are imported lazily inside `_plan_visual_story` because
  they import `ScenePlan` from the pipeline module (module-level imports
  would create a circular import).
- Identical inputs produce identical metadata; planners never mutate scenes.

## Frozen files untouched

`stickman_renderer.py`, `video_assembler.py`, `content_package.py`, all V1.3
semantic services, and `docs/visual_diversity.md` are not modified.

## Tests

- `tests/test_visual_planning_integration.py` — flag gating, once-per-phase
  execution, planner chaining, explicit-intent precedence, determinism,
  no renderer dependency, no duplicate beat/focus computation, empty-input
  safety, additive-only semantic metadata, path distinguishability.
- `tests/test_visual_planning_integration_e2e.py` — full `pipeline.run()`
  smoke tests (4 scenes, stub media) for enabled, V1.3-only, and V1.2 modes.
