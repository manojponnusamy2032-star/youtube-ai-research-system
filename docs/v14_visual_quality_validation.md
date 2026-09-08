# V1.4-G: End-to-End Visual Quality Validation Report

Validation of the integrated V1.4 planning stack (V1.4-A through V1.4-F).
Controlled A/B run of one deterministic 7-scene scenario through the real
pipeline (real FFmpeg renders), V1.4 OFF vs V1.4 ON, with full artifact
capture and pixel-level frame comparison.

Artifacts (gitignored): `output/v14g_validation/`
(`run_validation.py`, `baseline_v14_off/`, `v14_on/`, `comparison.json`).

## 1. Test environment

| Item | Value |
|---|---|
| Commit SHA | `829ef37e91e9475431b0a77732eecbe8605da912` + uncommitted V1.4-F (`src/pipeline/auto_publish_pipeline.py`, integration tests, doc) |
| Python | 3.13.7 |
| FFmpeg / FFprobe | 8.1.2 (gyan.dev full build) |
| Renderer | StickmanRenderer (structured scenes), SceneVideoRenderer (captions), VideoAssembler, MediaMuxer — all real executions |
| TTS | Deterministic synthetic WAV (220.5 Hz sine, 3.0 s/scene) injected via the pipeline's TTS injection point; Piper not required |
| Resolution | 1080×1920 (SHORTS_FORMAT, 9:16) |
| FPS | 30 |
| Scenario | 7 scenes: HOOK (character) → PROBLEM (explicit camera `static`+`focus_target`, explicit scale motion, explicit `fade`) → EXPLANATION (objects) → CONTRAST (two subjects, explicit `crossfade`) → EXAMPLE (objects, text-led) → SOLUTION (new character, explicit camera `slow_zoom_in`) → CTA (attention return, explicit `fade_to_black`) |
| Scene duration | 3.0 s narration + 0.4 s padding per scene |

## 2. Baseline (V1.4 OFF: `SEMANTIC_VISUALS_ENABLED=True`, `VISUAL_STORY_PLANNER_ENABLED=False`)

Existing V1.3 behavior only. Per scene: beat + focus from the V1.3 engine,
semantic motions, derived transitions (only where no explicit transition).
Effective camera per scene: `hold, static, hold, hold, hold, slow_zoom_in,
hold` — 3 unique patterns, longest run 3 (four consecutive `hold` scenes).
No planning metadata exists anywhere in the pipeline.

## 3. V1.4 result (both flags True)

Everything from the baseline, plus per-scene `visual_planning` metadata from
the full A–E stack: story treatment, diversity flags, composition type,
camera continuity, attention handoffs. The plans are advisory: they reach
staging as metadata and change no render input.

## 4. Quantitative comparison

| Metric | V1.4 OFF | V1.4 ON (effective) | V1.4 ON (advisory plans) |
| --- | ---: | ---: | ---: |
| Unique camera patterns | 3 | 3 | **5** |
| Longest camera run | 3 | 3 | 2 |
| Continuity states (established/held/changed/reversed) | n/a | n/a | 1/2/3/1 |
| Explicit camera preserved | n/a | yes (scenes 2, 6) | yes (planner flags true) |
| Unique composition types | n/a | unchanged | **7** (0 consecutive repeats) |
| Unique attention targets | 5 | 5 | 5 |
| Attention shifts / returns | 5 / 1 | 5 / 1 | 5 / 1 |
| Longest attention run | 2 | 2 | 2 |
| Scenes flagged visually repetitive | untracked | untracked | 6 of 7 (4 camera, 6 focus-pattern) |
| Repeated treatments | untracked | untracked | 1 (of 7 unique treatments) |
| Camera+composition combo repeats | n/a | n/a | 0 |
| Explicit intent violations | 0 | **0** | 0 |
| Invalid vocabulary | 0 | 0 | 0 |
| Invented targets | 0 | 0 | 0 |

Key reading: the *rendered* camera work is identical (advisory stack), while
the advisory camera plan proposes 5 patterns with a longest run of 2 over the
baseline's hold-heavy 3-run — i.e. V1.4 quantifies exactly the diversity the
baseline lacks (6/7 scenes flagged repetitive, mostly repeated `hold` camera
and repeated focus pattern).

## 5. Render integrity

Both runs: `status=completed`, no FFmpeg errors.

| Check | V1.4 OFF | V1.4 ON |
| --- | --- | --- |
| File exists / playable MP4 | yes (`final_with_audio.mp4`, 654,629 bytes) | yes (654,629 bytes) |
| Video stream | h264 High 4:4:4, 1080×1920, 30 fps, 599 frames | identical |
| Audio stream | AAC LC mono 22.05 kHz | identical |
| Duration | 19.966 s | 19.966 s |
| Frame MD5 at 7 per-scene midpoints | 7/7 | **7/7 identical to OFF** |
| Plan snapshot / scene count / durations | — | identical to OFF |

Pixel-identical output confirms the advisory-only contract end-to-end.

## 6. Visual inspection (same timestamps both versions — frames identical)

- **Scene 1 (HOOK, 1.4 s):** standing guide character left-of-center, palace
  gate object right, "Memory Palace" headline — clear establish shot.
- **Scene 2 (PROBLEM, 4.3 s):** explicit static camera on guide with desk and
  book; explicit scale motion on the character renders (motion trails
  visible). Composition matches narration.
- **Scene 3 (EXPLANATION, 7.1 s):** map/shelf objects with "Place It"; a
  seated stickman appears although no character was authored — the V1.3
  semantic motion lowerer introduces a default subject (existing behavior,
  see §7).
- **Scene 4 (CONTRAST, 10.0 s):** two figures present as intended, but they
  sit close together near center — V1.2 staging pulls subjects toward the
  central band (existing behavior, see §7).
- **Scene 6 (SOLUTION, 15.7 s):** the explicit `slow_zoom_in` camera is
  visibly tighter than neighboring scenes — explicit camera intent works and
  matters here.
- **Scene 7 (CTA, 18.6 s):** guide returns with "Subscribe" text and the
  explicit fade-to-black — coherent close.
- Sequence-level: each scene has a distinct subject arrangement, so framing
  is not literally repeated; however the fixed sky/ground/sun background and
  the recurring left-side motion-trail motif repeat in all scenes, and the
  four consecutive `hold` scenes make the middle of the video visually
  flatter than the advisory camera plan's pan/zoom suggestions would be.
- Attention flow (guide → objects → two-subject → objects → mentor → guide)
  tracks the narration and the return lands intentionally.

## 7. Problems discovered

- **Real V1.4 defects:** none found. Recommendations are deterministic,
  use only supported vocabulary, never invent targets, and never override
  explicit intent (0 violations across all 7 scenes, all safety checks).
- **Architectural (by design, documented):** V1.4-F is an advisory metadata
  layer — enabling V1.4 does not change rendered pixels. The measured
  diversity/continuity improvements exist only in the plans. Visible
  improvement requires a future application layer that consumes
  `visual_planning` metadata during staging (separate task; not attempted
  here per V1.4-G scope).
- **Existing V1.2/V1.3 behavior (not V1.4):** (a) V1.3 semantic motions
  introduce a default stickman in the character-free EXPLANATION scene;
  (b) V1.2 staging clusters the two CONTRAST subjects near center;
  (c) fixed background/motif repeats across scenes.
- **Test/environment notes:** real renders are CPU-heavy (~5 min/run cold);
  per-variant audio paths differ by directory (normalized in comparison);
  one validation-script comparison bug (unstripped metadata key) was found
  and fixed during measurement — it affected the harness, not the product.

## 8. Recommendation

```text
V1.4 READY FOR PRODUCTION INTEGRATION
```

The stack integrates cleanly behind its disabled-by-default flag with zero
regressions (280 V1.4 + 227 V1.2/V1.3 tests), zero explicit-intent
violations, valid deterministic recommendations, and bit-identical rendering
when enabled. It ships as a safe advisory layer; converting its
recommendations into visible visual improvements is a separate, follow-up
task that consumes the `visual_planning` metadata at staging time.