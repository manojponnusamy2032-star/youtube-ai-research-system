# Semantic Motion Lowerer

`SemanticMotionSpec` describes a subject, semantic intent, and timing. `SemanticMotionLowerer` converts that derived metadata into existing `Motion` and optional `EffectSpec` values. It is isolated from rendering and does not persist or resolve focus.

## Intent vocabulary

- `emphasize`: scale up the validated subject; optional highlight effect
- `reveal`: fade in; optional camera zoom
- `reveal_decline`: fade in and scale down
- `emphasize_growth`: scale up farther than emphasis
- `compare`: enter explicitly supplied subjects from opposite sides
- `transform`: exit `from_subject`, then enter `to_subject`
- `point_to`: move a character or pan a camera when valid coordinates are supplied
- `isolate`: scale the primary subject and optionally fade focus deemphasis targets
- `accumulate`: enter explicitly supplied subjects
- `remove`: exit the subject
- `transition_attention`: fade, or pan the camera when coordinates are supplied

All emitted values are constructed by the existing model classes and therefore use their supported type and easing vocabularies. Effects are opt-in with `parameters={"effect": True}` or an existing `effect_type`.

## Beat to motion

`VisualBeat` describes why a visual beat exists. `VisualFocus` identifies existing scene elements that deserve attention. `SemanticMotionSpec` describes how to express that attention. The lowerer accepts focus as an optional input but does not resolve or mutate it.

Targets must be supplied through `characters`, `objects`, `text`, or the explicit `targets` mapping. Unknown subjects produce an empty result; unsupported or under-specified operations also produce no invented primitive. Lowering is deterministic and preserves `start_time` and the supplied positive `duration` (or uses the intent's deterministic default).
