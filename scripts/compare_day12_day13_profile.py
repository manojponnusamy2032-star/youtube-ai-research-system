"""Side-by-side view of the Day-12 baseline profile and the Day-13 profile."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def rounded(mapping: dict) -> dict:
    return {k: (round(v, 1) if isinstance(v, (int, float)) else v) for k, v in mapping.items()}


def main() -> int:
    day12 = load(ROOT / 'output/day12_profiling/raw_timings.json')
    day13 = load(ROOT / 'output/day13_optimization/day13_render_profile.json')
    excluded = {'alpha_blending'}
    d12_exclusive = {k: v for k, v in day12['profile']['exclusive'].items() if k not in excluded}
    d13_exclusive = {k: v for k, v in day13['breakdown'].items()
                     if k not in excluded and isinstance(v, (int, float))}
    report = {
        'day12': {
            'breakdown_exclusive': rounded(d12_exclusive),
            'frame_generation_seconds': round(day12['profile']['frame_generation_seconds'], 1),
            'instrumentation_gap_seconds': round(day12['profile']['frame_generation_seconds']
                                                 - sum(d12_exclusive.values()), 1),
            'render_seconds': round(day12['render_seconds'], 1),
            'scene_wall_sum_seconds': round(sum(s['render_seconds'] for s in day12['scenes']), 1),
            'frame_count': day12['profile']['frame_count'],
            'scenes': [{'scene': s['scene_id'][-8:], 'render_seconds': round(s['render_seconds'], 1),
                        'frame_generation_seconds': round(s['frame_generation_seconds'], 1),
                        'rendered_fps': round(s['rendered_fps'], 3),
                        'lines': round(s['exclusive'].get('lines', 0.0), 1)} for s in day12['scenes']],
            'stages_inclusive': rounded(day12['stages']),
        },
        'day13': {
            'breakdown_exclusive': rounded(d13_exclusive),
            'frame_generation_seconds': round(day13['frame_generation_seconds'], 1),
            'instrumentation_gap_seconds': round(day13['instrumentation_gap_seconds'], 1),
            'render_seconds': round(day13['render_seconds'], 1),
            'scene_wall_sum_seconds': round(sum(s['render_seconds'] for s in day13['scenes']), 1),
            'frame_count': day13['frame_count'],
            'scenes': [{'scene': s['scene_id'][-8:], 'render_seconds': round(s['render_seconds'], 1),
                        'frame_generation_seconds': round(s['frame_generation_seconds'], 1),
                        'rendered_fps': round(s['rendered_fps'], 3),
                        'lines': round(s['exclusive'].get('lines', 0.0), 1)} for s in day13['scenes']],
            'stages_inclusive': rounded(day13['stages_inclusive']),
        },
    }
    (ROOT / 'output/day13_optimization/profile_comparison.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
