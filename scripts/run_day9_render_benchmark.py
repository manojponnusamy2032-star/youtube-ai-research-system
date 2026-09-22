#!/usr/bin/env python3
"""Day-9 benchmark: realistic 1080p30 YAIRS render, timed per stage."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestration.agents.factory import build_default_stage_agents  # noqa: E402
from src.orchestration.orchestrator import VideoPipelineOrchestrator  # noqa: E402
from src.orchestration.pipeline import (  # noqa: E402
    STAGE_RENDER,
    STAGE_RESEARCH,
    STAGE_SCRIPT,
    STAGE_STRATEGY,
    STAGE_VISUAL_PLAN,
)
from src.orchestration.registry import PipelineRegistry  # noqa: E402
from src.orchestration.schemas.job import JobStatus  # noqa: E402

BENCH_STAGES = [STAGE_RESEARCH, STAGE_STRATEGY, STAGE_SCRIPT, STAGE_VISUAL_PLAN, STAGE_RENDER]

DAY8_BASELINE = {
    "resolution": "320x240",
    "fps": 12,
    "video_duration_seconds": 6.0,
    "render_seconds": 9.46,
}


def probe_mp4(path: Path) -> dict:
    """Real ffprobe metadata for the rendered MP4."""
    info = {"duration": 0.0, "fps": 0.0, "width": 0, "height": 0,
            "video_codec": "", "audio_codec": "", "audio": False,
            "size_bytes": 0, "total_frames": 0}
    try:
        info["size_bytes"] = path.stat().st_size
    except OSError:
        return info
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", "-count_frames", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return info
        data = json.loads(proc.stdout)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if video is None:
            return info
        fmt = data.get("format", {})
        try:
            info["duration"] = float(video.get("duration") or fmt.get("duration") or 0)
        except (ValueError, TypeError):
            info["duration"] = 0.0
        try:
            num, den = str(video.get("r_frame_rate", "0/1")).split("/")
            info["fps"] = float(num) / float(den) if int(den) else 0.0
        except (ValueError, ZeroDivisionError, AttributeError):
            info["fps"] = 0.0
        info["width"] = int(video.get("width") or 0)
        info["height"] = int(video.get("height") or 0)
        info["video_codec"] = str(video.get("codec_name") or "")
        nb = video.get("nb_read_frames") or video.get("nb_frames")
        try:
            info["total_frames"] = int(nb)
        except (ValueError, TypeError):
            info["total_frames"] = 0
        if audio is not None:
            info["audio"] = True
            info["audio_codec"] = str(audio.get("codec_name") or "")
    except Exception:
        pass
    return info


def stage_runtimes(job) -> dict:
    runtimes: dict = {}
    for stage in BENCH_STAGES:
        record = (job.stages or {}).get(stage)
        if record is None or record.started_at is None or record.finished_at is None:
            runtimes[stage] = None
            continue
        try:
            runtimes[stage] = round((record.finished_at - record.started_at).total_seconds(), 3)
        except Exception:
            runtimes[stage] = None
    return runtimes


def build_render_progress(job, wall_ms: float, mp4_info: dict, fps_cfg: int) -> dict:
    ok = job.status == JobStatus.COMPLETED
    fps = mp4_info["fps"] or float(fps_cfg)
    duration = mp4_info["duration"] or float(job.visual_plan.total_duration_seconds or 0)
    rendered = int(round(duration * fps)) if duration > 0 and fps > 0 else 0
    succeeded = [s for s, r in (job.stages or {}).items()
                 if getattr(r, "status", None) and r.status.value == "succeeded"]
    scenes = []
    if job.visual_plan is not None:
        for scene in job.visual_plan.scenes:
            scenes.append({
                "scene_number": scene.scene_number,
                "status": "completed" if ok else "failed",
                "duration_seconds": float(scene.duration_seconds),
            })
    now = datetime.now(timezone.utc)
    created = getattr(job, "created_at", None) or now
    completed = getattr(job, "completed_at", None) or now
    return {
        "job_id": job.job_id,
        "started_at": created.isoformat(),
        "completed_at": completed.isoformat(),
        "status": "completed" if ok else "failed",
        "total_ms": int(wall_ms),
        "work_ms": int(wall_ms),
        "total_frames": rendered,
        "rendered_frames": rendered,
        "frames_per_second": float(fps),
        "frame_ms": float(1000.0 / fps) if fps > 0 else 0.0,
        "remaining": 0,
        "eta_seconds": 0,
        "tasks_total": len(BENCH_STAGES),
        "tasks_done": len(BENCH_STAGES) if ok else len(succeeded),
        "current_stage": job.current_stage,
        "failures": [] if ok else [job.error or "pipeline failed"],
        "scenes": scenes,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Day-9 realistic 1080p30 render benchmark.")
    parser.add_argument("--output-dir", default="output/day9_benchmark/jobs")
    parser.add_argument("--result-path", default="output/day9_benchmark/day9_benchmark_result.json")
    parser.add_argument("--topic", default="Day-9 realistic 1080p30 benchmark")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = Path(args.result_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    agents = build_default_stage_agents(include_qc=False)
    registry = PipelineRegistry(stages=list(BENCH_STAGES))
    for stage in BENCH_STAGES:
        registry.register(agents[stage], stage=stage)

    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(output_dir), stages=list(BENCH_STAGES))
    orch.render_config = {"width": args.width, "height": args.height, "fps": args.fps}

    config = {
        "topic": args.topic,
        "width": args.width,
        "height": args.height,
        "fps": args.fps,
        "audio": "pipeline default (enabled if supported)",
        "stages": list(BENCH_STAGES),
    }
    print(f"[day9] config: {args.width}x{args.height}@{args.fps} topic={args.topic!r}")

    wall_start = time.perf_counter()
    job = orch.execute(args.topic)
    wall_seconds = time.perf_counter() - wall_start

    job_dir = output_dir / job.job_id
    runtimes = stage_runtimes(job)
    for stage in BENCH_STAGES:
        print(f"[day9] stage {stage}: {runtimes[stage]}s")
    print(f"[day9] job={job.job_id} status={job.status.value} wall={wall_seconds:.2f}s")

    result: dict = {
        "benchmark_configuration": config,
        "job_id": job.job_id,
        "job_dir": str(job_dir),
        "stage_timings_seconds": dict(runtimes),
        "audio_stage_note": "audio/assembly combined inside render stage",
        "total_wall_seconds": round(wall_seconds, 3),
        "video": {},
        "performance": {},
        "verifier": None,
        "errors": [],
        "warnings": [],
    }

    if job.status != JobStatus.COMPLETED:
        result["errors"].append(job.error or "pipeline failed")
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[day9] PIPELINE FAILED: {job.error}")
        return 1

    render_seconds = runtimes.get(STAGE_RENDER)
    result["stage_timings_seconds"]["render_detail"] = (
        "render covers scene rendering + audio + assembly/mux"
    )

    rendered_mp4 = job_dir / "video.mp4"
    canonical_mp4 = job_dir / "final_video.mp4"
    if rendered_mp4.exists():
        shutil.copy2(rendered_mp4, canonical_mp4)

    mp4 = probe_mp4(canonical_mp4)
    if mp4["total_frames"] > 0:
        total_frames = mp4["total_frames"]
    elif mp4["duration"] > 0:
        total_frames = int(round(mp4["duration"] * mp4["fps"]))
    else:
        total_frames = 0
    rtf = None
    if render_seconds and mp4["duration"] > 0:
        rtf = render_seconds / mp4["duration"]
    fps_rendered = None
    if render_seconds and total_frames > 0:
        fps_rendered = total_frames / render_seconds
    result["video"] = {
        "path": str(canonical_mp4),
        "duration_seconds": round(mp4["duration"], 3),
        "width": mp4["width"],
        "height": mp4["height"],
        "fps": round(mp4["fps"], 3),
        "video_codec": mp4["video_codec"],
        "audio_codec": mp4["audio_codec"],
        "audio_present": mp4["audio"],
        "size_bytes": mp4["size_bytes"],
        "total_frames": total_frames,
    }
    result["performance"] = {
        "render_seconds": render_seconds,
        "real_time_factor": round(rtf, 4) if rtf is not None else None,
        "frames_per_second_rendered": round(fps_rendered, 3) if fps_rendered is not None else None,
        "render_time_per_video_second": round(rtf, 4) if rtf is not None else None,
    }
    print(f"[day9] mp4: {mp4['duration']:.2f}s {mp4['width']}x{mp4['height']} fps={mp4['fps']:.2f}")
    if rtf is not None:
        print(f"[day9] real_time_factor={rtf:.3f}x fps_rendered={fps_rendered}")

    progress = build_render_progress(job, wall_seconds * 1000.0, mp4, args.fps)
    (job_dir / "render_progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")

    verify_cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "run_day8_verification.py"),
                  "--job-dir", str(job_dir)]
    verify = subprocess.run(verify_cmd, capture_output=True, text=True)
    print(verify.stdout)
    if verify.stderr:
        print(verify.stderr, file=sys.stderr)
    if (job_dir / "day8_verification.json").exists():
        try:
            result["verifier"] = json.loads((job_dir / "day8_verification.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            result["warnings"].append(f"verifier json unreadable: {exc}")
    result["verifier_exit_code"] = verify.returncode
    result["comparison_day8_vs_day9"] = {
        "day8": dict(DAY8_BASELINE),
        "day9": {
            "resolution": f"{mp4['width']}x{mp4['height']}",
            "fps": round(mp4["fps"], 3),
            "video_duration_seconds": round(mp4["duration"], 3),
            "render_seconds": render_seconds,
        },
    }
    result["passed"] = verify.returncode == 0
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[day9] verifier exit={verify.returncode} passed={result['passed']} -> {result_path}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

