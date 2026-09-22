"""Day-22 text-path primitive cost census (measurement only, no production edits).

Two independent measurements, both written to
``output/day22_profiling/text_path_primitives.json``:

1. ``alloc_trace`` -- wraps ``PIL.Image.new`` / ``Image.frombytes`` /
   ``Image.Image.tobytes`` while ONE real 1920x1080 frame is generated through
   the production per-frame core, recording every allocation (mode, size,
   colour, caller) so the per-frame buffer traffic of ``_draw_text_elements``
   is known exactly instead of inferred.

2. ``microbench`` -- median per-call cost of each primitive at the exact
   geometry the text path uses (1920x1080 RGB / RGBA, the real 45px
   ``arialbd.ttf`` font, the real caption strings), so the per-frame budget can
   be reconstructed and reconciled against the Day-22 baseline profile.

Nothing here changes production code: the wrappers are restored before exit.
"""
from __future__ import annotations

import inspect
import json
import statistics
import sys
import time
import types
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.content_package import RenderConfig  # noqa: E402
from src.services.scene_composition import SceneComposition  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

PLAN_PATH = ROOT / "output" / "day12_profiling" / "jobs" / "job_001" / "visual_plan.json"
OUT_PATH = ROOT / "output" / "day22_profiling" / "text_path_primitives.json"
WIDTH, HEIGHT, FPS = 1920, 1080, 30
FONT_PATH = "C:/Windows/Fonts/arialbd.ttf"
REPS = 40
def _build_frame_inputs(job):
    """Reproduce the driver's per-frame input construction for one job."""
    renderer = StickmanRenderer(execute_enabled=False)
    duration = int(job.get("duration_seconds", 1))
    composition = SceneComposition.from_visual_description(job.get("visual_description"))
    action = renderer._detect_action(job)
    request = types.SimpleNamespace(motions=job.get("motions", []), job=job)
    motion_list = renderer._collect_motions(request)
    camera_instructions = str(job.get("camera_instructions", ""))
    return renderer, duration, composition, action, motion_list, camera_instructions


def _motion_state(renderer, motion_list, frame_idx, duration, composition, action):
    t = frame_idx / FPS
    state = renderer._evaluate_motion_state(
        motion_list, t, float(duration), WIDTH, HEIGHT, action, composition=composition,
    )
    renderer._resolve_named_characters(state, t, float(duration), WIDTH, HEIGHT)
    return t, state


def _generate_one(renderer, job, composition, action, motion_list, camera_instructions,
                  duration, frame_idx):
    total_frames = duration * FPS
    t, motion_state = _motion_state(renderer, motion_list, frame_idx, duration,
                                    composition, action)
    pose = renderer._compute_pose(
        action, t, duration, WIDTH, HEIGHT,
        camera_instructions=camera_instructions, motion_state=motion_state,
    )
    if motion_state.get("suppress_primary_character"):
        pose.stickman_x = -10000
        pose.stickman_y = -10000
    return renderer._generate_frame(
        WIDTH, HEIGHT, t, duration, frame_idx, total_frames, pose,
        job=job, motion_state=motion_state,
    )


def trace_allocations(job, frame_idx):
    """Record every PIL allocation made while generating one real frame."""
    log = []
    originals = {
        "new": Image.new,
        "frombytes": Image.frombytes,
        "tobytes": Image.Image.tobytes,
        "paste": Image.Image.paste,
    }
    inside = {"frombytes": 0}

    def new_wrap(mode, size, *args, **kwargs):
        color = kwargs.get("color", 0)
        if args:
            color = args[0]
        log.append({
            "op": "Image.new",
            "mode": mode,
            "size": list(size),
            "color": list(color) if isinstance(color, (tuple, list)) else color,
            "nested_in_frombytes": inside["frombytes"] > 0,
        })
        return originals["new"](mode, size, *args, **kwargs)

    def frombytes_wrap(mode, size, data, *args, **kwargs):
        inside["frombytes"] += 1
        try:
            log.append({"op": "Image.frombytes", "mode": mode, "size": list(size),
                        "data_bytes": len(data)})
            return originals["frombytes"](mode, size, data, *args, **kwargs)
        finally:
            inside["frombytes"] -= 1

    def tobytes_wrap(self, *args, **kwargs):
        log.append({"op": "Image.Image.tobytes", "mode": self.mode, "size": list(self.size)})
        return originals["tobytes"](self, *args, **kwargs)

    def paste_wrap(self, im, box=None, mask=None):
        log.append({"op": "Image.Image.paste", "mode": self.mode, "size": list(self.size),
                    "box": list(box) if isinstance(box, (tuple, list)) else str(box),
                    "mask": "overlay" if mask is im else type(mask).__name__})
        return originals["paste"](self, im, box, mask)

    Image.new = new_wrap
    Image.frombytes = frombytes_wrap
    Image.Image.tobytes = tobytes_wrap
    Image.Image.paste = paste_wrap
    try:
        renderer, duration, composition, action, motion_list, cam = _build_frame_inputs(job)
        _generate_one(renderer, job, composition, action, motion_list, cam,
                      duration, frame_idx)
    finally:
        Image.new = originals["new"]
        Image.frombytes = originals["frombytes"]
        Image.Image.tobytes = originals["tobytes"]
        Image.Image.paste = originals["paste"]
    return log
def collect_text_strings(job, frame_idx):
    """Capture the real caption strings one frame measures (nothing hard-coded)."""
    captured: list[str] = []
    original = ImageDraw.ImageDraw.textlength

    def textlength_wrap(self, text, *args, **kwargs):
        value = str(text)
        if value not in captured:
            captured.append(value)
        return original(self, text, *args, **kwargs)

    ImageDraw.ImageDraw.textlength = textlength_wrap
    try:
        renderer, duration, composition, action, motion_list, cam = _build_frame_inputs(job)
        _generate_one(renderer, job, composition, action, motion_list, cam,
                      duration, frame_idx)
    finally:
        ImageDraw.ImageDraw.textlength = original
    return captured


_KEEPALIVE: list = []


def _timed(fn, reps=REPS):
    """Median per-call cost.

    Only the most recent result is retained between reps so that the previous
    large buffer is released and the allocator can recycle it -- matching the
    steady-state behaviour of the render loop (holding every result alive would
    force fresh pages for each rep and inflate the cost with page faults).
    """
    samples = []
    keep = None
    for _ in range(reps):
        start = time.perf_counter()
        keep = fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    _KEEPALIVE[:] = [keep]
    return {
        "reps": reps,
        "median_ms": round(statistics.median(samples), 4),
        "min_ms": round(min(samples), 4),
        "p95_ms": round(sorted(samples)[max(0, min(reps - 1, int(0.95 * reps) - 1))], 4),
    }


def microbench(strings):
    """Median cost of each primitive at the exact geometry the text path uses."""
    frame = bytearray(WIDTH * HEIGHT * 3)
    frame_bytes = bytes(frame)
    font = ImageFont.truetype(FONT_PATH, 45)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgb = Image.frombytes("RGB", (WIDTH, HEIGHT), frame_bytes)
    small = Image.new("RGBA", (800, 200), (0, 0, 0, 0))
    small_draw = ImageDraw.Draw(small)
    draw.rectangle([100, 900, 700, 980], fill=(10, 12, 18, 150))
    for i, value in enumerate(strings[:3]):
        draw.text((120, 900 + i * 60), value, fill=(255, 255, 255, 255), font=font)

    ops = {}
    ops["bytes_of_RGB_frame_bytearray"] = _timed(lambda: bytes(frame))
    ops["Image.frombytes_RGB_1920x1080"] = _timed(
        lambda: Image.frombytes("RGB", (WIDTH, HEIGHT), frame_bytes))
    ops["Image.new_RGBA_1920x1080_zero_filled"] = _timed(
        lambda: Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)))
    ops["Image.new_RGB_1920x1080_uninitialised"] = _timed(
        lambda: Image.new("RGB", (WIDTH, HEIGHT)))
    paste_target = rgb.copy()
    ops["Image.paste_RGBA_overlay_full_frame"] = _timed(
        lambda: paste_target.paste(overlay, (0, 0), overlay))
    ops["Image.copy_RGB_1920x1080"] = _timed(lambda: rgb.copy())
    ops["Image.tobytes_RGB_1920x1080"] = _timed(lambda: rgb.tobytes())
    if strings:
        ops["ImageDraw.textlength_45px_full_size_draw"] = _timed(
            lambda: draw.textlength(strings[0], font=font))
        ops["ImageDraw.text_45px_full_RGBA_overlay_1920x1080"] = _timed(
            lambda: draw.text((120, 900), strings[0], fill=(255, 255, 255, 255), font=font))
        ops["ImageDraw.text_45px_small_RGBA_overlay_800x200"] = _timed(
            lambda: small_draw.text((10, 20), strings[0], fill=(255, 255, 255, 255), font=font))
    ops["ImageFont.truetype_45px"] = _timed(
        lambda: ImageFont.truetype(FONT_PATH, 45), reps=20)
    return ops
def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    import PIL

    plan_bytes = PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    jobs = plan["render_job_plan"]["jobs"]
    job = jobs[0]
    duration = int(job["duration_seconds"])
    text_frame = min(duration * FPS - 1, 45)

    first_log = trace_allocations(job, 0)
    text_log = trace_allocations(job, text_frame)
    strings = collect_text_strings(job, text_frame)
    ops = microbench(strings)

    probe_path = ROOT / "output" / "day22_profiling" / "instrumented" / "text_probe_full.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    probe_ops = probe["ops"]
    frames = probe["summary"]["aggregate"]["text_call_count (frames w/ text)"]
    counts = {name: round(payload["calls"] / frames, 6) for name, payload in probe_ops.items()}

    hash_probe_calls = 2 * probe["summary"]["aggregate"]["bitmap_key_cardinality"]
    new_total = probe_ops["Image.new"]["calls"]
    nested = probe_ops["Image.frombytes"]["calls"]
    overlay_new = new_total - nested - hash_probe_calls
    new_decomposition = {
        "Image.new_calls_total": new_total,
        "nested_inside_Image_frombytes": nested,
        "probe_bitmap_hashing_allocations": hash_probe_calls,
        "text_path_overlay_allocations": overlay_new,
        "text_path_overlay_per_frame": round(overlay_new / frames, 6),
        "per_frame_note": "text_path_overlay_per_frame ~= 1.0 (one RGBA overlay per "
                          "text-bearing frame); the frombytes count also carries the "
                          "nested Image.new that Pillow performs internally",
    }

    primitives = {
        "bytes_of_RGB_frame_bytearray": counts["Image.frombytes"],
        "Image.frombytes_RGB_1920x1080": counts["Image.frombytes"],
        "Image.new_RGBA_1920x1080_zero_filled": round(overlay_new / frames, 6),
        "Image.paste_RGBA_overlay_full_frame": counts["Image.Image.paste"],
        "Image.tobytes_RGB_1920x1080": counts["Image.Image.tobytes"],
        "ImageDraw.text_45px_full_RGBA_overlay_1920x1080": counts["ImageDraw.text"],
        "ImageDraw.textlength_45px_full_size_draw": counts["ImageDraw.textlength"],
        "ImageFont.truetype_45px": counts["_load_font"],
    }
    per_frame_ms = {}
    for op_name, calls in primitives.items():
        per_frame_ms[op_name] = {
            "calls_per_frame": calls,
            "median_ms_per_call": ops[op_name]["median_ms"],
            "per_frame_ms": round(calls * ops[op_name]["median_ms"], 4),
        }
    budget_total_ms = round(sum(v["per_frame_ms"] for v in per_frame_ms.values()), 3)

    baseline = json.loads(
        (ROOT / "output" / "day22_profiling" / "baseline_run" / "raw_timings.json")
        .read_text(encoding="utf-8"))["profile"]
    text_method = baseline["methods"]["StickmanRenderer._draw_text_elements"]
    text_inclusive_s = text_method["inclusive"]
    text_exclusive_s = text_method["exclusive"]
    frame_gen_s = baseline["frame_generation_seconds"]
    baseline_frames = baseline["frame_count"]

    bitmap_cardinality = probe["summary"]["aggregate"]["bitmap_key_cardinality"]
    in_situ_ops = {}
    for name, payload_ops in sorted(probe_ops.items()):
        call_count = payload_ops["calls"]
        in_situ_ops[name] = {
            "calls": call_count,
            "seconds_total": payload_ops["seconds"],
            "ms_per_call": round(payload_ops["seconds"] / call_count * 1000.0, 4)
                           if call_count else None,
            "bytes_total": payload_ops["bytes"],
            "contexts": payload_ops["contexts"],
        }

    cross_check = {
        "Image.frombytes": ("Image.frombytes_RGB_1920x1080", in_situ_ops["Image.frombytes"]),
        "Image.tobytes": ("Image.tobytes_RGB_1920x1080", in_situ_ops["Image.Image.tobytes"]),
        "Image.new": ("Image.new_RGBA_1920x1080_zero_filled", in_situ_ops["Image.new"]),
        "Image.paste": ("Image.paste_RGBA_overlay_full_frame", in_situ_ops["Image.Image.paste"]),
        "ImageDraw.text": ("ImageDraw.text_45px_full_RGBA_overlay_1920x1080",
                           in_situ_ops["ImageDraw.text"]),
        "ImageDraw.textlength": ("ImageDraw.textlength_45px_full_size_draw",
                                 in_situ_ops["ImageDraw.textlength"]),
        "_load_font": ("ImageFont.truetype_45px", in_situ_ops["_load_font"]),
    }
    cross_checked = {}
    for label, (cold_key, in_situ) in cross_check.items():
        cold = ops[cold_key]["median_ms"]
        hot = in_situ["ms_per_call"]
        cross_checked[label] = {
            "cold_microbench_median_ms": cold,
            "cold_microbench_op": cold_key,
            "in_situ_probe_ms_per_call": hot,
            "cold_over_hot_ratio": round(cold / hot, 3) if hot else None,
        }

    caveats = [
        "In-situ probe op timings wrap every PIL / ImageDraw entry point, so each wrapped "
        "call pays two extra perf_counter reads; they therefore sit above the pristine "
        "baseline profile.",
        f"The bitmap-hash probe adds its own work inside the 'text:' context: {hash_probe_calls} "
        f"extra Image.new plus {bitmap_cardinality} each of ImageDraw.textbbox, ImageDraw.text "
        "and Image.Image.tobytes. Those are included in the in-situ op totals.",
        "Cold microbench medians allocate a fresh multi-megabyte buffer per rep, so they are an "
        "upper bound on allocation cost; the render loop recycles buffers frame after frame. "
        "The cold/hot ratios below quantify that gap instead of hiding it.",
        "The instrumented run excludes x264 encoding and audio/TTS (not part of the text path).",
        "Image.Image.crop byte counts are mode*size of the crop result, not measured copy "
        "traffic; the crop source is Pillow's own scratch surface.",
    ]

    baseline_decomposition = {
        "text_inclusive_s": round(text_inclusive_s, 4),
        "wrapped_buffer_ops_in_text_path_s": {
            "Image.tobytes": round(baseline["methods"]["Image.tobytes"]["exclusive"], 4),
            "Image.frombytes": round(baseline["methods"]["Image.frombytes"]["exclusive"], 4),
            "Image.paste": round(baseline["methods"]["Image.paste"]["exclusive"], 4),
            "_load_font": round(baseline["methods"]["StickmanRenderer._load_font"]["exclusive"], 4),
        },
        "text_exclusive_s": round(text_exclusive_s, 4),
        "note": "The Day-22 baseline wrapper set did not wrap Image.new / ImageDraw.text / "
                "ImageDraw.textlength / Image.Image.crop, so their cost sits inside "
                "_draw_text_elements exclusive. The instrumented probe supplies those counts "
                "and in-situ times.",
    }
    baseline_decomposition["wrapped_buffer_ops_total_s"] = round(
        sum(baseline_decomposition["wrapped_buffer_ops_in_text_path_s"].values()), 4)
    baseline_decomposition["wrapped_buffer_share_percent"] = round(
        baseline_decomposition["wrapped_buffer_ops_total_s"] / text_inclusive_s * 100.0, 2)
    baseline_decomposition["unwrapped_share_percent"] = round(
        text_exclusive_s / text_inclusive_s * 100.0, 2)

    reconciliation = {
        "baseline_frames": baseline_frames,
        "baseline_text_inclusive_s": round(text_inclusive_s, 4),
        "baseline_text_exclusive_s": round(text_exclusive_s, 4),
        "baseline_text_inclusive_ms_per_frame": round(
            text_inclusive_s / baseline_frames * 1000.0, 4),
        "baseline_frame_generation_s": round(frame_gen_s, 4),
        "primitive_budget_ms_per_frame": budget_total_ms,
        "primitive_budget_s_per_render": round(budget_total_ms * baseline_frames / 1000.0, 4),
        "primitive_budget_share_of_text_inclusive_percent": round(
            budget_total_ms * baseline_frames / 1000.0 / text_inclusive_s * 100.0, 2),
    }

    payload = {
        "day": 22,
        "kind": "text-path primitive cost census (measurement only; no production edits)",
        "provenance": {
            "script": "scripts/day22_text_primitive_bench.py",
            "plan": str(PLAN_PATH.relative_to(ROOT)).replace("\\", "/"),
            "plan_sha256": plan_sha,
            "renderer_sha256": _sha256_file(ROOT / "src" / "services" / "stickman_renderer.py"),
            "pillow_version": PIL.__version__,
            "python_version": sys.version.split()[0],
            "resolution": f"{WIDTH}x{HEIGHT}",
            "fps": FPS,
            "reps": REPS,
            "probe_artifact": "output/day22_profiling/instrumented/text_probe_full.json",
            "baseline_artifact": "output/day22_profiling/baseline_run/raw_timings.json",
            "alloc_trace_frames": {"first_frame": 0, "text_frame": text_frame},
        },
        "captured_text_strings": strings,
        "ops_microbench": ops,
        "per_frame_counts": counts,
        "image_new_decomposition": new_decomposition,
        "per_frame_budget_ms": per_frame_ms,
        "reconciliation": reconciliation,
        "in_situ_probe_ops": in_situ_ops,
        "cold_vs_in_situ_cross_check": cross_checked,
        "baseline_text_decomposition": baseline_decomposition,
        "caveats": caveats,
        "alloc_trace_text_frame": text_log,
        "alloc_trace_first_frame": first_log,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"pillow={PIL.__version__} python={sys.version.split()[0]}", flush=True)
    print(f"plan_sha256={plan_sha}", flush=True)
    print(f"captured_text_strings({len(strings)})={strings}", flush=True)
    print("\n=== per-frame primitive budget (ms) ===", flush=True)
    print(json.dumps(per_frame_ms, indent=2), flush=True)
    print(f"\nbudget per frame: {budget_total_ms} ms", flush=True)
    print(json.dumps(reconciliation, indent=2), flush=True)
    print("\n=== cold vs in-situ cross-check ===", flush=True)
    print(json.dumps(cross_checked, indent=2), flush=True)
    print("\n=== baseline text decomposition ===", flush=True)
    print(json.dumps(baseline_decomposition, indent=2), flush=True)
    print("\n=== alloc trace, text frame ===", flush=True)
    print(json.dumps(text_log, indent=2), flush=True)
    print("\nwrote", OUT_PATH, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

