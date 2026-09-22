#!/usr/bin/env python3
"""Day-10 profiling: measure where the YAIRS 1080p30 render time goes.

Wraps existing production classes with perf_counter timing at runtime
(no production code is modified):

    VideoPipelineOrchestrator stage records  -> per-stage timings
    YairsRendererAdapter.run                 -> render stage (job.stages)
      RenderPipelineOrchestrator.run         -> render_pipeline_total
        StickmanRenderer.render              -> scene_render_total (per scene)
          StickmanRenderer._generate_frame   -> frame_generation (per frame)
      FinalMediaOrchestrator:
        VideoAssembler.assemble              -> scene_assembly
        TTSAudioRenderer.render              -> audio_generation
        MediaMuxer.mux                       -> final_mux

Known overlaps (documented, not hidden):
  * _generate_frame timing excludes stdin writes. FFmpeg encodes concurrently;
    its independent encode time cannot be isolated by method wall timers.
    ffmpeg_encode is null, never the scene-minus-frame residual.
  * render_pipeline_total contains a small orchestration residual beyond
    the scene/audio/assembly/mux buckets.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator  # noqa: E402
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
from src.services.media_muxer import MediaMuxer  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402
from src.services.tts_audio_renderer import TTSAudioRenderer  # noqa: E402
from src.services.video_assembler import VideoAssembler  # noqa: E402

PIPELINE_STAGES = [STAGE_RESEARCH, STAGE_STRATEGY, STAGE_SCRIPT, STAGE_VISUAL_PLAN, STAGE_RENDER]

# Day-9 measured baseline (output/day9_benchmark/day9_benchmark_result.json).
DAY9_BASELINE = {
    "source": "output/day9_benchmark/day9_benchmark_result.json",
    "render_seconds": 511.471,
    "total_wall_seconds": 511.488,
    "video_duration_seconds": 59.967,
    "total_frames": 1799,
    "real_time_factor": 8.5293,
    "frames_per_second_rendered": 3.517,
}

TIMING: dict[str, float] = {
    "render_pipeline_total": 0.0,
    "scene_render_total": 0.0,
    "frame_generation": 0.0,
    "audio_generation": 0.0,
    "scene_assembly": 0.0,
    "final_mux": 0.0,
}
CALLS: dict[str, int] = {key: 0 for key in TIMING}
SCENES: list[dict[str, Any]] = []


def _timed(cls: type, method_name: str, bucket: str,
           pre: Callable | None = None, post: Callable | None = None) -> None:
    """Wrap a class method with perf_counter timing into TIMING[bucket]."""
    original = getattr(cls, method_name)

    def wrapper(self, *args, **kwargs):
        if pre is not None:
            pre(self, args, kwargs)
        start = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            TIMING[bucket] += elapsed
            CALLS[bucket] += 1
            if post is not None:
                post(self, args, kwargs, elapsed)

    setattr(cls, method_name, wrapper)


def install_instrumentation() -> None:
    """Install timing wrappers on the production render path classes."""

    def scene_pre(renderer, args, kwargs):
        request = args[0] if args else None
        job = getattr(request, "job", {}) or {}
        SCENES.append({
            "scene_id": str(job.get("job_id", "unknown")),
            "duration_seconds": float(job.get("duration_seconds", 0) or 0),
            "frame_count": 0,
            "render_seconds": None,
            "rendered_fps": None,
        })

    def scene_post(renderer, args, kwargs, elapsed):
        if SCENES:
            record = SCENES[-1]
            record["render_seconds"] = round(elapsed, 3)
            record["rendered_fps"] = (
                round(record["frame_count"] / elapsed, 3) if elapsed > 0 else None
            )

    def frame_pre(renderer, args, kwargs):
        if SCENES:
            SCENES[-1]["frame_count"] += 1

    _timed(RenderPipelineOrchestrator, "run", "render_pipeline_total")
    _timed(StickmanRenderer, "render", "scene_render_total",
           pre=scene_pre, post=scene_post)
    _timed(StickmanRenderer, "_generate_frame", "frame_generation", pre=frame_pre)
    _timed(VideoAssembler, "assemble", "scene_assembly")



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
            capture_output=True, text=True, timeout=120,
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
    """Per-stage timings from the orchestrator's own StageRecords."""
    runtimes: dict = {}
    for stage in PIPELINE_STAGES:
        record = (job.stages or {}).get(stage)
        if record is None or record.started_at is None or record.finished_at is None:
            runtimes[stage] = None
            continue
        try:
            runtimes[stage] = round((record.finished_at - record.started_at).total_seconds(), 3)
        except Exception:
            runtimes[stage] = None
    return runtimes


from src.services.ffmpeg_audio_renderer import FFmpegAudioRenderer

ACTIVE_SCENE = False
AUDIO_DEPTH = 0


def install_extra_instrumentation() -> None:
    """Measure nested audio once and distinguish scene muxes from final mux."""
    global ACTIVE_SCENE
    original_scene = StickmanRenderer.render
    def scene(self, *args, **kwargs):
        global ACTIVE_SCENE
        ACTIVE_SCENE = True
        try:
            return original_scene(self, *args, **kwargs)
        finally:
            ACTIVE_SCENE = False
    StickmanRenderer.render = scene
    for cls in (TTSAudioRenderer, FFmpegAudioRenderer):
        original = cls.render
        def audio(self, *args, _original=original, **kwargs):
            global AUDIO_DEPTH
            outer = AUDIO_DEPTH == 0
            AUDIO_DEPTH += 1
            start = time.perf_counter()
            try:
                return _original(self, *args, **kwargs)
            finally:
                AUDIO_DEPTH -= 1
                if outer:
                    TIMING['audio_generation'] += time.perf_counter() - start
                    CALLS['audio_generation'] += 1
        cls.render = audio
    original_mux = MediaMuxer.mux
    def mux(self, *args, **kwargs):
        bucket = 'scene_mux' if ACTIVE_SCENE else 'final_mux'
        start = time.perf_counter()
        try:
            return original_mux(self, *args, **kwargs)
        finally:
            TIMING[bucket] += time.perf_counter() - start
            CALLS[bucket] += 1
    MediaMuxer.mux = mux
    TIMING['scene_mux'] = 0.0
    CALLS['scene_mux'] = 0
    for method, bucket in (('_draw_rect', 'rectangle_drawing'),
                           ('_draw_text_elements', 'text_drawing')):
        TIMING[bucket] = 0.0
        CALLS[bucket] = 0
        _timed(StickmanRenderer, method, bucket)


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile unchanged Day-9 1080p30 rendering.")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "output/day10_profiling"))
    args = parser.parse_args()
    root = Path(args.output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    install_instrumentation()
    install_extra_instrumentation()
    agents = build_default_stage_agents(include_qc=False)
    registry = PipelineRegistry(stages=PIPELINE_STAGES)
    for stage in PIPELINE_STAGES:
        registry.register(agents[stage], stage=stage)
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(root / "jobs"),
                                     stages=PIPELINE_STAGES)
    orch.render_config = {"width": 1920, "height": 1080, "fps": 30}
    start = time.perf_counter()
    job = orch.execute("Day-9 realistic 1080p30 benchmark")
    wall = time.perf_counter() - start
    job_dir = root / "jobs" / job.job_id
    mp4_path = job_dir / "video.mp4"
    metadata = probe_mp4(mp4_path)
    render = stage_runtimes(job)[STAGE_RENDER]
    duration = metadata["duration"]
    errors = [] if job.status == JobStatus.COMPLETED else [job.error]
    verify = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts/run_day8_verification.py"),
                             "--job-dir", str(job_dir)], capture_output=True, text=True)
    (root / "verifier.log").write_text(verify.stdout + verify.stderr, encoding="utf-8")
    if verify.returncode:
        errors.append("Day-8 verifier failed; see verifier.log and job/day8_verification.json")
    notes = [
        "Same default content agents as Day 9 (deterministic mock research/strategy/script/visual); real rendering is unchanged.",
        "Runtime wrappers use perf_counter; overhead is included, not independently measured.",
        "frame_generation measures _generate_frame only, including raw bytearray drawing and PIL text; excludes stdin writes and motion/pose.",
        "ffmpeg_encode is null: FFmpeg runs concurrently with frame generation. Scene residual also includes pipe writes, motion/pose, process startup/drain and scene audio, not isolated encoding.",
        "Nested rectangle/text timings overlap frame_generation; frame_generation overlaps scene_render_total; all overlap total_render.",
        "Frame counts per scene count _generate_frame invocations; final MP4 count is ffprobe decoded frames.",
        "total_wall_seconds covers orchestrator execution, excluding setup, ffprobe and verification, matching Day 9.",
        "No render_progress.json synthesized; missing producer artifact is reported by the unchanged verifier.",
    ]
    report = {
        "resolution": "1920x1080", "fps": 30,
        "video_duration_seconds": duration, "frame_count": metadata["total_frames"],
        "total_wall_seconds": wall, "render_seconds": render,
        "rendered_fps": metadata["total_frames"] / render if render else None,
        "real_time_factor": render / duration if duration else None,
        "breakdown": {**TIMING, "ffmpeg_encode": None}, "calls": CALLS,
        "scenes": SCENES, "notes": notes, "errors": errors,
        "stage_timings": stage_runtimes(job), "video": metadata,
        "job_dir": str(job_dir), "mp4_path": str(mp4_path),
        "verifier_exit_code": verify.returncode,
        "day9": DAY9_BASELINE,
        "difference_seconds": render - DAY9_BASELINE["render_seconds"],
        "percentage_difference": (render / DAY9_BASELINE["render_seconds"] - 1) * 100,
    }
    (root / "day10_render_profile.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_report(root, report)
    print(json.dumps(report, indent=2), flush=True)
    return 1 if errors else 0


def write_report(root: Path, report: dict) -> None:
    """Persist measured evidence, including unsuccessful verification."""
    render = report['render_seconds']
    b = report['breakdown']
    dominant = ('frame generation' if b['frame_generation'] > render * 0.5
                else 'mixed/uncertain')
    report['dominant_bottleneck'] = dominant
    report['notes'].append('audio_generation includes scene FFmpeg audio and TTS/fallback, counted once per outer call; scene audio and scene_mux overlap scene_render_total. final_mux excludes scene muxes.')
    target = ('Investigate replacing the measured Python raster drawing loops with equivalent bulk drawing; preserve visuals and validate before adoption.'
              if dominant == 'frame generation' else
              'Isolate the largest unresolved render interval before choosing an optimization.')
    command = f'python scripts/run_day10_profiling.py --output-dir "{root}"'
    lines = ['# Day 10 render profile', '', '## A. Exact command used',
             f'`{command}`', '', '## B. Benchmark configuration',
             '1920x1080, 30 FPS, six unchanged Day-9 representative scenes; production real renderer with execution enabled. Upstream default agents are deterministic mocks, exactly as in Day 9.',
             '', '## C. Day-9 baseline', 'Render: 511.471s; wall: 511.488s; 59.967s output, 1799 frames.',
             '', '## D. Day-10 measured timings',
             '```json', json.dumps(report['stage_timings'], indent=2), '```',
             f"Total pipeline wall: {report['total_wall_seconds']:.6f}s",
             '', '## E. Per-scene timings',
             '| Scene | Duration | Frames generated | Render seconds | Rendered FPS |',
             '|---|---:|---:|---:|---:|']
    for s in report['scenes']:
        lines.append(f"| {s['scene_id']} | {s['duration_seconds']} | {s['frame_count']} | {s['render_seconds']} | {s['rendered_fps']} |")
    lines += ['', '## F. Rendered FPS', str(report['rendered_fps']),
              '', '## G. Real-time factor', str(report['real_time_factor']),
              '', '## H. Bottleneck breakdown', '```json', json.dumps(b, indent=2), '```',
              *['- ' + n for n in report['notes']],
              '', '## I. Comparison with Day 9',
              f"Day 9: 511.471s; Day 10: {render}s; difference: {report['difference_seconds']:.6f}s ({report['percentage_difference']:.3f}%). This includes instrumentation and run-to-run variation, not a measured overhead estimate.",
              '', '## J. Dominant bottleneck', dominant,
              '', '## K. Recommended next optimization', target,
              '', '## L. Files changed',
              str(Path(__file__).resolve()),
              str(root / 'day10_render_profile.json'), str(root / 'DAY10_REPORT.md'),
              f'New pipeline artifacts under {report["job_dir"]}; verifier.log and execution logs under {root}. Production sources and validators unchanged.',
              '', '## Output and verification', '```json', json.dumps(report['video'], indent=2), '```',
              f"Verifier exit: {report['verifier_exit_code']}",
              *['- ' + str(e) for e in report['errors']]]
    (root / 'DAY10_REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (root / 'day10_render_profile.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())


