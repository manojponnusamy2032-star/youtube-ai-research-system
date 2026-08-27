# Visual Focus Resolver (V1.3-B) — developer note

Converts a `VisualBeat` (V1.3-A) plus available scene composition elements into a
**deterministic attention hierarchy** (`VisualFocus`).  This layer says **WHAT**
deserves the viewer's attention; it never says HOW to animate it (that is V1.3-C /
later staging).

## Supported beat types
HOOK, PROBLEM, CONTRAST, EXPLANATION, EXAMPLE, SOLUTION, CTA (the V1.3-A seven-beat
vocabulary).  Unknown/empty beat types default to `medium` emphasis.

## VisualFocus fields
- `primary` — first thing the viewer should notice (an existing element name/text).
- `secondary` — next-most-important (used by CONTRAST to hold two sides).
- `supporting` — visible-but-subordinate elements.
- `background` — elements that should visually recede.
- `emphasis_target` — element singled out for the strongest emphasis.
- `deemphasis_targets` — elements to not compete with the primary.
- `emphasis` — `low`/`medium`/`high`, carried over from the beat.
- `timing` — left empty unless reliably derivable (not invented here).

## Resolution priority
1. Explicit existing `primary_focus` / camera `focus_target` **only if it names a real candidate** (no invention).
2. Beat `subject` matched to a real scene element.
3. Beat-aware rules (e.g. CONTRAST splits `"A vs B"` into primary + secondary; CTA prefers a text element).
4. First meaningful scene element fills the remaining hierarchy slots.
5. Empty fallback (`primary == ""`) when no element exists.

## Subject extraction / matching behavior
- `subject` is matched against character/object `name` and text element `text`
  using a normalized, order-insensitive substring test (alphanumerics + spaces only).
- Matching is **never hallucinatory**: an unmatched subject produces no invented
  primary — resolution falls back to the first existing element.
- Beat `emphasis` is always carried to `VisualFocus.emphasis`, even with no elements.

## Fallback behavior
- Empty scene → `VisualFocus(emphasis=<from beat>)`, `primary == ""`.
- Missing optional `Analysis`/`primary_focus`/`focus_target` → treated as absent.
- Dict specs (e.g. `{"name": ...}`) are accepted alongside real spec dataclasses.

## How integrated layers consume `VisualFocus`
- **V1.3-C (Semantic Motion):** read `emphasis_target`/`deemphasis_targets` to emit
  existing `Motion(scale)` / `EffectSpec(highlight|spotlight)` primitives.  This resolver
  does *not* emit them.
- **V1.3-D (Transitions):** use `primary`/`secondary` + the originating beat to drive
  transition choice (e.g. two sides → contrast transition).
- **V1.3-E (Visual QA):** treat `primary == ""` on a non-empty scene, or a `primary` that
  matches nothing in the composition, as a composition failure worth flagging.

## Non-goals / hard boundaries (do not break these)
- Never imports `StickmanRenderer` or `FFmpeg`; no network/LLM.
- Never mutates `VisualScene`, `SceneComposition`, or any spec.
- Identical inputs always produce identical outputs (deterministic).
- V1.3-F consumes this layer only when `SEMANTIC_VISUALS_ENABLED` is true; the
  default V1.2 rendering path remains unchanged.
