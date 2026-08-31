# Composition Decision Layer (V1.4-C)

## Purpose

The Composition Decision Layer is a deterministic, pure, standalone planning service that decides how each scene should be visually composed based on existing scene structure, V1.4-A story decisions, and V1.4-B diversity analysis.

It analyzes scene content (characters, objects, text elements) and story context (beat type, treatment) to recommend high-level composition layouts using only supported vocabulary values.

## Architecture

V1.4-C is the third layer in the V1.4 visual planning stack:

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
      |
      v
V1.4-C CompositionPlanner
      |
      v
CompositionPlan
```

V1.4-C may also inspect the original `ScenePlan` objects for explicit positioning intent. It does **NOT** modify rendering behavior yet.

## Inputs

- `scenes: list[ScenePlan]` - The sequence of scenes to analyze
- `story_plan: VisualStoryPlan | None` - Optional V1.4-A output for derived values
- `diversity_report: VisualDiversityReport | None` - Optional V1.4-B output

## Outputs

- `CompositionPlan` containing:
  - `decisions: tuple[CompositionDecision, ...]` - Per-scene composition decisions
  - `warnings: tuple[str, ...]` - Sequence-level warnings

Each `CompositionDecision` contains:
- `scene_index: int` - Scene position in sequence
- `composition_type: str` - Recommended composition type
- `primary_region: str` - Primary subject region
- `secondary_region: str | None` - Secondary subject region (if applicable)
- `text_region: str | None` - Text element region (if applicable)
- `subject_regions: tuple[str, ...]` - Types of subjects present
- `recommended_scale: str` - Recommended scale (small/medium/large)
- `recommended_alignment: str` - Recommended alignment (center/left/right)
- `repeated_with_previous: bool` - Whether composition repeats previous scene
- `warnings: tuple[str, ...]` - Specific warning codes

## Composition Vocabulary

### Composition Types
- `single_subject` - One meaningful visual subject
- `subject_support` - Primary subject with supporting elements
- `comparison` - Two subjects in contrast/comparison
- `text_led` - Text is the primary communication element
- `object_led` - Object/diagram is the primary explanatory element
- `problem_focus` - Problem-focused composition (restrained)
- `solution_result` - Solution/result composition (expansive)

### Regions
- `center` - Center of frame
- `left` - Left side
- `right` - Right side
- `upper` - Upper portion
- `lower` - Lower portion
- `left_center` - Left-of-center
- `right_center` - Right-of-center
- `upper_left` - Upper left quadrant
- `upper_right` - Upper right quadrant
- `lower_left` - Lower left quadrant
- `lower_right` - Lower right quadrant

### Scales
- `small` - Reduced size
- `medium` - Standard size
- `large` - Expansive size

### Alignments
- `center` - Centered
- `left` - Left-aligned
- `right` - Right-aligned

## Decision Precedence

The planner follows a strict precedence order:

1. **Explicit scene positions** - If the scene has explicit positioning (x/y coordinates), preserve it
2. **V1.4-A story treatment** - Use treatment from story planner if available
3. **Beat type** - Use beat type from story planner or scene role
4. **Content-based classification** - Fall back to counting subjects
5. **Safe fallback** - Default to `single_subject`

## Diversity Behavior

The planner detects repeated composition patterns and provides deterministic alternatives:

- When the same composition type appears 2+ times consecutively, an alternative layout is used
- Warnings are generated for repeated compositions (`repeated_composition:<type>`)
- Short-run warnings for 3+ consecutive same compositions (`composition_run:<type>:<count>`)
- Sequence-level warning for low composition diversity (`low_composition_diversity`)

### Alternative Layouts
- `single_subject`: center → upper
- `comparison`: left/right → right/left
- `subject_support`: center/lower → left/right
- `text_led`: center/upper → center/lower
- `object_led`: center → upper
- `problem_focus`: center → left_center
- `solution_result`: center/upper → center/lower

## Explicit Intent Preservation

The planner **NEVER** overwrites explicit scene decisions:

- If a scene has explicit character/object/text positions (x/y coordinates), the planner:
  - Still classifies the composition type
  - Adds `explicit_composition_preserved` warning
  - Does NOT recommend moving elements

This ensures that explicit creative decisions are preserved.

## Deterministic Guarantees

- Identical inputs always produce identical outputs
- No use of `random`, timestamps, UUIDs, or hash-order-dependent behavior
- No network calls, LLM calls, or external dependencies
- Stable ordering with explicit tie-breakers

## Limitations

1. **Standalone only**: Not connected to the production pipeline yet
2. **No geometry**: Does not calculate actual pixel positions or bounding boxes
3. **No renderer integration**: Does not modify rendering behavior
4. **No feature flag**: Not yet available for runtime toggling
5. **High-level only**: Produces composition recommendations, not pixel-perfect layouts

## Why Geometry is Intentionally Not Handled

V1.4-C is a **planning service**, not a renderer. It intentionally does not:

- Calculate actual rendered bounding boxes
- Simulate renderer frames
- Calculate FFmpeg camera transforms
- Estimate text wrapping
- Perform pixel collision detection
- Inspect generated MP4s

These capabilities belong to the renderer and QA layers (V1.2, V1.3, and future V1.5+).

## Future Integration Point

When ready for integration:
1. Add feature flag for runtime toggling
2. Connect to V1.4-A and V1.4-B outputs in the pipeline
3. Feed composition recommendations to the renderer
4. Add more sophisticated layout algorithms

## Important Note

**V1.4-C does NOT modify rendering behavior yet.** It is an advisory-only planning layer that produces composition recommendations. Any changes to actual rendering require explicit integration work.
