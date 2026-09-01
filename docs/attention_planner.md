# Attention Continuity Planner (V1.4-E)

Deterministic, sequence-level planning of **visual attention continuity**:
what the viewer should be looking at in each scene, and how that attention
flows from one scene into the next.

> V1.4-E is currently a standalone planning layer and is not connected to the
> production rendering pipeline.

> Attention continuity describes *intended viewer focus*; it does not simulate
> rendered frames or guarantee actual viewer behavior.

## Purpose

V1.4-A planned *treatments*, V1.4-B *diversity*, V1.4-C *composition*, and
V1.4-D *camera motion*. V1.4-E completes the visual planning stack with the
last missing dimension: **attention**. For every scene it answers:

- What is the primary attention target (and secondary, when the scene
  legitimately supports one)?
- How does attention arrive from the previous scene and hand off to the next?
- Is the same target intentionally retained, or does it shift?
- Is a transition abrupt, and is continuity weak enough to warn about?

The planner is pure, read-only, deterministic, and advisory-only. It never
renders, never mutates its inputs, and never invents a target identifier.

## Relationship to other layers

| Layer | Relationship |
|---|---|
| V1.3-B `VisualFocusResolver` | Per-scene focus results are *consumed* when supplied (`focus_results`), never rerun. |
| V1.4-A `VisualStoryPlanner` | `story_plan` supplies beat type, treatment, and story-level focus targets. |
| V1.4-B `VisualDiversityPolicy` | `diversity_report` supplies repetition flags that refine diagnostics. |
| V1.4-C `CompositionPlanner` | `composition_plan` supplies composition type and dual-subject intent. |
| V1.4-D `CameraPlanner` | `camera_plan` supplies camera focus targets; camera intent is subordinate to explicit scene focus. |

None of these planners are invoked by V1.4-E; their outputs are optional
keyword-only inputs. V1.4-E runs standalone on plain scenes.

## Inputs

```python
AttentionPlanner().plan(
    scenes,                     # list[ScenePlan] (required)
    *, story_plan=None,         # VisualStoryPlan   (V1.4-A)
    diversity_report=None,      # VisualDiversityReport (V1.4-B)
    composition_plan=None,      # CompositionPlan   (V1.4-C)
    camera_plan=None,           # CameraPlan        (V1.4-D)
    focus_results=None,         # {scene_index: VisualFocus} (V1.3-B results)
)
```

## Outputs

- `AttentionDecision` (frozen dataclass, one per scene):
  `scene_index`, `primary_target`, `secondary_target`, `target_kind`,
  `handoff_from_previous`, `handoff_to_next`, `retained_from_previous`,
  `target_changed`, `explicit_focus_preserved`, `warnings`.
- `AttentionPlan` (frozen dataclass): `decisions` tuple + sequence-level
  `warnings`. Both expose `to_dict()` for JSON serialization.

Target kinds are `character`, `object`, `text`, or `scene` (the safe
scene-level fallback). A target is always an identifier that already exists in
the supplied scene, or `None` / `"scene"` when no valid target exists.

## Attention continuity states

`SUPPORTED_HANDOFF_STATES` (also used for `handoff_to_next`):

| State | Meaning |
|---|---|
| `established` | First scene with a target (nothing came before). |
| `retained` | Same target as the previous scene. |
| `shifted` | Different target than the previous scene. |
| `introduced` | First target after previous scene(s) had none. |
| `returned` | Target reappears after being absent for at least one scene. |
| `lost` | Previous scene had a target, this scene has none. |
| `fallback` | No valid target exists (primary target is `None`). |

`retained_from_previous` mirrors the `retained` state; `target_changed` is
true for `shifted` and `returned`.

## Primary target resolution

Strict precedence — the first level that yields a *real* scene element wins:

1. **Explicit scene focus intent** (`visual.primary_focus` or
   `camera_spec.focus_target`, excluding the no-intent default `"scene"`) —
   always wins, never replaced.
2. **Existing VisualFocusResolver result** (V1.3-B `focus_results`).
3. **Explicit camera focus target** (V1.4-D); the camera-level `"scene"`
   target is not an element and falls through.
4. **V1.4-C composition primary subject** (composition-type kind preference,
   then `subject_regions`).
5. **V1.4-A story treatment / beat** (treatment kind preference, then the
   story focus target when it names a real element).
6. **Existing scene subject ordering** (characters, then objects, then text).
7. **Safe scene-level fallback** (`"scene"`, only when the scene carries
   visual intent but has no named subjects); otherwise `primary_target=None`.

## Secondary target resolution

A secondary target exists only when scene data legitimately supports one:

1. Dual-subject compositions (`comparison`, `subject_support`) — the first
   distinct element becomes the secondary; a comparison with a single valid
   subject is *not* collapsed into a fake pair.
2. A `VisualFocus.secondary` that names a real, distinct element.
3. Otherwise `None`.

The secondary never duplicates the primary and is never invented.

## Handoff behavior

Attention flow between adjacent scenes is derived from resolved targets:

- `hero -> hero` → `retained` (`retained_from_previous=True`)
- `hero -> book` → `shifted` (`target_changed=True`)
- `None -> hero` → `introduced`
- `hero -> book -> hero` → scene 3 reports `returned` (see below)
- `hero -> None` → `lost`
- no target at all → `fallback`

`handoff_to_next` of scene *i* always mirrors `handoff_from_previous` of
scene *i + 1*; the final scene carries a deterministic `established`
placeholder because it has no next scene.

## Return-to-previous-target behavior

The planner tracks every target seen in earlier scenes. When a scene resolves
to a target that was absent for at least one intervening scene, the handoff is
`returned` (instead of `shifted`) and an `attention_returned:<target>`
warning is emitted. This is a *diagnostic*, not a correction: narrative
returns are legitimate and are never rewritten.

## Warning / diagnostic semantics

All warnings are deterministic strings derived only from inputs. Per scene:

| Warning | Meaning |
|---|---|
| `explicit_focus_preserved` | Scene carried explicit focus intent and it was honored. |
| `explicit_focus_repetition` | Explicit focus names the same target as the previous scene. |
| `explicit_focus_unresolved` | Explicit focus names no existing element (never invented around it). |
| `repeated_attention:<target>` | Same target as the previous scene (informational). |
| `extended_attention_run:<target>:<n>` | Target held for *n* consecutive scenes (n ≥ 3). |
| `attention_returned:<target>` | Target returned after an absence. |
| `scene_level_fallback` | Scene-level `"scene"` fallback used. |
| `no_target_found` | No valid target exists for the scene. |
| `comparison_dual_targets` | Dual-subject composition resolved a primary + secondary pair. |
| `attention_diversity_recommendation:<target>` | A legitimate secondary target exists and diversity flags suggest variation (advisory only). |
| `diversity_confirms_focus_repetition` | V1.4-B independently confirms focus repetition. |

Sequence level: `low_attention_diversity` when attention runs make the
sequence visually monotone.

## Explicit-intent precedence

If a scene explicitly identifies its visual focus, `explicit_focus_preserved`
is true and the intent is never replaced — not by diversity, composition,
camera continuity, story treatment, or previous-scene continuity. The planner
may still *report* (e.g. `explicit_focus_repetition`) but always preserves
explicit intent. An explicit focus that names nothing real is never silently
rewritten either: the planner falls through the normal precedence and flags
`explicit_focus_unresolved`.

## Treatment awareness (V1.4-A)

Treatments bias *which kind* of target is preferred (planning rules only):

| Treatment | Preferred target kinds |
|---|---|
| `establish` | scene-level or broad primary target |
| `problem_focus` | character → object → text |
| `compare` | two complementary targets |
| `explain` | object → character → text |
| `proof` | text → object |
| `solution_growth` | object → character |
| `cta` | text → character |

## Composition awareness (V1.4-C)

- `comparison` / `subject_support` → primary + secondary dual targets when
  two valid subjects exist.
- `text_led` → text preferred as primary when valid.
- `object_led` → object preferred as primary.
- `single_subject` / `problem_focus` / `solution_result` → composition-type
  kind preferences; unknown compositions fall back to `subject_regions`.

## Camera awareness (V1.4-D)

A camera focus target of `focus_on_character` / `focus_on_object` resolves to
that element when it exists. Camera intent is subordinate to explicit scene
focus, and a camera target that names no real element (including the
scene-level `"scene"` value) never forces a target.

## Diversity awareness (V1.4-B)

Attention repetition is *diagnosed, not forced away*. A long run of the same
target yields `extended_attention_run:<target>:<n>` diagnostics. A different
target is only *recommended* (`attention_diversity_recommendation:<target>`)
when a legitimate secondary target exists and diversity flags / story intent
permit it. Narrative correctness always outranks forced diversity.

## Determinism guarantees

- No randomness, time, UUIDs, network, LLM, FFmpeg, or renderer access.
- Fixed iteration order and fixed precedence everywhere.
- Identical inputs always produce identical `plan.to_dict()` output.
- All collections in outputs are tuples; all warnings are sorted-free,
  generation-ordered strings.

## No-mutation guarantee

The planner never mutates `ScenePlan`, `VisualScene`, `VisualStoryPlan`,
`VisualDiversityReport`, `CompositionPlan`, or `CameraPlan`. Inputs are read
through field access only; this is enforced by tests that snapshot inputs
before and after planning.

## Current limitations

- Standalone advisory layer: nothing consumes `AttentionPlan` yet, so its
  output has no effect on rendering.
- Targets are name-based: two distinct characters sharing the same name are
  indistinguishable at the attention level.
- `handoff_to_next` on the final scene is a fixed `established` placeholder
  (no next scene exists).
- Handoff states describe adjacent-scene relationships only; there is no
  notion of attention *duration* beyond consecutive-run counting.
- Cross-scene identity is lexical: `"Hero"` and `"hero"` match, but a renamed
  character across scenes reads as a shift, not a return.

## Future integration point

The natural consumer is the same downstream integration point planned for the
other V1.4 planners: a pipeline stage that runs the planning stack
(A → B → C → D → E) and passes the resulting advisory metadata into rendering
decisions. Suggested shape:

```python
attention_plan = AttentionPlanner().plan(
    scenes,
    story_plan=story_plan,             # V1.4-A
    diversity_report=diversity_report, # V1.4-B
    composition_plan=composition_plan, # V1.4-C
    camera_plan=camera_plan,           # V1.4-D
    focus_results=focus_results,       # V1.3-B results
)
```

No pipeline, renderer, schema, or media changes are included in V1.4-E.
