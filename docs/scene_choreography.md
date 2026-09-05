# V1.6-E — Scene Choreography

## Purpose

V1.6-A/B/C/D added environment, character, motion, and camera layers. V1.6-E
coordinates them into coherent **scene choreography**: deterministic
cast-delta entrances, non-cut exits, attention-aware emphasis, and
transition-aware settling — strictly append-only on top of the existing
motion list.

```
V1.3 beats/focus ─┐
V1.4 planning ────┼─→ semantic_context
V1.5 application ─┘
        ↓
V1.6-A/B/C/D (existing, untouched)
        ↓
V1.6-E scene choreography (this layer)
        ↓
RenderJobSpec → renderer (existing enter/exit/scale execution)
```

## Feature flag

```python
# src/services/scene_choreography.py
VISUAL_CHOREOGRAPHY_ENABLED = False  # default OFF
```

- **OFF**: `apply_scene_choreography` returns the original motions unchanged
  (same objects), adds no metadata, and the pipeline path is identical to the
  V1.6-D state.
- **ON**: new `Motion` entries are appended; nothing existing is mutated,
  retimed, or reordered.

## What it does

1. **Cast-delta detection** — `collect_cast_names` builds a
   `(kind, name)` set per scene; `previous_cast` / `next_cast` are threaded
   across the sequence (pipeline: `_render_scenes`).
2. **Entrances** — a member in the current scene but absent from the previous
   scene receives one `enter` in the lead-in window (start `0.0`, width
   `max(0.55s, min(0.22·duration, 1.2s))`) unless the window already has a
   motion for that target. Scene 1 is a deliberate cold open (empty previous
   cast).
3. **Exits** — a member absent from the next scene receives one `exit` in the
   tail window (`end − width`), only when the transition to the next scene is
   **not** a cut.
4. **Attention-aware emphasis** — one short `scale` (≤1.0s) on the V1.4-E
   attention primary target (fallback: V1.6-D `focus_on_*` camera focus),
   only when the emphasis window (`[max(0.55·d, 0.5), min(0.85·d, d−0.25)]`)
   is free of motions for that target.
5. **Transition-aware settling** — under a non-cut transition, retained
   members with motions still active in the tail are reported
   (`unsettled_tail_motion` warnings); existing motions are never rewritten.

## Precedence (highest → lowest)

1. Explicit authored motions (never retimed/duplicated)
2. Explicit legacy character actions / camera instructions
3. V1.4-E attention + V1.4-A treatment + V1.4-C composition (read-only)
4. V1.6-D camera spec (read-only: focus/duration)
5. V1.6-C / V1.3 semantic motions (window-absence guards)
6. V1.6-E fill-only choreography (`label` prefix `v1.6-e:`)
7. Existing renderer defaults

## Determinism

No `random`, no UUIDs, no timestamps, no global mutable state. Entrance side:
authored `x < 0.5` → `left`, else `right`; camera-focus side fallback; safe
`left` default. All windows are fixed-ratio constants rounded to 3 decimals.
Identical inputs produce identical decisions (verified by tests).

## Safety

Invalid duration (≤0/NaN/inf), unknown targets, window conflicts, and
oversized windows are skipped with a warning (`decision.warnings`); the
function never raises. Every generated motion is validated with
`Motion.validate(scene_duration)` before being appended. Empty scenes are
safe.

## Metadata

- `visual_description["choreography"]` — `ChoreographyDecision.to_dict()`
- render record `record["choreography"]`
- stage result `stage_result["choreography"] = True` (when any scene applied)

## Files

- `src/services/scene_choreography.py` — the layer
- `src/pipeline/auto_publish_pipeline.py` — wiring only
- `tests/test_scene_choreography.py`, `tests/test_scene_choreography_integration.py`
- `output/v16e_validation/validate_choreography_render.py` — OFF/ON real render
