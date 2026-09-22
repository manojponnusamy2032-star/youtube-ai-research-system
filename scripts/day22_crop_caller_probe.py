"""Day-22 probe: who calls ``Image.Image.crop`` ~1x/frame in the text path?

The Day-22 instrumented run attributes 1854 ``Image.Image.crop`` calls to
``text:_draw_text_elements``. This probe installs the *same* ``TextPathProbe``
and additionally patches ``Image.Image.crop`` to record, for every call, the
immediate Python caller (file/line/function), the crop box, the surface being
cropped and the probe's current context -- so the call site is identified from
evidence instead of inferred.

Output: ``output/day22_profiling/text_crop_callers.json``.
"""
from __future__ import annotations

import json
import sys
import sysconfig
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.day22_instrumentation import TextPathProbe  # noqa: E402
from src.services.scene_composition import SceneComposition  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

import types  # noqa: E402

PLAN_PATH = ROOT / "output" / "day12_profiling" / "jobs" / "job_001" / "visual_plan.json"
OUT_PATH = ROOT / "output" / "day22_profiling" / "text_crop_callers.json"
WIDTH, HEIGHT, FPS = 1920, 1080, 30
PIL_DIR = Path(Image.__file__).resolve().parent


def _caller() -> str:
    frame = sys._getframe(2)
    filename = frame.f_code.co_filename
    try:
        relative = str(Path(filename).resolve().relative_to(PIL_DIR))
    except Exception:
        relative = Path(filename).name
    return f"{relative}:{frame.f_lineno}:{frame.f_code.co_name}"


def run(frames: int = 100000) -> dict:
    records: list[dict] = []
    probe = TextPathProbe(hash_bitmaps=True)
    probe.install()
    ops_snapshot: dict = {}

    original_crop = Image.Image.crop

    def crop_wrap(self, box=None):
        try:
            records.append({
                "caller": _caller(),
                "box": list(box) if box else None,
                "surface_mode": self.mode,
                "surface_size": list(self.size),
                "context": probe.context(),
                "scene": probe.current_scene,
                "frame_index": probe.frame_index,
            })
        except Exception:
            pass
        return original_crop(self, box)

    Image.Image.crop = crop_wrap
    try:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        job = plan["render_job_plan"]["jobs"][0]
        renderer = StickmanRenderer(execute_enabled=False)
        duration = int(job["duration_seconds"])
        total_frames = duration * FPS
        composition = SceneComposition.from_visual_description(job.get("visual_description"))
        action = renderer._detect_action(job)
        motion_list = renderer._collect_motions(
            types.SimpleNamespace(motions=job.get("motions", []), job=job))
        camera_instructions = str(job.get("camera_instructions", ""))
        probe.scene(job.get("job_id", "unknown"))
        for frame_idx in range(min(frames, total_frames)):
            t = frame_idx / FPS
            state = renderer._evaluate_motion_state(
                motion_list, t, float(duration), WIDTH, HEIGHT, action,
                composition=composition)
            renderer._resolve_named_characters(state, t, float(duration), WIDTH, HEIGHT)
            pose = renderer._compute_pose(
                action, t, duration, WIDTH, HEIGHT,
                camera_instructions=camera_instructions, motion_state=state)
            if state.get("suppress_primary_character"):
                pose.stickman_x = -10000
                pose.stickman_y = -10000
            renderer._generate_frame(WIDTH, HEIGHT, t, duration, frame_idx, total_frames,
                                     pose, job=job, motion_state=state)
    finally:
        Image.Image.crop = original_crop
        ops_snapshot.update({k: dict(v) for k, v in probe.ops.items()})
        ops_snapshot["__probe_frames_with_text"] = len(probe.calls)
        ops_snapshot["__probe_bitmap_hashed"] = probe.bitmap_hashed
        probe.close()

    by_caller = Counter(r["caller"] for r in records)
    by_context = Counter(r["context"] for r in records)
    summary = {
        "day": 22,
        "kind": "Image.Image.crop call-site census (measurement only; no production edits)",
        "provenance": {
            "script": "scripts/day22_crop_caller_probe.py",
            "plan": str(PLAN_PATH.relative_to(ROOT)).replace("\\", "/"),
            "frames_probed": min(frames, total_frames),
            "scene": "why-most-people-quit-lea-scene-01",
            "probe": "scripts/day22_instrumentation.py TextPathProbe(hash_bitmaps=True)",
            "python": sys.version.split()[0],
            "pysuffix": sysconfig.get_config_var("EXT_SUFFIX"),
        },
        "crop_calls_total": len(records),
        "probe_ops_snapshot": ops_snapshot,
        "crop_calls_by_caller": dict(by_caller),
        "crop_calls_by_context": dict(by_context),
        "crop_surface_shapes": dict(Counter(
            f"{r['surface_mode']} {r['surface_size']} box={r['box']}" for r in records)),
        "first_records": records[:12],
    }
    return summary


def main() -> int:
    summary = run()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("crop_calls_total:", summary["crop_calls_total"], flush=True)
    print("probe_ops_snapshot:", json.dumps(summary["probe_ops_snapshot"], indent=2), flush=True)
    print("by_caller:", json.dumps(summary["crop_calls_by_caller"], indent=2), flush=True)
    print("by_context:", json.dumps(summary["crop_calls_by_context"], indent=2), flush=True)
    print("surface shapes:", json.dumps(summary["crop_surface_shapes"], indent=2), flush=True)
    print("first records:", json.dumps(summary["first_records"], indent=2), flush=True)
    print("\nwrote", OUT_PATH, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())