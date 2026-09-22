"""Controlled same-process A/B timing for the Day-13 off-screen line guard.

The 1080p30 end-to-end benchmark necessarily includes machine noise between
days. This harness removes that variable: the frozen pre-Day-13 renderer and the
optimized renderer draw the *same* real scene frames in the *same* process, on
the same machine state, alternated per repetition, and every frame is also
checked for byte equality. It isolates the cost of the change itself.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.compare_day13_lines import (  # noqa: E402
    OriginalLineRenderer,
    difference,
    scene_state,
)
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
FRAMES_PER_SCENE = 4
REPETITIONS = 2


def render_sequence(renderer, index: int, suppressed: bool) -> bytes:
    """Render deterministic frames for one scene state and return the last frame."""
    data = b''
    for frame_index in range(FRAMES_PER_SCENE):
        t = frame_index / FRAMES_PER_SCENE
        state = copy.deepcopy(scene_state(index, WIDTH, HEIGHT, suppress=suppressed))
        pose = renderer._compute_pose('walk', t, 4, WIDTH, HEIGHT, motion_state=state)
        if suppressed:
            pose.stickman_x = -10000
            pose.stickman_y = -10000
        data = renderer._generate_frame(WIDTH, HEIGHT, t, 4, frame_index, FRAMES_PER_SCENE,
                                        pose, job={}, motion_state=state)
    return data


def time_sequence(renderer, index: int, suppressed: bool) -> tuple[float, bytes]:
    start = time.perf_counter()
    data = render_sequence(renderer, index, suppressed)
    return time.perf_counter() - start, data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/day13_optimization/ab_timing.json')
    args = parser.parse_args()
    baseline = OriginalLineRenderer(False)
    optimized = StickmanRenderer(False)
    layout = [(0, False), (2, False), (4, False), (1, True), (3, True), (5, True)]
    # Warm both implementations on an unrelated scene so first-call costs do not skew.
    time_sequence(baseline, 0, False)
    time_sequence(optimized, 0, False)
    scenes = []
    all_baseline = 0.0
    all_optimized = 0.0
    pixels_different = 0
    for index, suppressed in layout:
        best = {'baseline': float('inf'), 'optimized': float('inf')}
        last: dict[str, bytes] = {}
        for rep in range(REPETITIONS):
            order = [('baseline', baseline), ('optimized', optimized)]
            if rep % 2:
                order = order[::-1]
            for name, renderer in order:
                seconds, data = time_sequence(renderer, index, suppressed)
                best[name] = min(best[name], seconds)
                last[name] = data
        diff = difference(last['baseline'], last['optimized'])
        assert diff['different_pixels'] == 0, (index, suppressed, diff)
        pixels_different += diff['different_pixels']
        all_baseline += best['baseline']
        all_optimized += best['optimized']
        scenes.append({
            'scene_index': index, 'suppressed_primary_character': suppressed,
            'frames': FRAMES_PER_SCENE, 'repetitions': REPETITIONS,
            'baseline_seconds': best['baseline'], 'optimized_seconds': best['optimized'],
            'speedup': best['baseline'] / best['optimized'],
            'percent_faster': (1 - best['optimized'] / best['baseline']) * 100.0,
            'baseline_seconds_per_frame': best['baseline'] / FRAMES_PER_SCENE,
            'optimized_seconds_per_frame': best['optimized'] / FRAMES_PER_SCENE,
            'different_pixels': diff['different_pixels'],
            'maximum_channel_difference': diff['maximum_channel_difference'],
        })
    report = {
        'resolution': f'{WIDTH}x{HEIGHT}', 'frames_per_scene': FRAMES_PER_SCENE,
        'repetitions': REPETITIONS, 'interleaved': True,
        'totals': {
            'baseline_seconds': all_baseline, 'optimized_seconds': all_optimized,
            'seconds_saved': all_baseline - all_optimized,
            'speedup': all_baseline / all_optimized,
            'percent_faster': (1 - all_optimized / all_baseline) * 100.0,
        },
        'different_pixels': pixels_different,
        'scenes': scenes,
        'notes': [
            'Both implementations ran in one process, alternating per repetition, so machine drift affects both equally.',
            'Baseline is the frozen pre-Day-13 `_draw_line` (scripts/day13_line_reference.py); everything else is production code.',
            'Frames are real scene states at 1920x1080, including the Day-12 amplifier (primary character pushed off-screen).',
            'Byte equality was verified for every scene pair; no tolerance was applied.',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'totals': report['totals'], 'different_pixels': pixels_different}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
