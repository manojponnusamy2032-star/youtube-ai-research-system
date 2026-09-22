"""Deterministic RGB comparisons; no encoder or production artifact synthesis."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.day11_rectangle_reference import OriginalRectangleRenderer
from src.services.stickman_renderer import StickmanRenderer


def difference(a: bytes, b: bytes) -> dict:
    if len(a) != len(b):
        raise AssertionError('Frame buffer length changed')
    count = sum(a[i:i + 3] != b[i:i + 3] for i in range(0, len(a), 3))
    return {'different_pixels': count,
            'maximum_channel_difference': max((abs(x - y) for x, y in zip(a, b)), default=0),
            'baseline_sha256': hashlib.sha256(a).hexdigest(),
            'optimized_sha256': hashlib.sha256(b).hexdigest()}


def rectangle_pair(seed: int) -> tuple[bytes, bytes]:
    rng = random.Random(seed)
    w, h = 97, 61
    initial = bytes(rng.randrange(256) for _ in range(w * h * 3))
    frames = [bytearray(initial), bytearray(initial)]
    renderers = [OriginalRectangleRenderer(), StickmanRenderer()]
    # Static, overlapping, boundary, empty, outside, moving, and fractional inputs.
    rectangles = [(0, 0, w, h, (13, 54, 231), 1),
                  (-10, -8, 23, 19, (255, 0, 0), 1),
                  (w - 1, h - 1, 10, 12, (0, 255, 0), 1),
                  (w + 10, h + 10, 9, 9, (0, 0, 255), 1),
                  (2, 2, 0, 8, (1, 2, 3), 1),
                  (5, 7, -4, 5, (1, 2, 3), 1),
                  (1.9, 2.8, 8.7, 9.2, (120, 30, 255), 1)]
    for i in range(40):
        rectangles.append((rng.randrange(-w, 2*w), rng.randrange(-h, 2*h),
                           rng.randrange(-3, w), rng.randrange(-3, h),
                           tuple(rng.randrange(256) for _ in range(3)),
                           [-1, 0, 0.01, 0.25, 0.55, 0.999, 1, 2][i % 8]))
    for rect in rectangles:
        for renderer, frame in zip(renderers, frames):
            renderer._draw_rect(frame, w, h, *rect)
        assert frames[0] == frames[1], f'First divergent rectangle: {rect}'
        assert len(frames[1]) == len(initial)
    return bytes(frames[0]), bytes(frames[1])


def scene_pair(index: int, width: int = 320, height: int = 180) -> tuple[bytes, bytes]:
    t = index / 3
    state = {
        'environment': {'type': ['default', 'classroom', 'bedroom'][index % 3]},
        'camera_zoom': 1 + index * 0.02, 'camera_pan_x': index * 2,
        'object_layers': {'moving': {'x': 25 + index * 10, 'y': 40,
                                    'scale': 1 + index * 0.1, 'opacity': 0.55}},
        'typed_objects': {name: {'type': name, 'x': width * (0.2 + n * 0.12),
                                'y': height * 0.6, 'opacity': 1 if n % 2 else 0.55}
                          for n, name in enumerate(['book', 'desk', 'chair', 'graph', 'laptop'])},
        'text_specs': [{'text': 'Rectangle equivalence', 'x': 0.5, 'y': 0.9}],
    }
    frames = []
    for renderer in (OriginalRectangleRenderer(), StickmanRenderer()):
        local = copy.deepcopy(state)
        pose = renderer._compute_pose('walk', t, 4, width, height, motion_state=local)
        frames.append(renderer._generate_frame(width, height, t, 4, index, 120,
                                               pose, job={}, motion_state=local))
    return tuple(frames)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'output/day11_optimization')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for seed in range(20):
        results.append({'case': f'rectangles-{seed}', **difference(*rectangle_pair(seed))})
    for i in range(9):
        results.append({'case': f'full-frame-{i}', **difference(*scene_pair(i))})
    for i in range(3):
        pair = scene_pair(i, 1920, 1080)
        results.append({'case': f'1080p-frame-{i}', **difference(*pair)})
        from PIL import Image
        for label, data in zip(('baseline', 'optimized'), pair):
            Image.frombytes('RGB', (1920, 1080), data).save(args.output_dir / f'{label}-{i}.png')
    report = {'comparison_frames': len(results),
              'different_pixels': sum(r['different_pixels'] for r in results),
              'maximum_channel_difference': max(r['maximum_channel_difference'] for r in results),
              'cases': results}
    (args.output_dir / 'pixel_equivalence.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}))
    return int(report['different_pixels'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
