"""Summarize saved Day-13 measurements without synthesizing producer artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output/day13_optimization'


def load(name):
    return json.loads((OUT / name).read_text(encoding='utf-8-sig'))


def main():
    p = load('day13_render_profile.json')
    e = load('pixel_equivalence.json')
    media = load('final_ffprobe.json')
    verifier = load('jobs/job_001/day8_verification.json')
    assert '12 failed, 1968 passed, 32 warnings' in (OUT / 'full_suite.log').read_text(encoding='utf-8-sig')
    assert '49 passed' in (OUT / 'final_focused_tests.log').read_text(encoding='utf-8')
    assert e['different_pixels'] == e['maximum_channel_difference'] == 0
    assert all(hashlib.sha256(Path(f).read_bytes()).hexdigest() == h
               for f, h in load('source_hashes_after.json').items())
    baseline = dict(line_drawing_seconds=255.412, frame_generation_seconds=364.609,
                    render_seconds=393.004, rendered_fps=4.578, real_time_factor=6.554)
    optimized = {k: p[k] for k in baseline if k != 'line_drawing_seconds'}
    optimized['line_drawing_seconds'] = p['breakdown']['lines']
    changes = {k: {'absolute_change': optimized[k] - v,
                   'percent_change': 100 * (optimized[k] - v) / v}
               for k, v in baseline.items()}
    result = {
        'status': 'incomplete', 'definition_of_done_met': False,
        'baseline': baseline, 'optimized': optimized, 'comparison': changes,
        'pixel_equivalence': {'different_pixels': e['different_pixels'],
                              'max_channel_difference': e['maximum_channel_difference'],
                              'comparison_count': e['comparison_count']},
        'tests': {'total': 1980, 'passed': 1968, 'failed': 12, 'warnings': 32,
                  'full_suite_log': str(OUT / 'full_suite.log'),
                  'final_focused': {'total': 49, 'passed': 49, 'failed': 0,
                                    'warnings': 0, 'day13_tests': 20, 'day11_tests': 29}},
        'media': media, 'verifier': verifier,
        'mp4_sha256': hashlib.sha256((OUT / 'jobs/job_001/video.mp4').read_bytes()).hexdigest(),
        'notes': [
            'Full suite fails: run_pipeline.py is absent. Unrelated publishing code was not created.',
            'Benchmark completed despite failed full-suite prerequisite; strict definition of done is not met.',
            'Verifier fails solely for missing render_progress.json. No progress artifact was fabricated.',
            'Current profile, scene measurements, stdout and source hashes agree. Stale profile_comparison.json is not authoritative.',
            'Single measured benchmark, not a controlled causal estimate. Non-line times also vary from Day 12.',
            'No further renderer optimization performed.'
        ]}
    (OUT / 'day13_optimization_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'optimized': optimized, 'comparison': changes}, indent=2))


if __name__ == '__main__':
    main()
