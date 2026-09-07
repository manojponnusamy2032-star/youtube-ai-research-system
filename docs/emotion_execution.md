# V1.6-F — Character Emotion Execution

## Purpose

V1.6-F activates the renderer's existing, previously undriven character
emotion system. Every character previously rendered with the identical
neutral posture and untinted color regardless of narrative context; the
emotional layer of stickman storytelling (tension on the problem, focus
during explanation, energy on the hook/CTA) was invisible.

The renderer already fully supports emotion:

* `scene_composition.SUPPORTED_EMOTIONS` — `neutral, happy, frustrated,
  focused, surprised, sad, excited`
* `scene_composition.EMOTION_TINTS` — per-emotion color, blended at 25% into
  the character base color (`color_with_emotion`)
* `stickman_renderer._compute_pose` — per-emotion posture cues
* `CharacterSpec.emotion` — validated/normalized pass-through, built
  directly from each staged character dict (`CharacterSpec(**c)`)

V1.6-F is an **execution layer**: it derives a deterministic per-scene
`emotion` for the character the scene is emotionally about (the V1.4-E
attention primary target) from planner-authoritative semantics, and stages
it as an additive `emotion` key on that single character dict. No renderer,
model, or planner code changes.

## Pipeline position

```
V1.6-D Camera Execution
  → V1.6-E Scene Choreography
  → V1.6-F Emotion Execution   (NEW)
  → RenderJobSpec
  → build_scene_composition → CharacterSpec(**c) (emotion flows through)
  → StickmanRenderer (tint + posture)
```

## Feature flag

`VISUAL_EMOTION_EXECUTION_ENABLED = False` (in `src/services/emotion_execution.py`).

When OFF the layer returns the caller's character list unchanged (same
objects), adds no `emotion` keys and no metadata — the pipeline path is
byte-identical to the pre-V1.6-F behavior.

## Precedence (highest → lowest)

1. Explicitly authored `emotion` on a character dict — never modified or
   duplicated; the bearer keeps its authored value (`source="explicit"`).
2. V1.4 story treatment: `visual_planning["story"]["treatment"]`.
3. V1.3 beat type: `visual_planning["beat"]["type"]`.
4. V1.3 scene role (deterministic fallback).
5. `neutral` (existing renderer default; non-bearers always stay here).

## Mapping tables (fixed, deterministic)

Treatment (`TREATMENT_EMOTIONS`):

| treatment | emotion |
|---|---|
| establish | excited |
| problem_focus | frustrated |
| compare | surprised |
| explain | focused |
| proof | focused |
| solution_growth | happy |
| cta | excited |

Beat (`BEAT_EMOTIONS`): hook→excited, problem→frustrated, contrast→surprised,
explanation→focused, example→focused, solution→happy, cta→excited.

Role fallback (`ROLE_EMOTIONS`): hook→excited, explanation→focused,
conclusion→excited, cta→excited, otherwise→neutral.

## Semantic correctness over variety

**No forced alternation.** When two consecutive scenes legitimately map to
the same emotion (e.g. two `problem_focus` scenes → `frustrated`), the same
emotion is staged in both. There is no sequence-level variation machinery.

## Determinism

No `random`, UUIDs, timestamps, or global mutable state. Pure lookup tables
keyed by normalized (lowercased, stripped) vocabulary values. Target
selection matches the normalized attention target name against the declared
character order (first match wins). Unknown vocabulary values normalize to
`neutral`. Identical inputs produce identical staged lists and identical
decision dicts.

## Additivity and safety

* Input character dicts are never mutated: the bearer's dict is
  shallow-copied with `emotion` added; all other members pass through as the
  same objects. The caller's list is never modified (a new list is returned).
* Exactly one emotion-bearer per scene (the attention target, only when it
  is a character present in the scene). Non-target characters and objects
  are untouched.
* Every generated value is validated against `SUPPORTED_EMOTIONS`, so it is
  always compatible with `CharacterSpec(**character_dict)`.
* Malformed planning metadata, object attention targets, missing targets,
  empty/malformed scenes, and unknown vocabulary values all resolve to a
  safe skip or `neutral` with a warning — the layer never raises.
* `visual_description["camera"]` and all V1.6-A/B/C/D/E metadata are never
  touched.

## Metadata

When enabled and a decision is applied:

* `visual_description["emotion_execution"]` — decision dict
  (`scene_index`, `bearer`, `emotion`, `source`, `changed`, `skipped`,
  `reason`, `warnings`)
* `record["emotion_execution"]` — same decision on the render record
* `stage_result["emotion_execution"] = True` — when any scene applied

When disabled or when no emotion action is produced, none of these keys
appear (no misleading metadata).

## Tests

* `tests/test_emotion_execution.py` — 38 focused unit tests
* `tests/test_emotion_execution_integration.py` — 8 pipeline integration
  tests, including `SceneComposition.from_visual_description` verification
  that the emotion reaches `CharacterSpec`.
* `output/v16f_validation/validate_emotion_render.py` — minimal OFF/ON
  real-render validation with character-region frame-difference evidence.
