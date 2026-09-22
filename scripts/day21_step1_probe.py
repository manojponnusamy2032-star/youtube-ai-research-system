"""Day-21 Step-1 probe: measure `_draw_circle` write behavior (read-only).

Patches `_blend_pixel` at instance level (same mechanism as
`compare_day13_lines._WriteCounter`) to count invocations vs. effective buffer
writes for representative circles. No production code is modified.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compare_day13_lines import noise  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

W, H = 97, 61


def run_case(label, cx, cy, radius, opacity, color=(200, 10, 10), draw_twice=False):
    renderer = StickmanRenderer(False)
    stats = {'calls': 0, 'writes': 0, 'idx': set(), 'dup': 0}
    original = renderer._blend_pixel

    def counting(frame, idx, px_color, px_opacity, _orig=original):
        alpha = int(round(px_opacity * 255.0))
        stats['calls'] += 1
        if alpha > 0:
            if idx in stats['idx']:
                stats['dup'] += 1
            stats['idx'].add(idx)
            stats['writes'] += 1
        _orig(frame, idx, px_color, px_opacity)

    renderer._blend_pixel = counting
    frame = bytearray(noise(W, H, 4))
    renderer._draw_circle(frame, W, H, cx, cy, radius, color, opacity)
    if draw_twice:
        renderer._draw_circle(frame, W, H, cx, cy, radius, color, opacity)
    visible = (stats['calls'] == stats['writes'])
    print(f'{label:<34} calls={stats["calls"]:<6} writes={stats["writes"]:<6} '
          f'dup_idx={stats["dup"]:<4} calls==writes:{visible}')
    return stats


print('== opaque circles ==')
run_case('interior r=10 (48,30)', 48, 30, 10, 1.0)
run_case('interior small r=1 (48,30)', 48, 30, 1, 1.0)
run_case('interior large r=20 (48,30)', 48, 30, 20, 1.0)
run_case('interior r=20 drawn twice', 48, 30, 20, 1.0, draw_twice=True)
print('== tangent / boundary (opaque) ==')
run_case('tangent-left cx=10 r=10', 10, 30, 10, 1.0)
run_case('tangent-right cx=86 r=10', 86, 30, 10, 1.0)
run_case('tangent-top cy=10 r=10', 48, 10, 10, 1.0)
run_case('tangent-bottom cy=50 r=10', 48, 50, 10, 1.0)
print('== clipped (opaque) ==')
run_case('clip-left cx=-3 r=10', -3, 30, 10, 1.0)
run_case('clip-right cx=99 r=10', 99, 30, 10, 1.0)
run_case('clip-top cy=-3 r=10', 48, -3, 10, 1.0)
run_case('clip-bottom cy=63 r=10', 48, 63, 10, 1.0)
run_case('clip-corner br cx=99 cy=63', 99, 63, 12, 1.0)
print('== invisible ==')
run_case('fully invisible cx=-50 r=10', -50, 30, 10, 1.0)
print('== non-opaque ==')
run_case('opacity 0.5 interior r=10', 48, 30, 10, 0.5)
run_case('opacity 0.0 interior r=10', 48, 30, 10, 0.0)
run_case('opacity 0.5 clipped cx=-3', -3, 30, 10, 0.5)
