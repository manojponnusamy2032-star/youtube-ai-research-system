"""Day-16 focused tests: opaque thick-stamp fast path in `_draw_line`.

Compares production `_draw_line` against the frozen pre-Day-13 reference
byte-for-byte (no tolerance). The reference contains no stamp guard and no
fast path, so any semantic change in the production fast path fails here.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compare_day13_lines import difference, noise  # noqa: E402
from scripts.day13_line_reference import OriginalLineRenderer  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

WIDTH = 97
HEIGHT = 61


def assert_identical(line: tuple, label: str = '') -> None:
    initial = noise(WIDTH, HEIGHT, 5)
    frames = []
    for renderer in (OriginalLineRenderer(False), StickmanRenderer(False)):
        frame = bytearray(initial)
        renderer._draw_line(frame, WIDTH, HEIGHT, *line)
        frames.append(bytes(frame))
    result = difference(*frames)
    assert result['different_pixels'] == 0, f'{label}: {result}'
    assert result['maximum_channel_difference'] == 0, f'{label}: {result}'


def test_day16_thin_opaque_line() -> None:
    assert_identical((5, 5, 90, 50, (200, 10, 10), 1, 1.0), 'thin-opaque')


def test_day16_thick_horizontal_line() -> None:
    assert_identical((2, 30, 94, 30, (0, 200, 0), 9, 1.0), 'thick-horizontal')


def test_day16_thick_vertical_line() -> None:
    assert_identical((48, 2, 48, 58, (0, 0, 200), 7, 1.0), 'thick-vertical')


def test_day16_thick_diagonal_line() -> None:
    assert_identical((0, 0, 96, 60, (255, 0, 0), 5, 1.0), 'thick-diagonal')


def test_day16_shallow_diagonal() -> None:
    assert_identical((0, 30, 96, 38, (10, 20, 30), 9, 1.0), 'shallow-diagonal')


def test_day16_steep_diagonal() -> None:
    assert_identical((30, 0, 38, 60, (40, 50, 60), 9, 1.0), 'steep-diagonal')


def test_day16_crosses_left_boundary() -> None:
    assert_identical((-30, 10, 50, 40, (70, 80, 90), 9, 1.0), 'cross-left')


def test_day16_crosses_right_boundary() -> None:
    assert_identical((60, 10, 200, 40, (11, 22, 33), 9, 1.0), 'cross-right')


def test_day16_crosses_top_boundary() -> None:
    assert_identical((10, -30, 60, 40, (44, 55, 66), 7, 1.0), 'cross-top')


def test_day16_crosses_bottom_boundary() -> None:
    assert_identical((10, 30, 60, 200, (77, 88, 99), 7, 1.0), 'cross-bottom')


def test_day16_stamp_touching_boundary() -> None:
    # Stamp exactly touches the frame edge (clipped span of width 1).
    assert_identical((0, 30, 96, 30, (1, 2, 3), 3, 1.0), 'touch-boundary')
    assert_identical((-1, 30, 50, 30, (4, 5, 6), 3, 1.0), 'touch-left-outside')


def test_day16_endpoints_outside_crossing_frame() -> None:
    assert_identical((-100, -50, 200, 120, (9, 9, 9), 5, 1.0), 'outside-crossing')


def test_day16_very_thick_stamp() -> None:
    assert_identical((20, 20, 70, 45, (123, 45, 67), 25, 1.0), 'very-thick')
    assert_identical((48, 30, 48, 30, (200, 200, 200), 31, 1.0), 'very-thick-point')


def test_day16_multiple_consecutive_stamps() -> None:
    lines = [
        (0, 0, 96, 60, (255, 0, 0), 5, 1.0),
        (0, 60, 96, 0, (0, 255, 0), 9, 1.0),
        (48, 0, 48, 60, (0, 0, 255), 3, 1.0),
        (-20, 30, 120, 30, (9, 9, 9), 11, 1.0),
    ]
    initial = noise(WIDTH, HEIGHT, 9)
    frames = []
    for renderer in (OriginalLineRenderer(False), StickmanRenderer(False)):
        frame = bytearray(initial)
        for line in lines:
            renderer._draw_line(frame, WIDTH, HEIGHT, *line)
        frames.append(bytes(frame))
    result = difference(*frames)
    assert result['different_pixels'] == 0, result
    assert result['maximum_channel_difference'] == 0, result


def test_day16_opaque_vs_reference_exhaustive() -> None:
    colors = [(255, 0, 0), (0, 0, 0), (255, 255, 255)]
    thicknesses = [1, 2, 3, 5, 9, 13]
    endpoints = [
        (0, 0, 96, 60), (0, 60, 96, 0), (0, 30, 96, 30),
        (48, 0, 48, 60), (-40, -20, 140, 90), (10, 10, 12, 12),
    ]
    count = 0
    for color in colors:
        for thickness in thicknesses:
            for x0, y0, x1, y1 in endpoints:
                assert_identical(
                    (x0, y0, x1, y1, color, thickness, 1.0),
                    f'exhaustive-{color}-{thickness}-{(x0, y0, x1, y1)}',
                )
                count += 1
    assert count == len(colors) * len(thicknesses) * len(endpoints)
