# VisualStoryPlanner (V1.4-A)

## Purpose and Scope

The `VisualStoryPlanner` is an **advisory-only** sequence-level visual treatment planning service for the YouTube AI Research System. It analyzes a sequence of scenes and produces immutable, deterministic visual treatment decisions without mutating any input objects or calling the production pipeline.

**Key characteristics:**
- **Advisory only**: Does not create render primitives, modify scenes, or invoke FFmpeg/renderers
- **Deterministic**: Identical inputs always produce identical outputs
- **Non-mutating**: Never modifies input `ScenePlan` or `VisualScene` objects
- **Vocabulary-constrained**: Only uses supported camera patterns, motion types, and transitions
- **No hallucination**: Never invents focus targets; empty focus stays empty
- **Repetition-aware**: Detects and flags adjacent repeated treatments, cameras, motions, and focus targets

**V1.4-A Status**: **Not production-wired**. This layer is not connected to the AutoPublishPipeline, render jobs, or any production path. It exists solely for analysis, planning, and future integration.

---

## Inputs and Outputs

### Inputs

```python
planner.plan(
    scenes: list[ScenePlan],
    *,
    beats: list[Any] | None = None,      # Optional beat annotations per scene
    focuses: list[Any] | None = None     # Optional focus annotations per scene
) -> VisualStoryPlan
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `scenes` | `list[ScenePlan]` | Yes | Sequence of scenes to plan for. Each must have `narration`. `visual` is optional. |
| `beats` | `list[Any]` | No | Optional beat annotations (dict or object with `type` field). Overrides `scene_role` inference. |
| `focuses` | `list[Any]` | No | Optional focus annotations (dict or object with `primary` field). Fallback for missing focus. |

### Outputs

```python
@dataclass(frozen=True)
class VisualStoryDecision:
    scene_index: int
    beat_type: str                    # e.g., "HOOK", "PROBLEM", "CONTRAST", ...
    focus_target: str                 # Primary focus target (may be empty string)
    treatment: str                    # e.g., "establish", "problem_focus", "compare", ...
    camera_pattern: str               # One of SUPPORTED_CAMERA_PATTERNS
    preferred_motion_types: tuple[str, ...]  # Subset of SUPPORTED_MOTION_TYPES
    transition_type: str | None       # One of SUPPORTED_TRANSITION_TYPES or None (final scene)
    repeated_with_previous: bool      # True if any adjacent repetition detected
    warnings: tuple[str, ...]         # Deduplicated warnings for this scene

@dataclass(frozen=True)
class VisualStoryPlan:
    decisions: tuple[VisualStoryDecision, ...]
    warnings: tuple[str, ...]         # Global deduplicated warnings

    def to_dict(self) -> dict[str, Any]:
        return {"decisions": [d.to_dict() for d in self.decisions], "warnings": list(self.warnings)}
```

Both `VisualStoryDecision` and `VisualStoryPlan` are **frozen dataclasses** (immutable) and provide `to_dict()` for JSON serialization.
## Treatment Vocabulary

The planner maps beat types to visual treatments. Each treatment has preferred cameras and motions.

### Beat Type → Treatment Mapping

| Beat Type | Treatment | Description |
|-----------|-----------|-------------|
| `HOOK` | `establish` | Opening scene, establishing context |
| `PROBLEM` | `problem_focus` | Highlighting a problem/pain point |
| `CONTRAST` | `compare` | Side-by-side or before/after comparison |
| `EXPLANATION` | `explain` | Explaining a concept or mechanism |
| `EXAMPLE` | `proof` | Demonstrating proof, evidence, example |
| `SOLUTION` | `solution_growth` | Showing solution, growth, improvement |
| `CTA` | `cta` | Call to action |

Default fallback: `EXPLANATION` → `explain`

### Treatment → Camera Patterns (Preference Order)

| Treatment | Primary | Alternatives |
|-----------|---------|--------------|
| `establish` | `slow_zoom_in` | `static`, `pan_right` |
| `problem_focus` | `focus_on_character` | `slow_zoom_in`, `static` |
| `compare` | `pan_left` | `pan_right`, `static` |
| `explain` | `static` | `slow_zoom_in`, `pan_right` |
| `proof` | `pan_right` | `slow_zoom_in`, `static` |
| `solution_growth` | `slow_zoom_in` | `zoom_then_pan`, `static` |
| `cta` | `slow_zoom_out` | `static`, `pan_up` |

### Treatment → Motion Types (Preference Order)

| Treatment | Primary | Alternatives |
|-----------|---------|--------------|
| `establish` | `enter`, `zoom` | `fade`, `zoom` |
| `problem_focus` | `fade`, `scale` | `scale`, `zoom` |
| `compare` | `enter`, `move`, `pan` | `move`, `pan` |
| `explain` | `fade`, `scale` | `fade`, `zoom` |
| `proof` | `pan`, `scale` | `pan`, `zoom` |
| `solution_growth` | `scale`, `zoom` | `scale`, `fade` |
| `cta` | `fade`, `scale` | `fade`, `exit` |