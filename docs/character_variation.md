# V1.6-B - Character Staging & Pose Variation

## Purpose

Rendered videos presented characters identically across scenes: every character
without explicit pose/scale/position intent rendered with the renderer defaults
(`pose="idle"`, `scale=1.0`, centered). In the V1.5 validation scenario all 6
characters were idle at default scale regardless of scene role.

V1.6-B is a small, deterministic, feature-flagged service that varies *default*
character intent - pose, scale, and position - using the existing renderer
vocabulary (`SUPPORTED_POSES`) and the existing V1.2 presentation staging
(clamping, framing, object clearance) which runs afterwards and stays
authoritative.

The layer modifies **staging inputs only** - it never changes renderer code,
never creates a second character system, and never touches
`stickman_renderer.py`, `scene_composition.py`, `video_assembler.py`,
`content_package.py`, or the V1.3-V1.6-A services.

## Root cause

Authored scenes commonly give characters only a name and (sometimes) a position.
Every character then renders with the renderer defaults, producing visually
identical character presentation scene after scene. Measured on the V1.5
validation scenario: 6/6 characters idle, 6/6 default scale.

V1.6-B addresses only the *unnecessary* repetition: explicit intent is always
preserved, and scenes with a single valid configuration are left untouched.

## Existing character pipeline

```
ScenePlan[]
  -> V1.3 semantics (optional)
  -> V1.4 planning metadata (optional)
| Renderer | `SUPPORTED_POSES` vocabulary | untouched; consumes staged characters as-is |

## Architecture

```
ScenePlan[]
  -> existing staging (_stage_structured_visual)   <- V1.6-B varies character defaults BEFORE this
  -> V1.3 semantics (optional)
  -> V1.4 planning metadata (optional)
  -> V1.5 application (optional)
  -> V1.6-A background variation (optional)
  -> V1.6-B character variation (this service)    <- varies DEFAULT pose/scale/x only
  -> RenderJobSpec
  -> existing renderer
```

### New files

- `src/services/character_variation.py` - the service:
  - `CharacterVariationDecision` (frozen dataclass, `to_dict()`)
  - `CharacterVariationReport` (frozen dataclass, `to_dict()`)
  - `apply_character_variation(characters, objects, scene_index, total_scenes, ...)`
    - per-scene entry point.
  - `apply_character_variation_sequence(scenes, ...)` - sequence-level entry
    point producing a report.
  - `_anchor_candidates(name, role)` / `_anchor_conflicts(...)` - pure helpers.
- `tests/test_character_variation.py` - unit tests.
- `tests/test_character_variation_integration.py` - pipeline-level integration
  tests.
- `docs/character_variation.md` - this document.

### Pipeline integration boundary

In `AutoPublishPipeline._render_visual_scene`, inside the `if structured_visual:` block,
after the V1.5 block and **before** `_stage_structured_visual` is called (runs
whenever the staging dict exists - V1.3/V1.4/V1.5/V1.6-A are optional):

```python
import src.services.character_variation as char_var_mod

if char_var_mod.VISUAL_CHARACTER_VARIATION_ENABLED:
    varied_characters, char_variation_decision = (
        char_var_mod.apply_character_variation(
            list(getattr(visual, "characters", []) or []),
            list(getattr(visual, "objects", []) or []),
            scene_index=max(int(scene_number) - 1, 0),
            total_scenes=total,
            scene_role=str(getattr(visual, "scene_role", "") or "general"),
            primary_focus=str(getattr(visual, "primary_focus", "") or "scene"),
            focus_target=variation_focus,
        )
    )
    if char_variation_decision.changed:
        varied_visual = copy.copy(visual)
        varied_visual.characters = varied_characters
        visual = varied_visual
visual_description = self._stage_structured_visual(visual, duration, transition_to_next)
if char_variation_decision is not None:
    visual_description["character_variation"] = char_variation_decision.to_dict()
```

The decision also surfaces on the render record and the `_render_scenes()` stage
result (`character_variation: True`) for pipeline-level observability.

## Feature flag

Independent flag (module-level in `src/services/character_variation.py`):

```python
VISUAL_CHARACTER_VARIATION_ENABLED = False
```

### OFF (default)

Existing behavior is byte-for-byte identical to V1.2-V1.6-A. No character
intent is added or modified; the decision object is never created.

### ON

Character staging/pose variation is applied where safe (see Precedence below).
5. **Existing renderer defaults** - used only when no higher rule applies.

## Deterministic strategy

No `random`, no timestamps, no UUIDs, no environment hashing. The layer uses
stable deterministic inputs:

- **Pose**: scene-role -> pose mapping (`ROLE_POSES`), restricted to
  `SUPPORTED_POSES`.
- **Scale**: structural constants (`PRIMARY_SCALE = 1.1`, `SUPPORTING_SCALE =
  0.85`) for multi-character scenes.
- **Position**: anchor hash over `(character name, scene role)` using
  `zlib.crc32`, drawn from `POSITION_ANCHORS = (0.3, 0.7)`.

Identical inputs always produce identical outputs.

## Continuity

Because anchors hash identity+role (not scene position), the same character in
the same scene role keeps the same staging across consecutive scenes; a role
change is the only thing that moves it. Pose is determined by scene role, so
role continuity produces pose continuity.

## Variation strategy

### Pose

Mapped from scene role via `ROLE_POSES`. Values are restricted to
`SUPPORTED_POSES` and mirror the semantic choices proven in
`examples/plan_visual_quality_v1.json` (hook -> surprised, object_interaction
-> point, explanation family -> talk). Roles not listed keep the renderer
default (`"idle"`). Pose is only assigned when the character has no explicit
`pose` key.

### Scale

Only applied in multi-character scenes and only when no explicit `scale` key
exists. The first character (or the V1.4 focus character, when identified)
receives `PRIMARY_SCALE` (1.1); supporting characters receive `SUPPORTING_SCALE`
(0.85). V1.2 presentation staging then multiplies by 1.25 for final framing.

### Position

Only when no explicit `x` key exists. Anchors are drawn from `POSITION_ANCHORS`
via a deterministic hash of `(character name, scene role)`. Candidates are
rejected if they conflict with an occupied position (object or already-staged
character) within a small tolerance. The first free anchor is used.

orientation variation is intentionally NOT attempted. Adding it would require
modifying the protected `stickman_renderer.py`.

## Semantic safety

- Variation operates only within semantically valid choices (role-driven poses
  from the proven vocabulary).
- Character-object relationships are respected: anchors are rejected if they
  conflict with object positions.
- Multi-character scenes avoid collisions: occupied positions block
  conflicting anchors.

## Focus / continuity handling

- V1.4 focus decisions (attention/camera `primary_target`) are read additively:
  the focus character is staged first and receives the primary scale. V1.4
  planner outputs are never modified.
- If V1.4 focus names a character in the scene, that character's scale
  assignment is verified against the primary scale.
- Continuity is preserved via identity+role hashing (see Deterministic
  strategy).

## Multi-character scenes

- The V1.4 focus character (when identified) is staged first and receives the
  primary scale.
- Supporting characters receive the supporting scale and are assigned anchors
  that avoid the focus character and objects.
- Simple deterministic collision avoidance: occupied `x` positions block
  conflicting anchors within a tolerance. No full collision detection is
  implemented (documented limitation).

## V1.6-A compatibility

V1.6-B and V1.6-A are fully independent:

- V1.6-B attaches `character_variation` to `visual_description`; V1.6-A attaches
  `background_variation`. Different keys, no overwrites.
- When both flags are ON, both layers coexist and the stage result reports both
  `character_variation: True` and `background_variation: True`.
- When V1.6-B is OFF and V1.6-A is ON, V1.6-A continues working unchanged.
- When both are OFF, existing V1.2-V1.5 behavior is byte-for-byte identical.

## Tests

- `tests/test_character_variation.py` - 20 unit tests covering determinism,
  explicit-intent preservation (position/scale/pose/orientation/motion),
  semantic compatibility, focus preservation, continuity, multi-character
  handling, single-valid-configuration, flag OFF/ON, immutability.
- `tests/test_character_variation_integration.py` - 8 pipeline-level tests
  covering the full flow ScenePlan -> V1.3 -> V1.4 -> V1.5 -> V1.6-A -> V1.6-B ->
  RenderJobSpec.

### Coverage matrix

| Scenario | Tests |
|---|---|
| Determinism | same input -> same result |
| Explicit position | preserved |
| Explicit scale | preserved |
| Explicit pose | preserved |
| Explicit orientation | preserved |
| Explicit motion | preserved |
| Semantic compatibility | invalid variation rejected |
| Focus preservation | V1.4 focus not contradicted |
| Continuity | valid continuity preserved |
| Multi-character | characters distinguishable |
| Single valid config | no failure |
| Flag OFF | existing behavior unchanged |
| Flag ON | variation observable |
| Immutability | inputs unchanged |
| V1.6-A compatibility | coexist without overwrite |

## Known limitations

- **No orientation/facing variation**: the renderer has no facing concept; adding
  it would require modifying the protected `stickman_renderer.py`.
- **No full collision detection**: multi-character scenes use a simple
  deterministic tolerance-based constraint, not a full packing solver.
- **Pose vocabulary restricted to `SUPPORTED_POSES`**: new poses require
  renderer support and must be added to the vocabulary first.
- **Continuity heuristic**: relies on identity+role hashing; no cross-scene
  continuity metadata is tracked beyond the deterministic hash.
- **Only default intent is varied**: scenes with fully explicit character
  intent are untouched by design.

## Future V1.6 work

- V1.6-C: (future)
- V1.6-D: (future)
- V1.6-E: (future)
- V1.6-F: visual QA system
- V1.6-G: (future)

### Orientation / facing

The renderer has no facing concept (limb drawing is symmetric or fixed), so
orientation variation is intentionally NOT attempted. Adding it would require
modifying the protected `stickman_renderer.py`.


## Decision precedence

From highest to lowest:

1. **Explicit scene/character intent** - a character dict key that is present
   (`pose`/`scale`/`x`) is *never* overwritten.
2. **Existing V1.4 focus decision** - the attention/camera focus character
   keeps priority in anchor assignment and receives the primary scale.
3. **Existing scene constraints** - objects and already-staged characters
   deterministically block conflicting anchors.
4. **V1.6-B variation** - role-driven pose, structural scale, hashed anchor.
5. **Existing renderer defaults** - used only when no higher rule applies.

  -> V1.5 application (optional)
  -> V1.6-A background variation (optional)
  -> _stage_structured_visual (V1.2 presentation staging)
      <- characters: pose/scale/x  (V1.6-B varies defaults BEFORE this)
      <- objects, environment, text_elements, effects, camera
  -> RenderJobSpec
  -> existing renderer (StickmanRenderer)
```

V1.6-B runs inside `_render_visual_scene`, after the structured visual is
detected and before `_stage_structured_visual` applies its authoritative
clamping/framing/clearance. The renderer consumes the staged dict unchanged.

## Relationship to V1.2-V1.6-A

| Layer | Role | Interaction with V1.6-B |
|---|---|---|
| V1.2/V1.2.1 structured staging | `_stage_structured_visual` | authoritative downstream; clamps/frames after V1.6-B assigns defaults |
| V1.3 semantic visuals | beats/focus/semantics | independent; V1.6-B runs with or without V1.3 |
| V1.4 planning stack | advisory metadata | V1.6-B reads focus decisions additively (never modifies them) |
| V1.5 application layer | applies V1.4 recommendations | independent; V1.6-B hooks before V1.2 staging |
| V1.6-A background variation | fills empty environments | independent; V1.6-B and V1.6-A attach to different keys |
| Renderer | `SUPPORTED_POSES` vocabulary | untouched; consumes staged characters as-is |
