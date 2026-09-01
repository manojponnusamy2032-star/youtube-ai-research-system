# Camera Continuity Planner (V1.4-D)

## Purpose

The Camera Continuity Planner is a deterministic, pure, standalone planning service that makes camera behavior work as a *sequence*, rather than selecting camera treatment independently for every scene.

It recommends camera patterns that:
- Preserve explicit, directed camera intent from production scenes
- Maintain visual continuity between consecutive scenes
- Avoid repetitive camera runs
- Derive sensible camera choices from story treatment (V1.4-A) and composition type (V1.4-C)
- Respect diversity recommendations (V1.4-B) while honoring explicit camera intent

This is an advisory-only planning layer. It does **NOT** modify any inputs, invoke the production pipeline, or make any external calls.

## Relationship to V1.4-A / V1.4-B / V1.4-C

V1.4-D builds on the earlier layers of the visual planning stack:

```
ScenePlan[]
      |
      v
V1.4-A VisualStoryPlanner  -> VisualStoryPlan  (treatments, beat, focus)
      |
      v
V1.4-B VisualDiversityPolicy -> VisualDiversityReport (repetition + variation recs)
      |
      v
V1.4-C CompositionPlanner  -> CompositionPlan  (composition type, regions, scale)
      |
      v
V1.4-D CameraPlanner       -> CameraPlan       (camera continuity sequence)
```

V1.4-D consumes the outputs of V1.4-A, V1.4-B, and V1.4-C as **optional** inputs, so it can also run standalone on a plain `list[ScenePlan]`.

## Inputs

- `scenes: list[ScenePlan]` - The sequence of scenes to analyze
- `story_plan: VisualStoryPlan | None` - Optional V1.4-A output (treatments)
- `diversity_report: VisualDiversityReport | None` - Optional V1.4-B output (repetition + camera recommendations)
- `composition_plan: CompositionPlan | None` - Optional V1.4-C output (composition types)

All are keyword-only arguments after `scenes`.

## Outputs

- `CameraPlan` containing:
  - `decisions: tuple[CameraDecision, ...]` - Per-scene camera decisions
  - `warnings: tuple[str, ...]` - Sequence-level warnings

Each `CameraDecision` contains:
- `scene_index: int` - Scene position in sequence
- `recommended_pattern: str` - The camera pattern to recommend
- `focus_target: str | None` - The focus target (character/object) or `None`
- `continuity_from_previous: str` - One of `established`, `held`, `changed`, `reversed`
- `repeated_with_previous: bool` - Whether the pattern repeats the prior scene
- `explicit_camera_preserved: bool` - Whether an explicit camera directive was preserved
- `warnings: tuple[str, ...]` - Specific warning codes

## Continuity States

The planner tracks how each recommended camera relates to the previous scene:

| State | Meaning |
|-------|---------|
| `established` | First scene in the sequence (no previous pattern) |
| `held` | Same pattern as the previous scene |
| `changed` | Different pattern from the previous scene |
| `reversed` | Opposite pan direction (e.g., `pan_left` → `pan_right`) |

Non-default states in the vocabulary (`continued`, `fallback`) are reserved for future integration.

## Camera Selection Logic

The planner chooses a camera pattern in this order of precedence:

1. **Explicit camera intent** (from `camera_spec.pattern` or a real legacy `camera_pattern`) - *always preserved*.
2. **Diversity camera recommendations** (from V1.4-B) - used when present and valid for available subjects.
3. **Treatment-based candidates** (from V1.4-A) - the preferred camera tuples per treatment.
4. **Composition-based candidates** (from V1.4-C) - used when no treatment is present.
5. **Safe fallback** - `focus_on_character` if characters exist, `focus_on_object` if objects exist, otherwise `static`.

### Targeting Constraints

When a candidate is `focus_on_character` or `focus_on_object`, the planner only keeps it if the scene actually contains characters/objects. Otherwise it moves to the next valid candidate.

## Explicit Intent Semantics

The planner distinguishes a *directed* camera/focus choice from the VS default values:

- Legacy `camera_pattern="hold"` is the **default/no-intent** value - it is treated as non-explicit so the planner can derive a better pattern.
- `primary_focus="scene"` (the default) is treated as no-intent - the planner derives a real character/object focus target only when one exists.
- Any `camera_spec.pattern` in `SUPPORTED_CAMERA_PATTERNS`, any non-`hold` legacy camera pattern, and any non-`scene` primary focus are treated as explicit and preserved.

Explicit camera directives are never overridden by diversity recommendations.

## Repetition & Warnings

- `repeated_with_previous` is set when the recommended pattern equals the prior scene's pattern.
- Warning codes include:
  - `explicit_camera_preserved` - an explicit directive was honored
  - `explicit_camera_repetition` - an explicit directive repeats the prior scene
  - `repeated_camera:<pattern>` - pattern repeated adjacent to previous
  - `camera_run:<pattern>:<n>` - three or more consecutive uses
- Sequence-level warning:
  - `low_camera_diversity` - three or more scenes all using a single pattern

## Deterministic Guarantees

- Identical inputs always produce identical outputs
- No use of `random`, timestamps, UUIDs, or hash-order-dependent behavior
- No network calls, LLM calls, or external dependencies
- Stable ordering with explicit tie-breakers

## Unsupported Value Behavior

- Unknown camera patterns in specs are ignored (no crash) and fall back to a valid derivation
- Empty sequences produce empty plans
- Single scenes produce a decision with `established` continuity and no repetition
- Scenes without visual subjects degrade gracefully (no focus target, safe fallback pattern)

## Limitations

1. **Standalone only**: Not connected to the production pipeline yet
2. **Advisory only**: Recommendations are not applied to rendering
3. **Explicit intent always wins**: On explicit scenes, diversity/treatment derivation is skipped
4. **No feature flag**: Not yet available for runtime toggling

## Why It Is Currently Standalone

V1.4-D is intentionally isolated to:
- Validate the camera continuity logic independently
- Avoid destabilizing the production pipeline
- Allow review and iteration before integration
- Maintain clean separation of concerns

## Future Integration Point

When ready for integration:
1. Add feature flag for runtime toggling
2. Connect V1.4-A/B/C outputs in the pipeline
3. Feed camera decisions back to the renderer's camera instructions
4. Add richer continuity rules (e.g., matching axis of motion across scenes)

## Important Note

**V1.4-D does NOT modify rendering behavior yet.** It is an advisory-only planning layer that produces reports. Any changes to actual rendering require explicit integration work.
