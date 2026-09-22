"""Day-22 un-instrumented text-path stage bench (measurement only).

The instrumented runs wrap every PIL entry point, so their absolute timings
cannot be compared against the un-instrumented baseline profile. This script
measures the production text path with NO wrappers installed:

1. ``method``: calls the real ``StickmanRenderer._draw_text_elements`` on a real
   generated frame, N times, and reports the median per-call cost.
2. ``stages``: replays the same statements the method performs, with a local
   stopwatch around each stage (``bytes`` copy, ``Image.frombytes``, overlay
   allocation, word-wrap measurement, per-line rectangle, per-line ``text``,
   overlay ``paste``, ``tobytes``), so the per-frame budget is attributed.

Output: ``output/day22_profiling/text_path_stages.json``.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
import time
import types
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.scene_composition import (  # noqa: E402
    SAFE_MARGIN_RATIO,
    SceneComposition,
    resolve_text_placement,
)
from src.services.stickman_renderer import StickmanRenderer, _text_opacity  # noqa: E402

PLAN_PATH = ROOT / "output" / "day12_profiling" / "jobs" / "job_001" / "visual_plan.json"
OUT_PATH = ROOT / "output" / "day22_profiling" / "text_path_stages.json"
WIDTH, HEIGHT, FPS = 1920, 1080, 30
FONT_PATH = "C:/Windows/Fonts/arialbd.ttf"
REPS = 25


def _setup(job, frame_idx):
    """Return (renderer, state, t, duration) for one real frame."""
    renderer = StickmanRenderer(execute_enabled=False)
    duration = int(job["duration_seconds"])
    composition = SceneComposition.from_visual_description(job.get("visual_description"))
    action = renderer._detect_action(job)
    motion_list = renderer._collect_motions(
        types.SimpleNamespace(motions=job.get("motions", []), job=job))
    t = frame_idx / FPS
    state = renderer._evaluate_motion_state(
        motion_list, t, float(duration), WIDTH, HEIGHT, action, composition=composition)
    renderer._resolve_named_characters(state, t, float(duration), WIDTH, HEIGHT)
    return renderer, state, t, duration


def _median_ms(fn, reps=REPS):
    samples = []
    keep = None
    for _ in range(reps):
        start = time.perf_counter()
        keep = fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return round(statistics.median(samples), 4), round(min(samples), 4), keep


def _stage_timings(renderer, frame, state, t, duration):
    """Replay the production statements with a stopwatch per stage."""
    stage: dict = {}

    def timed(name, fn):
        start = time.perf_counter()
        result = fn()
        stage[name] = stage.get(name, 0.0) + (time.perf_counter() - start) * 1000.0
        return result

    specs = state.get("text_specs") or []
    margin_x = int(WIDTH * SAFE_MARGIN_RATIO)
    counters = {"textlength": 0, "rectangle": 0, "text": 0, "lines": 0}

    image = timed("bytes_frame_copy_ms", lambda: Image.frombytes(
        "RGB", (WIDTH, HEIGHT), timed("bytes_frame_ms", lambda: bytes(frame))))
    overlay = timed("overlay_alloc_ms",
                    lambda: Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)))
    draw = ImageDraw.Draw(overlay)

    for spec in specs:
        text = str(spec.get("text", "")).strip()
        if not text:
            continue
        opacity = _text_opacity(spec, t, duration)
        if opacity <= 0.01:
            continue
        scale_factor = {"small": 0.7, "normal": 1.0, "large": 1.4,
                        "headline": 2.0}.get(str(spec.get("size", "normal")), 1.0)
        px_size = max(10, int(min(WIDTH, HEIGHT) * 0.030 * scale_factor))
        font = timed("font_load_ms", lambda: renderer._load_font(px_size))
        if font is None:
            continue
        color = tuple(spec.get("color", (255, 255, 255)))
        max_px = min(int(WIDTH * float(spec.get("max_width", 0.8))),
                     WIDTH - 2 * margin_x)

        def wrap():
            words = text.split()
            lines: list[str] = []
            current = ""
            for word in words:
                trial = (current + " " + word).strip()
                tw = draw.textlength(trial, font=font)
                counters["textlength"] += 1
                if tw <= max_px or not current:
                    current = trial
                else:
                    lines.append(current)
                    current = word
            if current:
                lines.append(current)
            return lines

        lines = timed("word_wrap_measure_ms", wrap)
        counters["lines"] += len(lines)
        line_h = int(px_size * 1.32)
        block_h = line_h * len(lines)
        anchor_name = str(spec.get("anchor", "center"))
        pad_x, pad_y = int(px_size * 0.45), int(px_size * 0.28)

        def widest_of():
            widest = 0
            for ln in lines:
                lw = int(draw.textlength(ln, font=font))
                counters["textlength"] += 1
                widest = max(widest, lw)
            return widest

        widest = timed("widest_measure_ms", widest_of)

        def place():
            return resolve_text_placement(
                float(spec.get("x", 0.5)), float(spec.get("y", 0.9)),
                widest + 2 * pad_x, block_h + 2 * pad_y, WIDTH, HEIGHT,
                blocked_rects=state.get("blocked_rects") or [], anchor=anchor_name)

        bx0, by0 = timed("placement_ms", place)
        x0, y0 = bx0 + pad_x, by0 + pad_y

        def rect():
            counters["rectangle"] += 1
            draw.rectangle([bx0, by0, bx0 + widest + 2 * pad_x,
                            by0 + block_h + 2 * pad_y],
                           fill=(10, 12, 18, int(150 * opacity)))

        timed("rectangle_ms", rect)

        def texts():
            for i, ln in enumerate(lines):
                counters["text"] += 1
                draw.text((x0, y0 + i * line_h), ln,
                          fill=(color[0], color[1], color[2], int(255 * opacity)),
                          font=font)

        timed("text_draw_ms", texts)

    timed("paste_ms", lambda: image.paste(overlay, (0, 0), overlay))
    payload = timed("tobytes_ms", lambda: image.tobytes())
    timed("frame_slice_assign_ms", lambda: frame.__setitem__(slice(None), payload))

    stage["_counts"] = {"specs": len(specs), **counters}
    stage["_total_ms"] = round(sum(v for k, v in stage.items()
                                   if isinstance(v, float)), 4)
    return stage


def _real_frame(renderer, job, state, t, duration, frame_idx):
    """Generate one real frame (no wrappers) and return its bytes."""
    total_frames = int(job["duration_seconds"]) * FPS
    pose = renderer._compute_pose(
        renderer._detect_action(job), t, duration, WIDTH, HEIGHT,
        camera_instructions=str(job.get("camera_instructions", "")), motion_state=state)
    if state.get("suppress_primary_character"):
        pose.stickman_x = -10000
        pose.stickman_y = -10000
    return renderer._generate_frame(WIDTH, HEIGHT, t, duration, frame_idx, total_frames,
                                    pose, job=job, motion_state=state)


def _median_stages(renderer, frame, state, t, duration, reps=8):
    keys = None
    samples: dict = {}
    for _ in range(reps):
        stage = _stage_timings(renderer, bytearray(frame), state, t, duration)
        if keys is None:
            keys = [k for k in stage if k.endswith("_ms")]
        for k in keys:
            samples.setdefault(k, []).append(stage[k])
    out = {k: round(statistics.median(v), 4) for k, v in samples.items()}
    out["_total_ms"] = round(sum(out.values()), 4)
    out["_counts"] = stage["_counts"]
    return out


def main() -> int:
    import PIL

    plan_bytes = PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    jobs = plan["render_job_plan"]["jobs"]
    job = jobs[0]
    duration = int(job["duration_seconds"])
    frame_idx = min(duration * FPS - 1, 45)

    renderer, state, t, duration = _setup(job, frame_idx)
    frame = _real_frame(renderer, job, state, t, duration, frame_idx)

    method_median, method_min, _ = _median_ms(
        lambda: renderer._draw_text_elements(bytearray(frame), WIDTH, HEIGHT,
                                             state, t, float(duration)))
    stages = _median_stages(renderer, frame, state, t, float(duration))

    baseline = json.loads(
        (ROOT / "output" / "day22_profiling" / "baseline_run" / "raw_timings.json")
        .read_text(encoding="utf-8"))["profile"]
    text_method = baseline["methods"]["StickmanRenderer._draw_text_elements"]
    frames_baseline = baseline["frame_count"]
    baseline_ms = round(text_method["inclusive"] / frames_baseline * 1000.0, 4)

    pilot = json.loads(
        (ROOT / "output" / "day22_profiling" / "instrumented" / "text_probe_full.json")
        .read_text(encoding="utf-8"))
    probe_counts = {k: v["calls"] for k, v in pilot["ops"].items()}

    payload = {
        "day": 22,
        "kind": "un-instrumented text-path stage bench (measurement only)",
        "provenance": {
            "script": "scripts/day22_text_path_stage_bench.py",
            "plan_sha256": plan_sha,
            "renderer_sha256": hashlib.sha256(
                (ROOT / "src" / "services" / "stickman_renderer.py").read_bytes()).hexdigest(),
            "pillow_version": PIL.__version__,
            "python_version": sys.version.split()[0],
            "resolution": f"{WIDTH}x{HEIGHT}",
            "scene": job["job_id"],
            "frame_index": frame_idx,
            "reps": REPS,
            "wrappers_installed": False,
        },
        "method_call": {
            "target": "StickmanRenderer._draw_text_elements",
            "median_ms_per_frame": method_median,
            "min_ms_per_frame": method_min,
        },
        "stages_ms_per_frame": stages,
        "baseline_profile": {
            "text_inclusive_ms_per_frame": baseline_ms,
            "text_exclusive_s_total": round(text_method["exclusive"], 4),
            "text_inclusive_s_total": round(text_method["inclusive"], 4),
            "frames": frames_baseline,
        },
        "instrumented_run_call_counts": probe_counts,
        "interpretation_note": "Stage timings replay the production statements in the same "
                               "order with a local stopwatch; `method_call` times the real "
                               "method untouched, so it is the number to compare with the "
                               "baseline profile.",
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"pillow={PIL.__version__} python={sys.version.split()[0]}", flush=True)
    print(f"scene={job['job_id']} frame={frame_idx} specs="
          f"{stages['_counts']['specs']} lines={stages['_counts']['lines']}", flush=True)
    print(json.dumps(payload["method_call"], indent=2), flush=True)
    print("\n=== stages (ms per frame, median of 8) ===", flush=True)
    print(json.dumps(stages, indent=2), flush=True)
    print("\n=== baseline profile ===", flush=True)
    print(json.dumps(payload["baseline_profile"], indent=2), flush=True)
    print("\nwrote", OUT_PATH, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())