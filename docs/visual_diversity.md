# Visual Diversity Policy (V1.4-B)

## Purpose

The Visual Diversity Policy is a deterministic, pure, standalone service that detects repetitive visual treatments across a sequence of scenes and produces safe variation recommendations.

It analyzes camera patterns, motion treatments, story treatments, and focus patterns to identify when consecutive scenes use the same visual approach, and provides advisory recommendations for variation using only supported vocabulary values.

## Relationship to V1.4-A

V1.4-B is **NOT** a replacement for V1.4-A (`VisualStoryPlanner`). The intended data flow is:

```
ScenePlan[]
      |
      v
V1.4-A VisualStoryPlanner
      |
      v
VisualStoryPlan
      |
      v
V1.4-B VisualDiversityPolicy
      |
      v
VisualDiversityReport
```

V1.4-B may also inspect the original `ScenePlan` objects for explicit intent. It does **NOT** modify rendering behavior yet.

## Inputs

- `scenes: list[ScenePlan]` - The sequence of scenes to analyze
- `story_plan: VisualStoryPlan | None` - Optional V1.4-A output for derived values

## Outputs

- `VisualDiversityReport` containing:
  - `decisions: tuple[VisualDiversityDecision, ...]` - Per-scene analysis
  - `warnings: tuple[str, ...]` - Sequence-level warnings

Each `VisualDiversityDecision` contains:
- `scene_index: int` - Scene position in sequence
- `repeated_with_previous: bool` - Any repetition detected
- `repeated_camera: bool` - Camera pattern repetition
- `repeated_motion: bool` - Motion treatment repetition
- `repeated_treatment: bool` - Story treatment repetition
- `repeated_focus_pattern: bool` - Focus pattern repetition
- `warnings: tuple[str, ...]` - Specific warning codes
- `camera_recommendations: tuple[str, ...]` - Suggested camera alternatives
- `motion_recommendations: tuple[str, ...]` - Suggested motion alternatives
- `treatment_recommendations: tuple[str, ...]` - Suggested treatment alternatives

## Repetition Categories

### Adjacent Repetition
Detects when consecutive scenes share the same:
- Camera pattern (e.g., both use `static`)
- Motion treatment (e.g., both use `fade`)
- Story treatment (e.g., both use `establish`)
- Focus pattern (e.g., both focus on `character`)

### Short-Run Repetition
Detects when the same visual treatment occurs 3+ consecutive times, producing additional warnings like `camera_run:static:3`.

## Recommendation Policy

When repetition is detected, the policy generates deterministic alternatives:

### Camera Alternatives
Each camera pattern has a predefined ordering of alternatives:
- `static` -> `slow_zoom_in`, `pan_right`, `pan_left`, `focus_on_character`
- `slow_zoom_in` -> `static`, `pan_right`, `pan_left`, `slow_zoom_out`
- etc.

### Motion Alternatives
Each motion type has a predefined ordering of alternatives:
- `fade` -> `scale`, `move`, `enter`, `zoom`
- `scale` -> `fade`, `move`, `zoom`, `enter`
- etc.

### Treatment Alternatives
Each treatment has a predefined ordering of alternatives:
- `establish` -> `explain`, `problem_focus`, `compare`, `proof`
- etc.

## Explicit Intent Precedence

The service distinguishes between:
- **Explicit intent**: Camera/motion values set directly on the `ScenePlan`'s `VisualScene`
- **Derived recommendations**: Values from the `VisualStoryPlan`

**The service NEVER recommends overwriting explicit intent.** When a scene has explicit camera or motion values, the service:
- Still detects and warns about repetition
- Returns empty recommendation tuples (no alternatives suggested)

This ensures that explicit creative decisions are preserved.

## Deterministic Guarantees

- Identical inputs always produce identical outputs
- No use of `random`, timestamps, UUIDs, or hash-order-dependent behavior
- No network calls, LLM calls, or external dependencies
- Stable ordering with explicit tie-breakers

## Unsupported Value Behavior

- Unknown camera patterns or motion types are ignored (no crash)
- Empty sequences produce empty reports
- Single scenes produce decisions with no repetition warnings
- If no suitable alternative exists, returns empty recommendation tuple with diagnostic warning

## Limitations

1. **Standalone only**: Not connected to the production pipeline yet
2. **No global similarity detection**: Only adjacent and short-run (3+) repetition
3. **No feature flag**: Not yet available for runtime toggling
4. **Explicit intent always wins**: Recommendations only for derived values

## Why It Is Currently Standalone

V1.4-B is intentionally isolated to:
- Validate the detection and recommendation logic independently
- Avoid destabilizing the production pipeline
- Allow review and iteration before integration
- Maintain clean separation of concerns

## Future Integration Point

When ready for integration:
1. Add feature flag for runtime toggling
2. Connect to V1.4-A output in the pipeline
3. Feed recommendations back to the planner for iterative improvement
4. Add global similarity detection for longer sequences

## Important Note

**V1.4-B does NOT modify rendering behavior yet.** It is an advisory-only analysis layer that produces reports. Any changes to actual rendering require explicit integration work.

