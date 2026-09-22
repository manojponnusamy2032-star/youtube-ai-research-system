"""Day-13 verification run: unchanged six-scene workload through real production rendering.

Same saved six-scene plan as Days 11-12 (identical plan bytes), fresh real
System.Speech audio, fresh scene media and a fresh MP4. No mocks, no reused
media, no shortened workload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from inspect import getsource

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.day12_instrumentation import FrameProfiler, delta
from src.adapters.renderer.yairs import YairsRendererAdapter
from src.orchestration.schemas.production import ProductionRequest
from src.orchestration.schemas.visual import VisualPlan
from src.services.stickman_renderer import StickmanRenderer
from src.services.system_speech_tts_service import SystemSpeechTTSService
from src.services.video_assembler import VideoAssembler
from src.services.media_muxer import MediaMuxer
from src.services.tts_audio_renderer import TTSAudioRenderer
from src.services.ffmpeg_audio_renderer import FFmpegAudioRenderer

DAY12_BASELINE = {
    'line_drawing_seconds': 255.41214580011365,
    'frame_generation_seconds': 364.60893520001446,
    'render_seconds': 393.00445000000036,
    'rendered_fps': 4.577556310113024,
    'real_time_factor': 6.553715083081078,
}
PLAN_SHA256 = '9a269915f3ce680a83c50c25fbca2a19d4d2d60a0f9f794895b46ea945632392'


def save(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=PROJECT_ROOT / 'output/day13_optimization')
    root = parser.parse_args().output_dir.resolve()
    job_dir = root / 'jobs/job_001'
    job_dir.mkdir(parents=True, exist_ok=False)
    work = root / 'work'
    work.mkdir(exist_ok=False)
    source = PROJECT_ROOT / 'output/day12_profiling/jobs/job_001/visual_plan.json'
    plan_bytes = source.read_bytes()
    assert hashlib.sha256(plan_bytes).hexdigest() == PLAN_SHA256, 'plan changed'
    plan = VisualPlan.model_validate_json(plan_bytes)
    assert [s.duration_seconds for s in plan.scenes] == [11, 12, 10, 8, 9, 12]
    assert len(plan.render_job_plan['jobs']) == 6
    (job_dir / 'visual_plan.json').write_bytes(plan_bytes)
    protected = [PROJECT_ROOT / 'src/services/stickman_renderer.py',
                 PROJECT_ROOT / 'scripts/run_day8_verification.py']
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    save(root / 'source_hashes_before.json', hashes)
    # Confirm the optimized line path (and the Day-11 rectangle path) are active.
    line_source = getsource(StickmanRenderer._draw_line)
    rect_source = getsource(StickmanRenderer._draw_rect)
    assert 'stamp_has_pixels' in line_source, 'off-screen line guard not active'
    assert 'frame[base:base + len(scanline)] = scanline' in rect_source, 'Day-11 rect path missing'
    os.chdir(work)  # Fresh ordinary output paths, no prior scene/audio media.
    tts = SystemSpeechTTSService(output_directory=str(work / 'output/audio'))
    if not tts.is_available():
        raise RuntimeError('Real System.Speech unavailable; no mock fallback allowed')
    adapter = YairsRendererAdapter(tts_service=tts)
    request = ProductionRequest(job_id='job_001', visual_plan=plan,
                                output_path=str(job_dir / 'video.mp4'),
                                render_config={'width': 1920, 'height': 1080, 'fps': 30})
    profiler = FrameProfiler().install()
    scenes = []
    stages = {}
    originals = []
    original_scene = StickmanRenderer.render

    def scene(self, request):
        before = profiler.snapshot()
        start = time.perf_counter()
        result = original_scene(self, request)
        elapsed = time.perf_counter() - start
        measurements = delta(profiler.snapshot(), before)
        record = {'scene_id': request.job['job_id'],
                  'duration': request.job['duration_seconds'],
                  'render_seconds': elapsed,
                  'rendered_fps': measurements['frame_count'] / elapsed,
                  'status': result.get('status'), **measurements}
        scenes.append(record)
        save(root / 'scene_measurements.json', scenes)
        print('SCENE', record['scene_id'], elapsed, flush=True)
        return result

    StickmanRenderer.render = scene

    for cls, method in ((VideoAssembler, 'assemble'), (MediaMuxer, 'mux'),
                        (TTSAudioRenderer, 'render'), (FFmpegAudioRenderer, 'render')):
        original = getattr(cls, method)
        label = cls.__name__ + '.' + method

        def measured(*a, _original=original, _label=label, **kw):
            start = time.perf_counter()
            try:
                return _original(*a, **kw)
            finally:
                stages[_label] = stages.get(_label, 0.0) + time.perf_counter() - start

        originals.append((cls, method, original))
        setattr(cls, method, measured)
    start = time.perf_counter()
    try:
        artifact = adapter.run(request)
        wall = time.perf_counter() - start
    finally:
        profiler.close()
        StickmanRenderer.render = original_scene
        for cls, method, original in originals:
            setattr(cls, method, original)
    save(job_dir / 'video_artifact.json', artifact.model_dump(mode='json'))
    raw = profiler.snapshot()
    save(root / 'raw_timings.json', {'render_seconds': wall, 'profile': raw, 'scenes': scenes, 'stages': stages})
    finish(root, job_dir, source, plan_bytes, protected, hashes, artifact, raw, scenes, stages, wall)
    return 0 if artifact.status == 'completed' else 1
def finish(root, job_dir, source, plan_bytes, protected, hashes, artifact, raw, scenes, stages, wall):
    mp4 = job_dir / 'video.mp4'
    probe = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams',
                            '-show_format', '-of', 'json', str(mp4)], capture_output=True, text=True)
    (root / 'independent_ffprobe.json').write_text(probe.stdout, encoding='utf-8')
    (root / 'ffprobe.stderr.log').write_text(probe.stderr, encoding='utf-8')
    verify = subprocess.run([sys.executable, str(PROJECT_ROOT / 'scripts/run_day8_verification.py'),
                             '--job-dir', str(job_dir)], capture_output=True, text=True)
    (root / 'verifier.log').write_text(verify.stdout + verify.stderr, encoding='utf-8')
    media = json.loads(probe.stdout) if probe.returncode == 0 else {}
    video = next((s for s in media.get('streams', []) if s['codec_type'] == 'video'), {})
    audio = next((s for s in media.get('streams', []) if s['codec_type'] == 'audio'), {})
    duration = float(video['duration']) if 'duration' in video else None
    frames = int(video['nb_read_frames']) if 'nb_read_frames' in video else None
    breakdown = {k: raw['exclusive'].get(k, 0.0) for k in
                 ('rectangles', 'text', 'lines', 'ellipses', 'characters', 'background',
                  'compositing', 'geometry', 'other', 'image_copies')}
    breakdown.update(polygons=0.0, alpha_blending=None)
    overhead = raw['frame_generation_seconds'] - sum(v for v in breakdown.values() if v is not None)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    save(root / 'source_hashes_after.json', after)
    measured = {
        'line_drawing_seconds': breakdown['lines'],
        'frame_generation_seconds': raw['frame_generation_seconds'],
        'render_seconds': wall,
        'rendered_fps': (frames / wall) if frames else None,
        'real_time_factor': (wall / duration) if duration else None,
    }
    comparison = {}
    for key, baseline in DAY12_BASELINE.items():
        value = measured[key]
        entry = {'day12': baseline, 'day13': value}
        if value is not None and baseline:
            entry['change'] = value - baseline
            entry['percent_change'] = (value - baseline) / baseline * 100.0
        comparison[key] = entry
    report = {
        'resolution': '1920x1080', 'fps': 30, 'video_duration_seconds': duration,
        'frame_count': frames, 'generated_frame_count': raw['frame_count'],
        'total_wall_seconds': wall, 'render_seconds': wall,
        'rendered_fps': measured['rendered_fps'],
        'real_time_factor': measured['real_time_factor'],
        'frame_generation_seconds': raw['frame_generation_seconds'],
        'breakdown': breakdown, 'instrumentation_gap_seconds': overhead,
        'breakdown_semantics': 'Exclusive method self time; alpha helper retained in primitives. Add instrumentation_gap to reconcile frame total.',
        'owners_inclusive': raw['owners_inclusive'], 'methods': raw['methods'],
        'primitive_calls': raw['primitive_calls'], 'scenes': scenes, 'stages_inclusive': stages,
        'bottleneck': max(breakdown, key=lambda k: breakdown[k] or 0),
        'media_validation': {'ffprobe_exit_code': probe.returncode, 'video': video, 'audio': audio},
        'verifier_exit_code': verify.returncode, 'render_status': artifact.status,
        'source_unchanged': hashes == after,
        'plan_source': str(source), 'plan_sha256': hashlib.sha256(plan_bytes).hexdigest(),
        'day13_comparison_vs_day12': comparison,
        'notes': [
            'Same saved six-scene input (plan bytes identical to Day-11/Day-12); no upstream agents or mocks executed; all scene media rendered afresh.',
            'Fresh real System.Speech cache; audio variation is not raster performance.',
            'Stage, owner and method inclusive timings overlap. Never add them to the exclusive breakdown.',
            'Alpha blending cannot be isolated cheaply by per-call wrappers; remains inside rectangle/line/circle times.',
            'Only change under measurement: the off-screen thickness-stamp guard in StickmanRenderer._draw_line.',
            'No progress artifact synthesized. Verifier unchanged.',
        ],
    }
    save(root / 'day13_render_profile.json', report)
    print(json.dumps({k: report[k] for k in ('render_status', 'render_seconds', 'frame_generation_seconds',
                                             'breakdown', 'bottleneck', 'verifier_exit_code',
                                             'day13_comparison_vs_day12')}, indent=2), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())