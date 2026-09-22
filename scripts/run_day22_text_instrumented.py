"""Day-22 instrumented text-path counting run (measurement-only, no production edits).

Runs the SAME canonical workload as the Day-22 baseline (the saved Day-11/12
six-scene plan, identical plan bytes / 1860 frames / 1920x1080 @30fps) through
the REAL renderer per-frame core:

    _evaluate_motion_state -> _resolve_named_characters -> _compute_pose ->
    _generate_frame -> _draw_text_elements

with TextPathProbe (scripts/day22_instrumentation.py) installed on top.

The frame-generation loop is an in-memory mirror of
StickmanRenderer._generate_animation (src/services/stickman_renderer.py
lines 1013-1048): it calls the real per-frame methods with the real
per-scene job/motion/composition state, but writes each generated frame to a
discarded bytearray instead of piping it through FFmpeg. The audio/TTS and
video-mux stages are intentionally excluded because they are NOT part of the
text-rendering path under investigation; the frame-generation code path is
the same one the canonical benchmark exercises.

Purpose:
  * aggregate operation counts + per-op timings for the text path,
  * characterize repetition of font-load, textlength and rendered-glyph keys
    to judge whether a narrowly-scoped cache is justified.

Usage:  python scripts/run_day22_text_instrumented.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.content_package import RenderConfig  # noqa: E402
from src.services.scene_composition import SceneComposition  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

from scripts.day22_instrumentation import TextPathProbe  # noqa: E402

PLAN_PATH = ROOT / "output" / "day12_profiling" / "jobs" / "job_001" / "visual_plan.json"
PLAN_SHA256 = "9a269915f3ce680a83c50c25fbca2a19d4d2d60a0f9f794895b46ea945632392"
WIDTH, HEIGHT, FPS = 1920, 1080, 30
OUT_DIR = ROOT / "output" / "day22_profiling" / "instrumented"


def _render_job_frames(renderer, job, probe):
    """Mirror _generate_animation's per-frame loop, in memory, probe active."""
    config = RenderConfig(width=WIDTH, height=HEIGHT, fps=FPS)
    width, height, fps = config.width, config.height, config.fps
    duration = int(job.get("duration_seconds", 1))
    total_frames = duration * fps
    composition = SceneComposition.from_visual_description(job.get("visual_description"))
    action = renderer._detect_action(job)
    request = types.SimpleNamespace(motions=job.get("motions", []), job=job)
    motion_list = renderer._collect_motions(request)
    camera_instructions = str(job.get("camera_instructions", ""))

    probe.scene(job.get("job_id", "unknown"))
    for frame_idx in range(total_frames):
        t = frame_idx / fps
        motion_state = renderer._evaluate_motion_state(
            motion_list, t, float(duration), width, height, action,
            composition=composition,
        )
        renderer._resolve_named_characters(motion_state, t, float(duration), width, height)
        pose = renderer._compute_pose(
            action, t, duration, width, height,
            camera_instructions=camera_instructions, motion_state=motion_state,
        )
        if motion_state.get("suppress_primary_character"):
            pose.stickman_x = -10000
            pose.stickman_y = -10000
        # Generate the frame in memory; discard bytes (no FFmpeg encode).
        renderer._generate_frame(
            width, height, t, duration, frame_idx, total_frames, pose,
            job=job, motion_state=motion_state,
        )


def _summarize_call(c):
    return {
        "scene": c.get("scene"),
        "frame_index": c.get("frame_index"),
        "n_specs": c.get("n_specs"),
        "seconds": round(c.get("seconds", 0.0), 6),
        "textlength_calls": c.get("textlength_calls", 0),
        "op_counts": dict(c.get("op_counts", {})),
    }


def main() -> int:
    plan_bytes = PLAN_PATH.read_bytes()
    assert hashlib.sha256(plan_bytes).hexdigest() == PLAN_SHA256, "canonical plan changed"
    from src.orchestration.schemas.visual import VisualPlan
    plan = VisualPlan.model_validate_json(plan_bytes)
    jobs = plan.render_job_plan["jobs"]

    renderer = StickmanRenderer(execute_enabled=False)
    probe = TextPathProbe(hash_bitmaps=True)
    probe.install()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    per_scene = []
    wall_start = time.perf_counter()
    try:
        for idx, job in enumerate(jobs):
            before = time.perf_counter()
            _render_job_frames(renderer, job, probe)
            per_scene.append({
                "scene_id": job.get("job_id"),
                "duration_s": job.get("duration_seconds"),
                "elapsed_s": round(time.perf_counter() - before, 3),
            })
            print(f"[day22] scene {idx+1}/{len(jobs)} {job.get('job_id')} done", flush=True)
    finally:
        probe.close()

    wall = time.perf_counter() - wall_start

    ops_summary = {k: {"calls": v["calls"], "seconds": round(v["seconds"], 6),
                        "bytes": v["bytes"], "contexts": dict(v["contexts"])}
                   for k, v in probe.ops.items()}
    font_keys = {str(k): v for k, v in probe.font_keys.items()}
    textlength_keys = {str(k): v for k, v in probe.textlength_keys.items()}
    bitmap_keys = {str(k): v for k, v in probe.bitmap_keys.items()}

    summary = {
        "plan_sha256": PLAN_SHA256,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "wall_seconds_instrumented": round(wall, 3),
        "scenes": per_scene,
        "aggregate": {
            "text_draw_calls (ImageDraw.text)": probe.bitmap_calls,
            "textlength_calls": probe.textlength_calls,
            "textbbox_calls": probe.ops.get("ImageDraw.textbbox", {}).get("calls", 0),
            "font_load_calls": probe.font_load_calls,
            "font_truetype_calls": probe.font_truetype_calls,
            "font_default_calls": probe.font_default_calls,
            "font_key_cardinality": len(probe.font_keys),
            "font_key_counts": font_keys,
            "font_paths": dict(probe.font_paths),
            "textlength_key_cardinality": len(probe.textlength_keys),
            "textlength_key_counts": textlength_keys,
            "bitmap_key_cardinality": len(probe.bitmap_keys),
            "bitmap_hashed": probe.bitmap_hashed,
            "bitmap_errors": probe.bitmap_errors,
            "text_call_count (frames w/ text)": len(probe.calls),
        },
        "ops": ops_summary,
    }

    (OUT_DIR / "text_probe_full.json").write_text(
        json.dumps({"summary": {k: v for k, v in summary.items() if k != "ops"},
                    "ops": ops_summary, "per_scene": per_scene}, indent=2, default=str),
        encoding="utf-8",
    )
    (OUT_DIR / "text_probe_calls.json").write_text(
        json.dumps([_summarize_call(c) for c in probe.calls], indent=2), encoding="utf-8",
    )
    (OUT_DIR / "text_probe_bitmap_keys.json").write_text(
        json.dumps(bitmap_keys, indent=2), encoding="utf-8",
    )
    (OUT_DIR / "text_probe_textlength_keys.json").write_text(
        json.dumps(textlength_keys, indent=2), encoding="utf-8",
    )
    (OUT_DIR / "text_probe_font_keys.json").write_text(
        json.dumps(font_keys, indent=2), encoding="utf-8",
    )

    print("\n===== DAY-22 TEXT-PATH INSTRUMENTED SUMMARY =====", flush=True)
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

