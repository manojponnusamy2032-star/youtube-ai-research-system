#!/usr/bin/env python3
"""Day-8 verification script."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

RENDER_STATUS_COMPLETED = "completed"
RENDER_STATUS_FAILED = "failed"
RENDER_STATUS_PENDING = "pending"
RENDER_STATUS_RUNNING = "running"

COMPLETED_STATUSES = frozenset({"completed"})

REQUIRED_VISUAL_PLAN_FIELDS = frozenset({"topic", "title", "scenes"})
REQUIRED_RENDER_PROGRESS_FIELDS = frozenset({
    "job_id", "started_at", "completed_at", "status",
    "total_ms", "work_ms", "total_frames", "rendered_frames",
    "frames_per_second", "frame_ms", "remaining", "eta_seconds",
    "tasks_total", "tasks_done", "current_stage", "failures", "scenes",
})

OPTIONAL_ARTIFACTS = frozenset({
    "research.json", "strategy.json", "script.json", "job.json", "clip_stats",
})


def discover_mp4(job_dir: Path) -> Path | None:
    """Discover the canonical MP4. Prefers final_video.mp4, then video.mp4,
    then a deterministic search of subdirectories."""
    job_json = job_dir / "job.json"
    if job_json.exists():
        try:
            with open(job_json) as f:
                job_data = json.load(f)
            fm = job_data.get("final_media")
            if isinstance(fm, dict):
                ref = fm.get("output_reference")
                if ref and isinstance(ref, str):
                    p = Path(ref)
                    if not p.is_absolute():
                        p = job_dir / p
                    if p.exists() and p.suffix.lower() == ".mp4":
                        return p
            ro = job_data.get("render_outputs")
            if isinstance(ro, list):
                for o in ro:
                    if isinstance(o, dict) and o.get("status") == RENDER_STATUS_COMPLETED:
                        ref = o.get("output_reference")
                        if ref and isinstance(ref, str):
                            p = Path(ref)
                            if not p.is_absolute():
                                p = job_dir / p
                            if p.exists() and p.suffix.lower() == ".mp4":
                                return p
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    for name in ("final_video.mp4", "video.mp4"):
        p = job_dir / name
        if p.exists():
            return p

    for p in sorted(job_dir.rglob("*.mp4")):
        parts = p.relative_to(job_dir).parts
        if "temp" not in parts and "tmp" not in parts and "__pycache__" not in str(p):
            return p

    return None
def validate_mp4_with_ffprobe(mp4_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False, "exists": False, "non_zero_size": False,
        "parseable": False, "video_stream_exists": False,
        "duration_seconds": None, "width": None, "height": None,
        "fps": None, "audio_present": False, "codec": None, "errors": [],
    }
    if not mp4_path.exists():
        result["errors"].append(f"MP4 not found: {mp4_path}")
        return result
    result["exists"] = True
    try:
        if mp4_path.stat().st_size == 0:
            result["errors"].append("MP4 is empty")
            return result
        result["non_zero_size"] = True
    except OSError as e:
        result["errors"].append(f"Cannot stat: {e}")
        return result

    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(mp4_path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            result["errors"].append(f"ffprobe failed: {proc.returncode}")
            return result
        data = json.loads(proc.stdout)
        result["parseable"] = True
    except json.JSONDecodeError:
        result["errors"].append("Cannot parse ffprobe output")
        return result
    except FileNotFoundError:
        result["errors"].append("ffprobe not available")
        return result
    except Exception as e:
        result["errors"].append(f"ffprobe error: {e}")
        return result

    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video_stream is None:
        result["errors"].append("No video stream")
        return result

    result["video_stream_exists"] = True
    result["codec"] = video_stream.get("codec_name", "unknown")
    result["audio_present"] = audio_stream is not None

    try:
        d = float(video_stream.get("duration", 0))
        if d > 0:
            result["duration_seconds"] = d
        else:
            result["errors"].append("Duration not positive")
    except (ValueError, TypeError):
        result["errors"].append("Cannot parse duration")

    try:
        w = int(video_stream.get("width", 0))
        if w > 0:
            result["width"] = w
        else:
            result["errors"].append("Width not positive")
    except (ValueError, TypeError):
        result["errors"].append("Cannot parse width")

    try:
        h = int(video_stream.get("height", 0))
        if h > 0:
            result["height"] = h
        else:
            result["errors"].append("Height not positive")
    except (ValueError, TypeError):
        result["errors"].append("Cannot parse height")

    try:
        fps_str = video_stream.get("r_frame_rate", "0/1")
        fps_num, den = fps_str.split("/")
        fps = float(fps_num) / float(den) if int(den) != 0 else 0
        if fps > 0:
            result["fps"] = fps
        else:
            result["errors"].append("FPS not positive")
    except (ValueError, ZeroDivisionError, AttributeError):
        result["errors"].append("Cannot parse FPS")

    result["valid"] = bool(
        len(result["errors"]) == 0
        and result["duration_seconds"]
        and result["width"]
        and result["height"]
        and result["fps"]
    )
    return result
def validate_visual_plan(vp: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False, "errors": [], "warnings": [],
        "topic": None, "title": None,
        "scene_count": 0, "total_duration_seconds": None,
    }

    if not isinstance(vp, dict):
        result["errors"].append("visual_plan is not a dict")
        return result

    result["topic"] = vp.get("topic")
    result["title"] = vp.get("title")

    for field in REQUIRED_VISUAL_PLAN_FIELDS:
        if field not in vp:
            result["errors"].append(f"Missing {field}")

    scenes = vp.get("scenes")
    if not isinstance(scenes, list) or len(scenes) == 0:
        result["errors"].append("scenes must be a non-empty list")
        return result

    result["scene_count"] = len(scenes)
    total_dur = 0.0
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            result["errors"].append(f"scene {i} is not a dict")
            continue
        if "scene_number" in sc:
            try:
                sn = int(sc["scene_number"])
                if sn < 1:
                    result["errors"].append(f"scene {i}: invalid scene_number")
            except (ValueError, TypeError):
                result["errors"].append(f"scene {i}: cannot parse scene_number")
        dur = sc.get("duration_seconds")
        if dur is not None:
            try:
                d = float(dur)
                if d < 0:
                    result["errors"].append(f"scene {i}: negative duration")
                total_dur += d
            except (ValueError, TypeError):
                result["warnings"].append(f"scene {i}: cannot parse duration")

    if total_dur > 0:
        result["total_duration_seconds"] = total_dur

    result["valid"] = len(result["errors"]) == 0
    return result
def validate_render_progress(rp: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False, "status": None, "errors": [], "warnings": [],
        "job_id": None, "tasks_total": None, "tasks_done": None,
        "current_stage": None, "failures": [], "scene_count": 0,
    }

    if not isinstance(rp, dict):
        result["errors"].append("render_progress is not a dict")
        return result

    result["status"] = rp.get("status")
    result["job_id"] = rp.get("job_id")
    result["tasks_total"] = rp.get("tasks_total")
    result["tasks_done"] = rp.get("tasks_done")
    result["current_stage"] = rp.get("current_stage")
    result["failures"] = rp.get("failures", [])

    critical_fields = ["job_id", "status", "tasks_total", "tasks_done",
                       "current_stage", "failures"]
    for field in critical_fields:
        if field not in rp:
            result["errors"].append(f"Missing field: {field}")

    if result["status"] not in COMPLETED_STATUSES:
        result["errors"].append(
            f"Render status '{result['status']}' is not 'completed'"
        )

    if isinstance(result["failures"], list) and len(result["failures"]) > 0:
        result["errors"].append(
            f"Non-empty failures: {result['failures']}"
        )
    elif isinstance(result["failures"], dict) and len(result["failures"]) > 0:
        result["errors"].append(
            f"Non-empty failures dict: {list(result['failures'])[:5]}"
        )

    scenes = rp.get("scenes")
    if isinstance(scenes, list):
        result["scene_count"] = len(scenes)

    result["valid"] = len(result["errors"]) == 0
    return result
def discover_optional_artifacts(job_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in sorted(OPTIONAL_ARTIFACTS):
        p = job_dir / name
        if p.is_dir() or p.exists():
            result[name] = "present"
        else:
            result[name] = "missing"
    return result
def verify_job_directory(job_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "passed": False,
        "overall_pass": False,
        "job_dir": str(job_dir),
        "visual_plan": {},
        "render_progress": {},
        "mp4": {},
        "optional_artifacts": {},
        "errors": [],
        "warnings": [],
    }

    def add_error(msg: str) -> None:
        result["errors"].append(msg)

    vp_path = job_dir / "visual_plan.json"
    rp_path = job_dir / "render_progress.json"

    if not vp_path.exists():
        add_error("Missing visual_plan.json")
        result["visual_plan"] = {"valid": False, "errors": ["File not found"]}
    else:
        try:
            with open(vp_path) as f:
                vp = json.load(f)
            vp_result = validate_visual_plan(vp)
            result["visual_plan"] = vp_result
            if not vp_result["valid"]:
                add_error(f"Visual plan invalid: {vp_result['errors']}")
            result["warnings"].extend(vp_result.get("warnings", []))
        except json.JSONDecodeError as e:
            result["visual_plan"] = {"valid": False, "errors": [f"Invalid JSON: {e}"]}
            add_error("visual_plan.json: invalid JSON")
        except OSError as e:
            result["visual_plan"] = {"valid": False, "errors": [str(e)]}
            add_error(f"visual_plan.json: {e}")
    if not rp_path.exists():
        add_error("Missing render_progress.json")
        result["render_progress"] = {"valid": False, "errors": ["File not found"]}
    else:
        try:
            with open(rp_path) as f:
                rp = json.load(f)
            rp_result = validate_render_progress(rp)
            result["render_progress"] = rp_result
            if not rp_result["valid"]:
                add_error(f"Render progress invalid: {rp_result['errors']}")
            result["warnings"].extend(rp_result.get("warnings", []))
        except json.JSONDecodeError as e:
            result["render_progress"] = {"valid": False, "errors": [f"Invalid JSON: {e}"]}
            add_error("render_progress.json: invalid JSON")
        except OSError as e:
            result["render_progress"] = {"valid": False, "errors": [str(e)]}
            add_error(f"render_progress.json: {e}")

    mp4_path = discover_mp4(job_dir)
    if mp4_path is None:
        add_error("No MP4 file found")
        result["mp4"] = {
            "valid": False, "exists": False, "path": None,
            "errors": ["No MP4 found"],
        }
    else:
        result["mp4"]["path"] = str(mp4_path)
        mp4_result = validate_mp4_with_ffprobe(mp4_path)
        result["mp4"].update({
            "valid": mp4_result["valid"],
            "exists": mp4_result["exists"],
            "non_zero_size": mp4_result["non_zero_size"],
            "parseable": mp4_result["parseable"],
            "video_stream_exists": mp4_result["video_stream_exists"],
            "duration_seconds": mp4_result["duration_seconds"],
            "width": mp4_result["width"],
            "height": mp4_result["height"],
            "fps": mp4_result["fps"],
            "audio_present": mp4_result["audio_present"],
            "codec": mp4_result["codec"],
            "errors": mp4_result["errors"],
        })
        if not mp4_result["valid"]:
            add_error(f"MP4 validation failed: {mp4_result['errors']}")

    result["optional_artifacts"] = discover_optional_artifacts(job_dir)

    vp_valid = bool(result["visual_plan"].get("valid", False))
    rp_valid = bool(result["render_progress"].get("valid", False))
    mp4_valid = bool(result["mp4"].get("valid", False))

    result["visual_plan_valid"] = vp_valid
    result["render_progress_valid"] = rp_valid
    result["mp4_valid"] = mp4_valid

    result["passed"] = bool(vp_valid and rp_valid and mp4_valid)
    result["overall_pass"] = result["passed"]

    result["render_status"] = result["render_progress"].get("status")
    result["scene_count"] = result["render_progress"].get("scene_count", 0)

    result["duration_seconds"] = result["mp4"].get("duration_seconds")
    result["width"] = result["mp4"].get("width")
    result["height"] = result["mp4"].get("height")
    result["fps"] = result["mp4"].get("fps")

    return result
def main() -> int:
    parser = argparse.ArgumentParser(description="Day-8 verification harness")
    parser.add_argument("--job-dir", type=str, required=True,
                        help="Path to render job directory")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON path (default: <job-dir>/day8_verification.json)")
    args = parser.parse_args()

    job_dir = Path(args.job_dir).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        print(f"ERROR: Invalid job directory: {job_dir}", file=sys.stderr)
        return 1

    result = verify_job_directory(job_dir)

    output_path = Path(args.output) if args.output else (job_dir / "day8_verification.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    status = "PASS" if result["passed"] else "FAIL"
    print(f"Day-8 Verification: {status}")
    print(f"  Job directory: {result['job_dir']}")
    print(f"  Visual plan: {'valid' if result['visual_plan'].get('valid') else 'invalid'}")
    print(f"  Render status: {result['render_progress'].get('status')}")
    print(f"  Render progress: {'valid' if result['render_progress'].get('valid') else 'invalid'}")

    mp4_info = result.get("mp4", {})
    if mp4_info.get("path"):
        print(f"  MP4: {mp4_info['path']}")
        if mp4_info.get("valid"):
            dur = mp4_info.get("duration_seconds") or 0
            print(f"    Duration: {dur:.2f}s")
            print(f"    Resolution: {mp4_info.get('width', '?')}x{mp4_info.get('height', '?')}")
            print(f"    FPS: {mp4_info.get('fps', 0):.2f}")
            print(f"    Audio: {'yes' if mp4_info.get('audio_present') else 'no'}")
    else:
        print("  MP4: NOT FOUND")

    print(f"  Output: {output_path}")

    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result["errors"]:
            print(f"  - {err}")

    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warn in result["warnings"]:
            print(f"  - {warn}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())