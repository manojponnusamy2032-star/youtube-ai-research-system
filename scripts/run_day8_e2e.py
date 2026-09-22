#!/usr/bin/env python3
"""Day-8 E2E: smallest REAL YAIRS pipeline execution."""

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
from src.orchestration.agents.script.mock import MockScriptAgent  # noqa: E402
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
from src.orchestration.schemas.script import ScriptPackage  # noqa: E402
from src.orchestration.schemas.strategy import StrategyPackage  # noqa: E402

E2E_STAGES = [STAGE_RESEARCH, STAGE_STRATEGY, STAGE_SCRIPT, STAGE_VISUAL_PLAN, STAGE_RENDER]
TINY_SCENES = 2
TINY_SCENE_SECONDS = 3


class TinyScriptAgent(MockScriptAgent):
    """Deterministic 2-section x 3s script (~6s total video)."""

    def run(self, request: StrategyPackage) -> ScriptPackage:
        full = super().run(request)
        sections = full.sections[:TINY_SCENES]
        for section in sections:
            section.duration_seconds = TINY_SCENE_SECONDS
        total = sum(s.duration_seconds for s in sections)
        return ScriptPackage(
            topic=full.topic,
            title=full.title,
            hook=full.hook,
            sections=sections,
            call_to_action=full.call_to_action,
            total_duration_seconds=total,
        )
def probe_mp4(path: Path) -> dict:
    info = {"duration": 0.0, "fps": 0.0, "width": 0, "height": 0, "audio": False}
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return info
        data = json.loads(proc.stdout)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if video is None:
            return info
        try:
            fmt = data.get("format", {})
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
        info["audio"] = audio is not None
    except Exception:
        pass
    return info

def build_render_progress(job, wall_ms: float, mp4_info: dict, fps_cfg: int) -> dict:
    ok = job.status == JobStatus.COMPLETED
    fps = mp4_info["fps"] or float(fps_cfg)
    duration = mp4_info["duration"] or float(job.visual_plan.total_duration_seconds or 0)
    rendered_frames = int(round(duration * fps)) if duration > 0 and fps > 0 else 0
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
        "total_frames": rendered_frames,
        "rendered_frames": rendered_frames,
        "frames_per_second": float(fps),
        "frame_ms": float(1000.0 / fps) if fps > 0 else 0.0,
        "remaining": 0,
        "eta_seconds": 0,
        "tasks_total": len(E2E_STAGES),
        "tasks_done": len(E2E_STAGES) if ok else len(succeeded),
        "current_stage": job.current_stage,
        "failures": [] if ok else [job.error or "pipeline failed"],
        "scenes": scenes,
    }


def stage_runtimes(job) -> dict:
    runtimes: dict = {}
    for stage in E2E_STAGES:
        record = (job.stages or {}).get(stage)
        if record is None or record.started_at is None or record.finished_at is None:
            runtimes[stage] = None
            continue
        try:
            runtimes[stage] = round((record.finished_at - record.started_at).total_seconds(), 3)
        except Exception:
            runtimes[stage] = None
    return runtimes


def main() -> int:
    parser = argparse.ArgumentParser(description="Day-8 real E2E.")
    parser.add_argument("--output-dir", default="output/day8_e2e")
    parser.add_argument("--topic", default="Day-8 tiny render check")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=12)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    agents = build_default_stage_agents(include_qc=False)
    agents[STAGE_SCRIPT] = TinyScriptAgent()
    registry = PipelineRegistry(stages=list(E2E_STAGES))
    for stage in E2E_STAGES:
        registry.register(agents[stage], stage=stage)

    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(output_dir), stages=list(E2E_STAGES))
    orch.render_config = {"width": args.width, "height": args.height, "fps": args.fps}

    print(f"[day8-e2e] topic: {args.topic!r} -> {output_dir}")
    wall_start = time.perf_counter()
    job = orch.execute(args.topic)
    wall_ms = (time.perf_counter() - wall_start) * 1000.0
    job_dir = output_dir / job.job_id
    print(f"[day8-e2e] job={job.job_id} status={job.status.value} wall={wall_ms / 1000.0:.2f}s")
    runtimes = stage_runtimes(job)
    for stage in E2E_STAGES:
        print(f"[day8-e2e] stage {stage}: {runtimes[stage]}s")

    if job.status != JobStatus.COMPLETED:
        print(f"[day8-e2e] PIPELINE FAILED: {job.error}")
        doc = {"passed": False, "job_id": job.job_id, "job_dir": str(job_dir),
               "stages": E2E_STAGES, "stage_runtimes_seconds": runtimes,
               "wall_seconds": round(wall_ms / 1000.0, 3), "error": job.error, "verifier": None}
        (output_dir / "day8_e2e_result.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return 1

    rendered_mp4 = job_dir / "video.mp4"
    if not rendered_mp4.exists():
        print("[day8-e2e] success reported but video.mp4 missing")
        return 1
    canonical_mp4 = job_dir / "final_video.mp4"
    shutil.copy2(rendered_mp4, canonical_mp4)

    mp4_info = probe_mp4(canonical_mp4)
    print(f"[day8-e2e] mp4: {mp4_info['duration']:.2f}s "
          f"{mp4_info['width']}x{mp4_info['height']} fps={mp4_info['fps']:.2f} audio={mp4_info['audio']}")

    progress = build_render_progress(job, wall_ms, mp4_info, args.fps)
    (job_dir / "render_progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")

    verify = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "run_day8_verification.py"),
         "--job-dir", str(job_dir)], capture_output=True, text=True)
    print(verify.stdout)
    if verify.stderr:
        print(verify.stderr, file=sys.stderr)
    verifier_doc = None
    verifier_path = job_dir / "day8_verification.json"
    if verifier_path.exists():
        try:
            verifier_doc = json.loads(verifier_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            verifier_doc = None

    doc = {
        "passed": bool(verify.returncode == 0),
        "input": {"topic": args.topic, "width": args.width, "height": args.height, "fps": args.fps},
        "job_id": job.job_id,
        "job_dir": str(job_dir),
        "stages": E2E_STAGES,
        "stage_runtimes_seconds": runtimes,
        "wall_seconds": round(wall_ms / 1000.0, 3),
        "final_mp4": str(canonical_mp4),
        "mp4": mp4_info,
        "render_progress_status": progress["status"],
        "verifier_exit_code": verify.returncode,
        "verifier": verifier_doc,
    }
    (output_dir / "day8_e2e_result.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"[day8-e2e] verifier exit={verify.returncode} passed={doc['passed']}")
    return 0 if doc["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

