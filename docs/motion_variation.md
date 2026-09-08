# V1.6-C - Motion Visual Richness

V1.6-C is a deterministic staging layer that adds one scene-aware motion
primitive when a structured scene has no explicit motion for the selected
target. It reuses the existing `Motion` model and renderer vocabulary; it does
not add renderer commands or change the rendering architecture.

## Feature flag

```python
VISUAL_MOTION_VARIATION_ENABLED = False
```

The flag is defined in `src/services/motion_variation.py` and defaults to
`False`. With the flag OFF, the original motion list and render path are
unchanged.

## Precedence

1. Explicit structured scene motions and existing semantic/planning motions.
2. Explicit legacy character actions.
3. Scene role, focus, available characters, and available objects.
4. V1.6-C deterministic motion selection.
5. Existing renderer defaults.

The service appends only validated `Motion` instances, and only when the
selected target has no explicit motion. It never mutates scene inputs.

## Selection

Role-aware intents use supported primitives only: hook/problem reactions and
emphasis, explanation emphasis, object-interaction object scaling,
character-action movement, transformation reveal/emphasis, and payoff/CTA
gestures or emphasis. Timing is derived from scene duration and uses a stable
`ease_in_out` easing. Scene index selects among compatible intent alternatives
without global randomness.

The decision is exposed as `visual_description["motion_variation"]`, on the
render record, and at pipeline stage level when the flag is enabled.

## Compatibility

V1.6-C runs after V1.6-A background and V1.6-B character staging. The layers
write separate metadata and operate on different concerns. V1.4/V1.5 motions
remain in the existing motion list and win over V1.6-C for their targets.
