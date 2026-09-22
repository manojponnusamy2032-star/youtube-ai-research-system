"""Day-21 circle equivalence: production `_draw_circle` vs frozen reference.

The frozen pre-Day-21 `_draw_circle` lives in scripts/day21_circle_reference.py
(verbatim copy taken before the Day-21 opaque span fast path). Every
comparison draws the same case into two identical deterministic noise buffers
and compares the raw bytes; no tolerance is applied. Effective write counts
use the `_WriteCounter` convention (one `_blend_pixel` call = 1 write,
`_blit_span` = len(scanline)//3), so the opaque span path must contribute
exactly the same pixel count as the per-pixel reference loop.

Full-scene pairs reuse compare_day13_lines: the Day-20 runs proved the
pre-Day-21 production renderer byte-identical to that frozen line reference
for whole frames, so a whole-frame match here also transitively proves
circle-path equivalence in real rendered scenes.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compare_day13_lines import (  # noqa: E402
    _WriteCounter,
    CountingStickmanRenderer,
    difference,
    noise,
    scene_pair,
    suppressed_character_pair,
)
from scripts.day21_circle_reference import OriginalCircleRenderer  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402


class CountingCircleRenderer(_WriteCounter, OriginalCircleRenderer):
    def __init__(self) -> None:
        super().__init__(False)
        self.writes = 0


def fixed_cases(width: int = 97, height: int = 61) -> list[tuple[str, tuple]]:
    """The Day-21 circle matrix: (label, (cx, cy, radius, color, opacity))."""
    cx, cy = width // 2, height // 2
    cases: list[tuple[str, tuple]] = []
    # Interior circles across radii (small / medium / large).
    for r in (1, 2, 3, 5, 8, 10, 13, 16, 20, 25):
        cases.append((f'interior-r{r}', (cx, cy, r, (200, 10, 10), 1.0)))
    # Tangent from inside each edge.
    cases.extend([
        ('tangent-left', (10, 30, 10, (10, 200, 10), 1.0)),
        ('tangent-right', (width - 11, 30, 10, (10, 10, 200), 1.0)),
        ('tangent-top', (cx, 10, 10, (200, 200, 10), 1.0)),
        ('tangent-bottom', (cx, height - 11, 10, (10, 200, 200), 1.0)),
        ('tangent-tl-inside', (10, 10, 10, (120, 240, 30), 1.0)),
        ('tangent-br-inside', (width - 11, height - 11, 10, (120, 240, 30), 1.0)),
    ])
    # Clipped: center outside the frame on each side plus all four corners.
    cases.extend([
        ('clip-left', (-3, 30, 10, (30, 30, 240), 1.0)),
        ('clip-right', (width + 2, 30, 10, (30, 30, 240), 1.0)),
        ('clip-top', (cx, -3, 10, (240, 30, 30), 1.0)),
        ('clip-bottom', (cx, height + 2, 10, (240, 30, 30), 1.0)),
        ('clip-corner-tl', (-3, -3, 12, (120, 240, 30), 1.0)),
        ('clip-corner-tr', (width + 2, -3, 12, (120, 240, 30), 1.0)),
        ('clip-corner-bl', (-3, height + 2, 12, (120, 240, 30), 1.0)),
        ('clip-corner-br', (width + 2, height + 2, 12, (120, 240, 30), 1.0)),
        ('center-on-left-edge', (0, 30, 10, (250, 120, 0), 1.0)),
        ('center-on-top-edge', (cx, 0, 10, (250, 120, 0), 1.0)),
        ('center-on-right-edge', (width - 1, 30, 10, (250, 120, 0), 1.0)),
        ('center-on-bottom-edge', (cx, height - 1, 10, (250, 120, 0), 1.0)),
        ('far-left-clamps', (-50, 30, 10, (45, 45, 45), 1.0)),
        ('far-above-clamps', (cx, -50, 10, (45, 45, 45), 1.0)),
        ('full-width-span', (cx, cy, 400, (60, 60, 60), 1.0)),
    ])
    # Circles centered in the frame corners.
    cases.extend([
        ('corner-tl', (0, 0, 15, (12, 34, 56), 1.0)),
        ('corner-br', (width - 1, height - 1, 15, (12, 34, 56), 1.0)),
        ('corner-bl', (0, height - 1, 15, (12, 34, 56), 1.0)),
        ('corner-tr', (width - 1, 0, 15, (12, 34, 56), 1.0)),
    ])
    # Different colors.
    for i, color in enumerate([(0, 0, 0), (255, 255, 255), (77, 88, 99),
                               (1, 2, 3), (254, 253, 1)]):
        cases.append((f'color-{i}', (cx, cy, 12, color, 1.0)))
    # Degenerate radii (clamped to 1 by the frozen geometry).
    for r in (0, -3, -100):
        cases.append((f'radius-{r}', (cx, cy, r, (222, 111, 0), 1.0)))
    # Fractional inputs.
    cases.append(('fractional-inside',
                  (cx + 0.9, cy + 0.4, 10.7, (99, 99, 99), 1.0)))
    cases.append(('fractional-clipped',
                  (-2.5, height + 1.5, 9.5, (99, 99, 99), 1.0)))
    # Opaque clamp and the full translucent/zero spectrum.
    for op in (1.5, 0.999, 0.75, 0.5, 0.25, 0.01, 1e-06, 0.0, -0.5):
        cases.append((f'opacity-{op}', (cx, cy, 10, (10, 60, 200), op)))
    for op in (0.5, 0.0):
        cases.append((f'opacity-{op}-clipped', (-3, 30, 10, (10, 60, 200), op)))
    return cases


def single_circle_pair(args: tuple, width: int = 97, height: int = 61,
                       seed: int = 0) -> tuple[bytes, bytes]:
    """One circle drawn onto two identical deterministic noise buffers."""
    initial = noise(width, height, seed)
    frames = [bytearray(initial), bytearray(initial)]
    for renderer, frame in zip((OriginalCircleRenderer(False),
                                StickmanRenderer(False)), frames):
        renderer._draw_circle(frame, width, height, *args)
    return bytes(frames[0]), bytes(frames[1])


def visible_pixels(args: tuple, width: int = 97, height: int = 61) -> int:
    """Predicted visible pixels from the frozen span arithmetic."""
    cx, cy, radius, _color, _opacity = args
    cx, cy, radius = int(cx), int(cy), int(radius)
    cx = max(0, min(cx, width - 1))
    cy = max(0, min(cy, height - 1))
    radius = max(1, radius)
    x_min = max(0, cx - radius)
    x_max = min(width - 1, cx + radius)
    y_min = max(0, cy - radius)
    y_max = min(height - 1, cy + radius)
    r2 = radius * radius
    total = 0
    for y in range(y_min, y_max + 1):
        dy = y - cy
        dx_max = int(math.sqrt(max(0, r2 - dy * dy)))
        total += min(x_max, cx + dx_max) - max(x_min, cx - dx_max) + 1
    return total


def sequence_pair(seed: int, width: int = 97, height: int = 61,
                  draws: int = 150) -> tuple[bytes, bytes]:
    """Random interior/clipped/translucent circle sequences, asserted per draw."""
    initial = noise(width, height, seed)
    frames = [bytearray(initial), bytearray(initial)]
    renderers = [OriginalCircleRenderer(False), StickmanRenderer(False)]
    rng = random.Random(seed + 7000)
    circles = []
    for i in range(draws):
        circles.append((
            rng.randrange(-2 * width, 3 * width),
            rng.randrange(-2 * height, 3 * height),
            rng.choice([-2, 0, 1, 2, 3, 4, 5, 7, 10, 13, 16, 20, 25, 31]),
            tuple(rng.randrange(256) for _ in range(3)),
            [0, 0.01, 0.25, 0.5, 0.75, 0.999, 1, 1.5][i % 8],
        ))
    for args in circles:
        for renderer, frame in zip(renderers, frames):
            renderer._draw_circle(frame, width, height, *args)
        assert frames[0] == frames[1], f'First divergent circle: {args}'
    return bytes(frames[0]), bytes(frames[1])


def overlapping_pair(args: tuple, width: int = 97, height: int = 61,
                     seed: int = 0) -> tuple[bytes, bytes]:
    """Same circle drawn twice onto both buffers (idempotent overwrite)."""
    initial = noise(width, height, seed)
    frames = [bytearray(initial), bytearray(initial)]
    for renderer, frame in zip((OriginalCircleRenderer(False),
                                StickmanRenderer(False)), frames):
        renderer._draw_circle(frame, width, height, *args)
        renderer._draw_circle(frame, width, height, *args)
    return bytes(frames[0]), bytes(frames[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'output/day21_profiling')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    writes = []
    for label, case in fixed_cases():
        baseline, optimized = single_circle_pair(case)
        results.append({'case': label, **difference(baseline, optimized)})
        reference = CountingCircleRenderer()
        production = CountingStickmanRenderer()
        initial = noise(97, 61, 4321)
        reference._draw_circle(bytearray(initial), 97, 61, *case)
        production._draw_circle(bytearray(initial), 97, 61, *case)
        expected = visible_pixels(case)
        assert reference.writes == expected, \
            (label, 'reference writes', reference.writes, expected)
        assert production.writes == expected, \
            (label, 'production writes', production.writes, expected)
        writes.append({'case': label, 'reference_writes': reference.writes,
                       'production_writes': production.writes,
                       'visible_pixels': expected})
    for seed in range(20):
        results.append({'case': f'circle-sequence-{seed}',
                        **difference(*sequence_pair(seed))})
    for i in range(9):
        results.append({'case': f'full-frame-{i}',
                        **difference(*scene_pair(i))})
    for i in range(3):
        results.append({'case': f'suppressed-character-frame-{i}',
                        **difference(*suppressed_character_pair(i))})
    for i in range(3):
        pair = scene_pair(i, 1920, 1080)
        results.append({'case': f'1080p-frame-{i}', **difference(*pair)})
    results.append({'case': 'overlapping-double-draw-r20',
                    **difference(*overlapping_pair((48, 30, 20, (200, 10, 10),
                                                    1.0)))})
    results.append({'case': 'overlapping-double-draw-huge',
                    **difference(*overlapping_pair((48, 30, 400, (60, 60, 60),
                                                    1.0)))})

    report = {
        'comparison_count': len(results),
        'different_pixels': sum(r['different_pixels'] for r in results),
        'maximum_channel_difference': max(r['maximum_channel_difference']
                                          for r in results),
        'byte_identical_cases':
            sum(1 for r in results
                if r['baseline_sha256'] == r['optimized_sha256']),
        'cases': results,
        'write_identity': writes,
        'probe_cross_check': {
            'r1_visible': visible_pixels((48, 30, 1, (0, 0, 0), 1.0)),
            'r10_visible': visible_pixels((48, 30, 10, (0, 0, 0), 1.0)),
            'r20_visible': visible_pixels((48, 30, 20, (0, 0, 0), 1.0)),
            'expected': {'r1': 5, 'r10': 317, 'r20': 1257},
        },
        'notes': ['Frozen pre-Day-21 `_draw_circle` compared byte-for-byte '
                  'with the production renderer.',
                  'No tolerance applied: any differing pixel count or channel '
                  'value fails.',
                  'Effective writes assert reference == production == '
                  'predicted visible pixels for every fixed case.',
                  'Full-scene baselines use the frozen pre-Day-13 line '
                  'renderer, which Day-20 proved byte-identical to the '
                  'pre-Day-21 production frames (transitive evidence).'],
    }
    (args.output_dir / 'pixel_equivalence.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ('cases', 'write_identity')}, indent=2))
    return int(report['different_pixels'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())

