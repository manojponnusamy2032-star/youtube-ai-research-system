# Visual Beat Engine (V1.3-A)

Deterministic narration → visual beat detection. Pure semantic service; no
rendering, LLM, or network dependency. Lives in `src/services/visual_beat_engine.py`.

## Supported beat types

`HOOK`, `PROBLEM`, `CONTRAST`, `EXPLANATION`, `EXAMPLE`, `SOLUTION`, `CTA`.

`REVEAL`, `TRANSFORMATION`, `CONSEQUENCE`, `SUMMARY` are intentionally not
implemented — map them onto the seven beats above (e.g. REVEAL → CONTRAST or
SOLUTION).

## Detection priority

For each scene, the first rule that produces a beat wins:

1. **Explicit `scene_role` metadata** — e.g. `hook` → HOOK, `problem` → PROBLEM,
   `explanation` → EXPLANATION, `method`/`solution` → SOLUTION, `cta` → CTA,
   `proof`/`comparison`/`contrast` → CONTRAST, `example`/`b_roll` → EXAMPLE.
2. **Scene position** — first scene → HOOK, last scene → CTA.
3. **Strong semantic keywords** in narration (small curated tuples, ordered
   HOOK → CTA → PROBLEM → SOLUTION → CONTRAST → EXAMPLE → EXPLANATION).
4. **`Analysis.story_structure`** — used only when narration yields no beat.
5. **Fallback** — `EXPLANATION`.

## Subject extraction

Conservative, never hallucinated:

- `CONTRAST`: "A vs B" → `subject="a vs b"`; "X does not mean Y" →
  `"x vs y"` (e.g. "study vs memory").
- `PROBLEM` / `SOLUTION`: "the problem is that focus drops …" → `"focus"`.
- Otherwise falls back to `Analysis.main_topic` (first 5 words) or `""`.

## Fallback behavior

- `scene_role` present → role wins regardless of position/keywords.
- Empty/whitespace narration mid-plan → fallback (`EXPLANATION`) or position
  rule (first/last).
- Missing/malformed `Analysis` fields (None/empty/partial dict) degrade to
  narration-only operation without raising.

## Examples

```python
engine = VisualBeatEngine()
engine.detect("The problem is that focus drops.", scene_index=2, total_scenes=5)
# VisualBeat(type="PROBLEM", subject="focus", importance=0.9, emphasis="high")

engine.detect("Studying longer does not mean you remember more.",
              scene_index=4, total_scenes=10)
# VisualBeat(type="CONTRAST", subject="study vs memory", importance=0.85, emphasis="high")
```

Use `detect_sequence(scenes, analysis=...)` for an ordered plan.

## Consuming `VisualBeat` (V1.3-B/C/D/F)

`VisualBeat` is a stable, serializable `@dataclass` (`type`, `subject`,
`importance` in 0..1, `emphasis` low/medium/high) with a `to_dict()`. Layers
should treat it as read-only metadata:

- **Visual Focus (B):** `subject`/`type` → primary focus & emphasis target.
- **Semantic Motion (C):** `type` + `subject` → `MotionIntent`/primitives.
- **Transitions (D):** adjacent `VisualBeat.type` pairs → `Transition`.
- **Visual QA (E):** validate staged composition geometry through the report-only QA service.

Do not mutate beats; do not store them as required schema fields.
