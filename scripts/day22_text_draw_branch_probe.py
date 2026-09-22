"""Day-22 probe: which branch Pillow's ``ImageDraw.text`` takes per frame.

Measurement only (no production edits). Patches ``ImageDraw.ImageDraw.text`` and
``Image.Image.crop`` for the duration of ONE real 1920x1080 frame and records,
for every text draw:

* the string, the ``xy`` anchor, the font pixel size and the target surface size,
* the glyph mask extent Pillow computes for that string,
* whether ``Image.Image.crop`` was entered while that draw was running (Pillow's
  slow "mask does not fit the surface" branch creates a full-surface scratch RGBA
  image, draws into it, crops to the image box and composites the result),
* the measured seconds of the draw itself.

Output: ``output/day22_profiling/text_draw_branch.json`` plus a stdout summary.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import types
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.scene_composition import SceneComposition  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

PLAN_PATH = ROOT / "output" / "day12_profiling" / "jobs" / "job_001" / "visual_plan.json"
OUT_PATH = ROOT / "output" / "day22_profiling" / "text_draw_branch.json"
WIDTH, HEIGHT, FPS = 1920, 1080, 30


def _build(job):
    renderer = StickmanRenderer(execute_enabled=False)
    composition = SceneComposition.from_visual_description(job.get("visual_description"))
    action = renderer._detect_action(job)
    motion_list = renderer._collect_motions(
        types.SimpleNamespace(motions=job.get("motions", []), job=job))
    return renderer, composition, action, motion_list, str(job.get("camera_instructions", ""))


def probe_frame(job, frame_idx):
    records: list[dict] = []
    crops: list[dict] = []
    depth = {"text": 0}

    orig_text = ImageDraw.ImageDraw.text
    orig_crop = Image.Image.crop

    def text_wrap(self, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        if font is None and len(args) > 1:
            font = args[1]
        surface = getattr(self, "_image", None)
        glyph_extent = None
        try:
            bbox = font.getbbox(str(text))
            glyph_extent = [bbox[2] - bbox[0], bbox[3] - bbox[1]]
        except Exception:
            pass
        entry = {
            "text": str(text),
            "xy": [xy[0], xy[1]] if isinstance(xy, (tuple, list)) else xy,
            "font_px": getattr(font, "size", None),
            "surface_mode": getattr(surface, "mode", None),
            "surface_size": list(surface.size) if surface is not None else None,
            "glyph_extent": glyph_extent,
            "crop_boxes": [],
        }
        depth["text"] += 1
        start = time.perf_counter()
        try:
            return orig_text(self, xy, text, *args, **kwargs)
        finally:
            entry["seconds"] = round(time.perf_counter() - start, 6)
            depth["text"] -= 1
            entry["crop_calls_during_draw"] = len(entry["crop_boxes"])
            entry["slow_branch"] = bool(entry["crop_boxes"])
            records.append(entry)

    def crop_wrap(self, box=None):
        if depth["text"] > 0 and records:
            records[-1]["crop_boxes"].append(list(box) if box else None)
        crops.append({"box": list(box) if box else None, "size": list(self.size),
                      "mode": self.mode, "during_text_draw": depth["text"] > 0})
        return orig_crop(self, box)

    ImageDraw.ImageDraw.text = text_wrap
    Image.Image.crop = crop_wrap
    try:
        renderer, composition, action, motion_list, cam = _build(job)
        duration = int(job["duration_seconds"])
        total_frames = duration * FPS
        t = frame_idx / FPS
        state = renderer._evaluate_motion_state(
            motion_list, t, float(duration), WIDTH, HEIGHT, action, composition=composition)
        renderer._resolve_named_characters(state, t, float(duration), WIDTH, HEIGHT)
        pose = renderer._compute_pose(action, t, duration, WIDTH, HEIGHT,
                                      camera_instructions=cam, motion_state=state)
        if state.get("suppress_primary_character"):
            pose.stickman_x = -10000
            pose.stickman_y = -10000
        renderer._generate_frame(WIDTH, HEIGHT, t, duration, frame_idx, total_frames, pose,
                                 job=job, motion_state=state)
    finally:
        ImageDraw.ImageDraw.text = orig_text
        Image.Image.crop = orig_crop
    return records, crops
def main() -> int:
    plan_bytes = PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes)
    job = plan["render_job_plan"]["jobs"][0]
    duration = int(job["duration_seconds"])
    frames = [0, 30, min(duration * FPS - 1, 60)]

    per_frame = []
    for frame_idx in frames:
        records, crops = probe_frame(job, frame_idx)
        slow = [r for r in records if r["slow_branch"]]
        per_frame.append({
            "frame_index": frame_idx,
            "text_draw_calls": len(records),
            "slow_branch_calls": len(slow),
            "fast_branch_calls": len(records) - len(slow),
            "crop_calls": len(crops),
            "crop_calls_during_text_draw": sum(1 for c in crops if c["during_text_draw"]),
            "seconds_total_text_draws": round(sum(r["seconds"] for r in records), 6),
            "records": records,
        })

    payload = {
        "day": 22,
        "kind": "ImageDraw.text branch census (measurement only; no production edits)",
        "provenance": {
            "script": "scripts/day22_text_draw_branch_probe.py",
            "plan": str(PLAN_PATH.relative_to(ROOT)).replace("\\", "/"),
            "renderer_sha256": hashlib.sha256(
                (ROOT / "src" / "services" / "stickman_renderer.py").read_bytes()).hexdigest(),
            "resolution": f"{WIDTH}x{HEIGHT}",
            "frames_probed": frames,
        },
        "per_frame": per_frame,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    for row in per_frame:
        print(f"frame {row['frame_index']}: text_draws={row['text_draw_calls']} "
              f"slow={row['slow_branch_calls']} fast={row['fast_branch_calls']} "
              f"crops={row['crop_calls']} "
              f"text_seconds={row['seconds_total_text_draws']}", flush=True)
        for rec in row["records"]:
            print(f"   {rec['text'][:30]!r} xy={rec['xy']} px={rec['font_px']} "
                  f"surface={rec['surface_size']} extent={rec['glyph_extent']} "
                  f"slow={rec['slow_branch']} boxes={rec['crop_boxes']} "
                  f"s={rec['seconds']}", flush=True)
    print("\nwrote", OUT_PATH, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())