"""Day-20 focused tests: interior opaque stamp fast path in `_draw_line`.

Pixel equivalence reference: the frozen pre-Day-13 renderer in
scripts/day13_line_reference.py. The pre-Day-20 implementation already matched
that reference byte-for-byte (output/day20_profiling/pre_edit_equivalence/
pixel_equivalence.json: 123 comparisons, 0 differing pixels), so proving the
Day-20 optimized renderer identical to the reference proves identity with the
pre-Day-20 implementation as well.

Work assertions: fully interior opaque stamps must skip the per-row candidate
scan (zero `px, py =` evaluations); stamps that can touch or cross a frame
edge must keep the clipping-safe scan; non-opaque stamps must keep the
per-candidate blending path.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compare_day13_lines import (  # noqa: E402
    candidate_events,
    difference,
    noise,
    write_counts,
)
from scripts.day13_line_reference import OriginalLineRenderer  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

WIDTH = 97
HEIGHT = 61

# (label, (x0, y0, x1, y1, color, thickness, opacity)) — all fully interior.
INTERIOR_CASES = [
    ('thin-horizontal', (10, 30, 80, 30, (10, 200, 30), 1, 1.0)),
    ('thick-horizontal', (10, 30, 80, 30, (10, 200, 30), 13, 1.0)),
    ('even-thickness-12', (10, 30, 80, 30, (10, 200, 30), 12, 1.0)),
    ('medium-horizontal-5', (10, 30, 80, 30, (10, 200, 30), 5, 1.0)),
    ('thin-vertical', (20, 10, 20, 50, (30, 10, 200), 1, 1.0)),
    ('thick-vertical-11', (20, 10, 20, 50, (30, 10, 200), 11, 1.0)),
    ('diagonal-down', (10, 10, 80, 50, (200, 10, 10), 9, 1.0)),
    ('diagonal-up', (80, 10, 10, 50, (200, 10, 10), 9, 1.0)),
    ('diagonal-reversed-endpoints', (10, 50, 80, 10, (200, 10, 10), 7, 1.0)),
    ('shallow-3-in-70', (10, 30, 80, 33, (90, 90, 90), 5, 1.0)),
    ('steep-40-in-3', (40, 10, 43, 50, (90, 90, 90), 5, 1.0)),
    ('zero-length-point', (30, 30, 30, 30, (222, 111, 0), 7, 1.0)),
    ('tangent-inside-left', (1, 20, 1, 45, (45, 45, 45), 1, 1.0)),
    ('tangent-inside-top', (2, 8, 90, 8, (5, 5, 5), 3, 1.0)),
    ('fractional-endpoints', (10.9, 20.7, 60.2, 55.9, (77, 88, 99), 3, 1.0)),
]
# Stamps that touch or cross a frame edge: the clipping-safe scan must run.
CLIPPED_CASES = [
    ('cross-left', (-5, 30, 40, 30, (30, 30, 240), 9, 1.0)),
    ('cross-right', (60, 30, WIDTH + 5, 30, (30, 30, 240), 9, 1.0)),
    ('cross-right-thick-13', (WIDTH - 4, 30, WIDTH + 8, 30, (30, 30, 240), 13, 1.0)),
    ('cross-top', (30, -5, 60, 30, (240, 30, 30), 9, 1.0)),
    ('cross-bottom', (30, 40, 60, HEIGHT + 5, (240, 30, 30), 9, 1.0)),
    ('corner-tl', (-3, -3, 60, 60, (120, 240, 30), 7, 1.0)),
    ('corner-br', (WIDTH + 3, HEIGHT + 3, 20, 10, (120, 240, 30), 7, 1.0)),
    ('corner-bl', (-3, HEIGHT + 3, 60, 5, (120, 240, 30), 7, 1.0)),
    ('corner-tr', (WIDTH + 3, -3, 20, 55, (120, 240, 30), 7, 1.0)),
    ('tangent-outside-left', (-1, 20, -1, 45, (45, 45, 45), 3, 1.0)),
    ('tangent-inside-left-t1', (0, 20, 0, 45, (45, 45, 45), 1, 1.0)),
    ('tangent-even-top', (20, 0, 60, 0, (45, 45, 45), 2, 1.0)),
    ('tangent-bottom-thick', (20, HEIGHT - 1, 60, HEIGHT - 1, (45, 45, 45), 5, 1.0)),
]

# Interior translucent lines: blending path must remain per-candidate.
NON_OPAQUE_CASES = [
    ('translucent-diagonal', (10, 10, 80, 50, (200, 10, 10), 9, 0.5)),
    ('translucent-horizontal', (10, 30, 80, 30, (90, 90, 90), 13, 0.25)),
]


def is_interior_line(line: tuple, width: int = WIDTH, height: int = HEIGHT) -> bool:
    """Mirror the production Day-20 interior condition for a line tuple."""
    x0, y0, x1, y1 = (int(v) for v in line[:4])
    thickness = line[5]
    low, high = -thickness // 2, thickness // 2
    return (min(x0, x1) + low >= 0 and max(x0, x1) + high < width
            and min(y0, y1) + low >= 0 and max(y0, y1) + high < height)


def assert_pixel_identical(line: tuple, label: str) -> dict:
    """Draw one line with reference and production renderers; require equality."""
    initial = noise(WIDTH, HEIGHT, 5)
    frames = []
    for renderer in (OriginalLineRenderer(False), StickmanRenderer(False)):
        frame = bytearray(initial)
        renderer._draw_line(frame, WIDTH, HEIGHT, *line)
        frames.append(bytes(frame))
    result = difference(*frames)
    assert result['different_pixels'] == 0, f'{label}: {result}'
    assert result['maximum_channel_difference'] == 0, f'{label}: {result}'
    assert result['baseline_sha256'] == result['optimized_sha256'], f'{label}: hash mismatch'
    return result


def _events(renderer_cls, line: tuple, seed: int) -> int:
    return candidate_events(renderer_cls(False), bytearray(noise(WIDTH, HEIGHT, seed)),
                            (WIDTH, HEIGHT, *line))



def test_interior_opaque_stamps_skip_scan_and_stay_identical() -> None:
    for label, line in INTERIOR_CASES:
        assert is_interior_line(line), f'{label}: misclassified as interior'
        assert_pixel_identical(line, label)
        baseline_writes, optimized_writes = write_counts(line)
        assert baseline_writes == optimized_writes, f'{label}: pixel writes changed'
        assert optimized_writes > 0, f'{label}: expected visible writes'
        baseline_events = _events(OriginalLineRenderer, line, 7)
        optimized_events = _events(StickmanRenderer, line, 7)
        assert baseline_events > 0, f'{label}: baseline scan missing'
        assert optimized_events == 0, f'{label}: scan not bypassed ({optimized_events})'


def test_clipped_stamps_keep_candidate_scan_and_stay_identical() -> None:
    for label, line in CLIPPED_CASES:
        assert not is_interior_line(line), f'{label}: misclassified as interior'
        assert_pixel_identical(line, label)
        baseline_writes, optimized_writes = write_counts(line)
        assert baseline_writes == optimized_writes, f'{label}: pixel writes changed'
        assert optimized_writes > 0, f'{label}: expected visible writes'
        if line[6] >= 1.0:
            assert _events(StickmanRenderer, line, 7) > 0, f'{label}: scan removed'
        baseline_events = _events(OriginalLineRenderer, line, 7)
        optimized_events = _events(StickmanRenderer, line, 7)
        assert optimized_events <= baseline_events, f'{label}: events grew'


def test_non_opaque_interior_stamps_keep_blending() -> None:
    for label, line in NON_OPAQUE_CASES:
        assert is_interior_line(line), f'{label}: misclassified as interior'
        assert_pixel_identical(line, label)
        baseline_writes, optimized_writes = write_counts(line)
        assert baseline_writes == optimized_writes, f'{label}: pixel writes changed'
        baseline_events = _events(OriginalLineRenderer, line, 7)
        optimized_events = _events(StickmanRenderer, line, 7)
        assert baseline_events > 0, f'{label}: baseline candidates missing'
        assert optimized_events == baseline_events, f'{label}: blending path changed'


def test_interior_condition_is_conservative_at_boundaries() -> None:
    """Stamps tangent from inside may use the fast path; from outside must not."""
    inside = (1, 20, 1, 45, (45, 45, 45), 1, 1.0)
    assert is_interior_line(inside)
    assert _events(StickmanRenderer, inside, 7) == 0
    assert_pixel_identical(inside, 'inside-tangent')

    for label, line in (('left-from-outside', (-1, 20, -1, 45, (45, 45, 45), 3, 1.0)),
                        ('top-even-thickness', (20, 0, 60, 0, (45, 45, 45), 2, 1.0)),
                        ('right-at-boundary', (WIDTH - 1, 20, WIDTH - 1, 45, (45, 45, 45), 3, 1.0)),
                        ('bottom-at-boundary', (20, HEIGHT - 1, 60, HEIGHT - 1, (45, 45, 45), 3, 1.0))):
        assert not is_interior_line(line), f'{label}: must not be interior'
        assert_pixel_identical(line, label)
        assert _events(StickmanRenderer, line, 7) > 0, f'{label}: scan removed'


def _bresenham_point_count(x0: int, y0: int, x1: int, y1: int) -> int:
    """Replicate the renderer's Bresenham walk to count stamped points."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    points = 0
    x, y = x0, y0
    while True:
        points += 1
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return points


def test_interior_even_and_odd_thickness_write_identity() -> None:
    for thickness in (12, 13):
        line = (10, 25, 80, 40, (60, 120, 180), thickness, 1.0)
        assert is_interior_line(line)
        assert_pixel_identical(line, f'parity-{thickness}')
        baseline_writes, optimized_writes = write_counts(line)
        assert baseline_writes == optimized_writes, f'parity-{thickness}: writes changed'
        # Interior fast path writes exactly the full (low..high) stamp square
        # once per Bresenham point — identical to the scanned path's total.
        # Production bounds: low = -thickness // 2, high = thickness // 2
        # (floor division, so odd thicknesses give high - low + 1 = t + 1).
        stamp_side = (thickness // 2) - (-thickness // 2) + 1
        points = _bresenham_point_count(line[0], line[1], line[2], line[3])
        expected = points * stamp_side * stamp_side
        assert optimized_writes == expected, (thickness, optimized_writes, expected)

