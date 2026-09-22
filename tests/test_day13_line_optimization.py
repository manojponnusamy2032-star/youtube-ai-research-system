"""Day-13 focused tests: off-screen line thickness-stamp guard.

Every test compares the production `_draw_line` against the frozen pre-Day-13
implementation in scripts/day13_line_reference.py byte-for-byte (no tolerance).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compare_day13_lines import (  # noqa: E402
    CountingLineRenderer,
    CountingStickmanRenderer,
    candidate_events,
    difference,
    fixed_cases,
    noise,
    scene_pair,
    sequence_pair,
    suppressed_character_pair,
    write_counts,
)
from scripts.day13_line_reference import OriginalLineRenderer  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

WIDTH = 97
HEIGHT = 61


def assert_identical(line: tuple, label: str = '') -> None:
    """Draw one line twice and require byte-identical buffers and write counts."""
    baseline_writes, optimized_writes = write_counts(line)
    assert baseline_writes == optimized_writes, f'{label}: pixel writes changed'
    frames = []
    initial = noise(WIDTH, HEIGHT, 5)
    for renderer in (OriginalLineRenderer(False), StickmanRenderer(False)):
        frame = bytearray(initial)
        renderer._draw_line(frame, WIDTH, HEIGHT, *line)
        frames.append(bytes(frame))
    result = difference(*frames)
    assert result['different_pixels'] == 0, f'{label}: {result}'
    assert result['maximum_channel_difference'] == 0, f'{label}: {result}'
    assert result['baseline_sha256'] == result['optimized_sha256'], f'{label}: hash mismatch'


def assert_writes(line: tuple, expected_min: int) -> int:
    """Require equal write counts and at least `expected_min` real pixel writes."""
    baseline_writes, optimized_writes = write_counts(line)
    assert baseline_writes == optimized_writes, 'pixel writes changed'
    if expected_min == 0:
        assert optimized_writes == 0, 'expected no visible writes'
    else:
        assert optimized_writes >= expected_min, f'expected >= {expected_min} writes'
    return optimized_writes


def test_case_01_completely_offscreen_left() -> None:
    for line in ((-400, 10, -200, 40, (200, 10, 10), 3, 1.0),
                 (-1400, -20, -200, 90, (10, 200, 10), 13, 0.5),
                 (-400, 80, -400, 80, (1, 2, 3), 9, 1.0)):
        assert_writes(line, 0)
        assert_identical(line, 'case-1')


def test_case_02_completely_offscreen_right() -> None:
    for line in ((WIDTH + 20, 10, WIDTH * 3, 40, (200, 10, 10), 1, 1.0),
                 (WIDTH + 20, -5, WIDTH * 3, HEIGHT + 9, (10, 10, 200), 21, 0.75),
                 (WIDTH + 30, 4, WIDTH + 30, 4, (7, 7, 7), 17, 1.0)):
        assert_writes(line, 0)
        assert_identical(line, 'case-2')


def test_case_03_completely_above_frame() -> None:
    for line in ((10, -400, 60, -120, (200, 200, 10), 5, 1.0),
                 (-30, -400, WIDTH + 30, -100, (0, 0, 0), 12, 0.25)):
        assert_writes(line, 0)
        assert_identical(line, 'case-3')


def test_case_04_completely_below_frame() -> None:
    for line in ((10, HEIGHT + 10, 60, HEIGHT * 3, (10, 200, 200), 5, 1.0),
                 (-30, HEIGHT + 4, WIDTH + 30, HEIGHT * 2, (255, 255, 255), 7, 0.6)):
        assert_writes(line, 0)
        assert_identical(line, 'case-4')


def test_case_05_thick_line_just_outside_frame() -> None:
    # thickness 9 => stamp spans -5..+4, so a center at width+5 stays invisible
    # while a center at width+4 still touches the last pixel column.
    assert_identical((WIDTH + 4, 20, WIDTH + 4, 40, (250, 120, 0), 9, 1.0), 'case-5-right-touch')
    assert_writes((WIDTH + 4, 20, WIDTH + 4, 40, (250, 120, 0), 9, 1.0), 1)
    assert_writes((WIDTH + 5, 20, WIDTH + 5, 40, (250, 120, 0), 9, 1.0), 0)
    assert_identical((-4, 20, -4, 40, (250, 120, 0), 9, 1.0), 'case-5-left-touch')
    assert_writes((-4, 20, -4, 40, (250, 120, 0), 9, 1.0), 1)
    assert_writes((-5, 20, -5, 40, (250, 120, 0), 9, 1.0), 0)
    assert_identical((20, -4, 40, -4, (0, 250, 120), 9, 1.0), 'case-5-top-touch')
    assert_writes((20, -4, 40, -4, (0, 250, 120), 9, 1.0), 1)
    assert_writes((20, -5, 40, -5, (0, 250, 120), 9, 1.0), 0)
    assert_identical((20, HEIGHT + 4, 40, HEIGHT + 4, (0, 250, 120), 9, 1.0), 'case-5-bottom-touch')
    assert_writes((20, HEIGHT + 4, 40, HEIGHT + 4, (0, 250, 120), 9, 1.0), 1)
    assert_writes((20, HEIGHT + 5, 40, HEIGHT + 5, (0, 250, 120), 9, 1.0), 0)


def test_case_05_boundary_sweep_is_exact() -> None:
    """Every stamp offset around each edge must match the mathematical boundary.

    A stamp with thickness t spans offset (-t) // 2 .. t // 2. The guard may
    only skip when the whole span is outside the half-open frame range.
    """
    for thickness in range(1, 14):
        # Mirrors the production expressions range(-t // 2, t // 2 + 1).
        low, high = -thickness // 2, thickness // 2
        for offset in range(-8, 9):
            for edge, coordinates in (
                ('left', (offset, 5, offset, 45)),
                ('right', (WIDTH + offset, 5, WIDTH + offset, 45)),
                ('top', (5, offset, 45, offset)),
                ('bottom', (5, HEIGHT + offset, 45, HEIGHT + offset)),
            ):
                line = (*coordinates, (11, 22, 33), thickness, 1.0)
                baseline_writes, optimized_writes = write_counts(line)
                assert baseline_writes == optimized_writes, (thickness, offset, edge)
                baseline_events = candidate_events(
                    OriginalLineRenderer(False), bytearray(noise(WIDTH, HEIGHT, 9)),
                    (WIDTH, HEIGHT, *line))
                optimized_events = candidate_events(
                    StickmanRenderer(False), bytearray(noise(WIDTH, HEIGHT, 9)),
                    (WIDTH, HEIGHT, *line))
                if edge == 'left':
                    center = offset
                elif edge == 'right':
                    center = WIDTH + offset
                elif edge == 'top':
                    center = offset
                else:
                    center = HEIGHT + offset
                visible = center + low < (WIDTH if edge in ('left', 'right') else HEIGHT) \
                    and center + high >= 0
                # Day-20: mirror the production interior condition for this
                # sweep line (endpoints (offset, 5)-(offset, 45) for the
                # left/right edges, (5, offset)-(45, offset) for top/bottom).
                # Fully interior opaque stamps may skip the candidate scan
                # entirely; stamps that can clip must keep the scan.
                if edge in ('left', 'right'):
                    base_x = offset if edge == 'left' else WIDTH + offset
                    interior = (base_x + low >= 0 and base_x + high < WIDTH
                                and 5 + low >= 0 and 45 + high < HEIGHT)
                else:
                    base_y = offset if edge == 'top' else HEIGHT + offset
                    interior = (5 + low >= 0 and 45 + high < WIDTH
                                and base_y + low >= 0 and base_y + high < HEIGHT)
                if not visible:
                    assert optimized_events < baseline_events, (thickness, offset, edge)
                elif interior:
                    # Interior fast path: zero candidate evaluations expected.
                    assert optimized_events == 0 < baseline_events, (thickness, offset, edge)
                else:
                    assert optimized_events == baseline_events, (thickness, offset, edge)


def test_case_06_thick_line_crossing_frame_boundary() -> None:
    for line in ((WIDTH - 3, 30, WIDTH + 60, 30, (30, 30, 240), 15, 1.0),
                 (-20, 15, 30, 15, (30, 30, 240), 15, 0.4),
                 (20, -20, 40, 30, (240, 30, 30), 15, 1.0)):
        assert_writes(line, 1)
        assert_identical(line, 'case-6')


def test_case_07_endpoint_outside_line_crosses_frame() -> None:
    for line in ((-50, 10, 40, 50, (120, 240, 30), 2, 0.5),
                 (60, 70, 20, -20, (120, 240, 30), 4, 0.9)):
        assert_writes(line, 1)
        assert_identical(line, 'case-7')


def test_case_08_diagonal_crossing_frame() -> None:
    for line in ((-40, -30, 130, 90, (255, 255, 0), 1, 1.0),
                 (-40, -30, 130, 90, (255, 255, 0), 6, 0.8),
                 (130, -30, -40, 90, (255, 255, 0), 6, 0.8)):
        assert_writes(line, 1)
        assert_identical(line, 'case-8')


def test_case_09_very_thick_line() -> None:
    for line in ((WIDTH // 2, 10, WIDTH // 2, 12, (60, 60, 60), 41, 1.0),
                 (WIDTH // 2, HEIGHT // 2, WIDTH // 2, HEIGHT // 2, (60, 60, 60), 65, 0.35),
                 (0, 30, WIDTH - 1, 30, (90, 10, 90), 51, 1.0)):
        assert_writes(line, 1)
        assert_identical(line, 'case-9')
    # A very thick stamp whose center is far outside is still skipped.
    assert_writes((WIDTH + 40, 30, WIDTH + 40, 30, (5, 5, 5), 41, 1.0), 0)
    assert_identical((WIDTH + 40, 30, WIDTH + 40, 30, (5, 5, 5), 41, 1.0), 'case-9-far')
    # ...but a thick stamp reaching back into the frame is not skipped.
    assert_writes((WIDTH + 18, 30, WIDTH + 18, 30, (5, 5, 5), 41, 1.0), 1)


def test_case_10_boundary_coordinates() -> None:
    for line in ((0, 0, WIDTH - 1, 0, (255, 255, 255), 1, 1.0),
                 (0, HEIGHT - 1, WIDTH - 1, HEIGHT - 1, (255, 255, 255), 3, 1.0),
                 (0, HEIGHT // 2, WIDTH - 1, HEIGHT // 2, (255, 255, 255), 1, 1.0),
                 (WIDTH - 1, 0, WIDTH - 1, HEIGHT - 1, (200, 0, 200), 3, 1.0),
                 (0, 0, 0, 0, (12, 34, 56), 4, 1.0),
                 (WIDTH - 1, HEIGHT - 1, WIDTH - 1, HEIGHT - 1, (12, 34, 56), 4, 1.0),
                 (0, HEIGHT - 1, 0, HEIGHT - 1, (12, 34, 56), 4, 1.0),
                 (WIDTH - 1, 0, WIDTH - 1, 0, (12, 34, 56), 4, 1.0),
                 (-2, HEIGHT // 2, -2, HEIGHT // 2, (45, 45, 45), 9, 1.0),
                 (WIDTH // 2, -2, WIDTH // 2, -2, (45, 45, 45), 8, 1.0)):
        assert_writes(line, 1)
        assert_identical(line, 'case-10')
    # A stamp at x = -1 with thickness 1 spans x = -2..-1, so nothing is visible.
    assert_writes((-1, 0, -1, 0, (99, 99, 99), 1, 1.0), 0)
    assert_identical((-1, 0, -1, 0, (99, 99, 99), 1, 1.0), 'case-10-negative-zero')
    # The same center with thickness 3 reaches x = 0.
    assert_writes((-1, 0, -1, 0, (99, 99, 99), 3, 1.0), 1)
    assert_identical((-1, 0, -1, 0, (99, 99, 99), 3, 1.0), 'case-10-negative-zero-thick')


def test_all_fixed_cases_and_sequences_pixel_identical() -> None:
    for label, line in fixed_cases():
        assert_identical(line, label)
    for seed in range(5):
        result = difference(*sequence_pair(seed))
        assert result['different_pixels'] == 0, (seed, result)
        assert result['maximum_channel_difference'] == 0, (seed, result)


def test_full_frames_pixel_identical() -> None:
    for index in range(6):
        result = difference(*scene_pair(index))
        assert result['different_pixels'] == 0, (index, result)
        assert result['maximum_channel_difference'] == 0, (index, result)


def test_suppressed_character_frames_pixel_identical() -> None:
    """Day-12 evidence path: primary character pushed off-screen by the amplifier."""
    for index in range(3):
        result = difference(*suppressed_character_pair(index))
        assert result['different_pixels'] == 0, (index, result)
        assert result['maximum_channel_difference'] == 0, (index, result)


def test_guard_skips_work_only_for_invisible_stamps() -> None:
    frame_size = (WIDTH, HEIGHT)
    offscreen = (-30000, 8, -28000, 8, (9, 9, 9), 11, 1.0)
    partly_visible = (-30000, 30, 30000, 35, (9, 9, 9), 11, 1.0)
    fully_visible = (0, HEIGHT // 2, WIDTH - 1, HEIGHT // 2, (9, 9, 9), 11, 1.0)
    baseline_offscreen = candidate_events(OriginalLineRenderer(False), bytearray(noise(*frame_size, 3)),
                                          (*frame_size, *offscreen))
    optimized_offscreen = candidate_events(StickmanRenderer(False), bytearray(noise(*frame_size, 3)),
                                           (*frame_size, *offscreen))
    assert baseline_offscreen > 0
    assert optimized_offscreen == 0
    baseline_visible = candidate_events(OriginalLineRenderer(False), bytearray(noise(*frame_size, 3)),
                                        (*frame_size, *fully_visible))
    optimized_visible = candidate_events(StickmanRenderer(False), bytearray(noise(*frame_size, 3)),
                                         (*frame_size, *fully_visible))
    # Day-20: this line is edge-clipped (its end stamps cross both the left
    # and right frame edges), so the clipping-safe candidate scan must still
    # run and match the pre-Day-13 baseline exactly.
    assert optimized_visible == baseline_visible
    assert baseline_visible > 0
    # A fully interior opaque line skips the candidate scan entirely.
    interior_line = (20, 20, 60, 40, (9, 9, 9), 11, 1.0)
    baseline_interior = candidate_events(OriginalLineRenderer(False), bytearray(noise(*frame_size, 4)),
                                         (*frame_size, *interior_line))
    optimized_interior = candidate_events(StickmanRenderer(False), bytearray(noise(*frame_size, 4)),
                                          (*frame_size, *interior_line))
    assert baseline_interior > 0
    assert optimized_interior == 0
    baseline_partial = candidate_events(OriginalLineRenderer(False), bytearray(noise(*frame_size, 3)),
                                        (*frame_size, *partly_visible))
    optimized_partial = candidate_events(StickmanRenderer(False), bytearray(noise(*frame_size, 3)),
                                         (*frame_size, *partly_visible))
    assert 0 < optimized_partial < baseline_partial
    assert_writes(partly_visible, 1)
    assert_identical(offscreen, 'guard-offscreen')
    assert_identical(partly_visible, 'guard-partly-visible')
    assert_identical(fully_visible, 'guard-fully-visible')


def test_counting_renderers_track_real_writes() -> None:
    line = (5, 5, 40, 30, (200, 200, 200), 3, 1.0)
    counter = CountingStickmanRenderer()
    counter._draw_line(bytearray(noise(WIDTH, HEIGHT, 1)), WIDTH, HEIGHT, *line)
    assert counter.writes > 0
    reference = CountingLineRenderer()
    reference._draw_line(bytearray(noise(WIDTH, HEIGHT, 1)), WIDTH, HEIGHT, *line)
    assert reference.writes == counter.writes


def test_bresenham_stepping_source_unchanged() -> None:
    """The guard must not alter stepping, rounding or endpoint handling."""
    from inspect import getsource
    optimized = getsource(StickmanRenderer._draw_line)
    baseline = getsource(OriginalLineRenderer._draw_line)
    stepping = ['e2 = 2 * err', 'if e2 > -dy:', 'if e2 < dx:', 'err -= dy', 'err += dx',
                'x += sx', 'y += sy', 'if x == x1 and y == y1:', 'err = dx - dy']
    for snippet in stepping:
        assert snippet in optimized, snippet
        assert snippet in baseline, snippet
    assert 'while True:' in optimized
    assert 'if 0 <= px < width and 0 <= py < height:' in optimized


def test_day11_rectangle_fast_path_still_active() -> None:
    """The Day-11 opaque row-slice rectangle write must remain in place."""
    from inspect import getsource
    source = getsource(StickmanRenderer._draw_rect)
    assert 'frame[base:base + len(scanline)] = scanline' in source
    assert 'if opacity >= 1.0 and w > 0 and h > 0:' in source

    renderer = StickmanRenderer(False)
    for rect, opacity in (((10, 10, 20, 15), 1.0), ((10, 10, 20, 15), 0.5),
                          ((-10, -10, 30, 30), 1.0), ((WIDTH - 3, HEIGHT - 3, 40, 40), 1.0),
                          ((5, 5, 0, 8), 1.0), ((5, 5, 8, 0), 1.0)):
        initial = noise(WIDTH, HEIGHT, 21)
        frame = bytearray(initial)
        renderer._draw_rect(frame, WIDTH, HEIGHT, rect[0], rect[1], rect[2], rect[3],
                            (33, 66, 99), opacity)
        x = max(0, min(int(rect[0]), WIDTH - 1))
        y = max(0, min(int(rect[1]), HEIGHT - 1))
        w = max(0, min(int(rect[2]), WIDTH - x))
        h = max(0, min(int(rect[3]), HEIGHT - y))
        expected = bytearray(initial)
        for row in range(y, y + h):
            for col in range(w):
                StickmanRenderer._blend_pixel(expected, (row * WIDTH + x + col) * 3,
                                              (33, 66, 99), opacity)
        assert bytes(frame) == bytes(expected), (rect, opacity)


def test_lines_and_rectangles_combined_pixel_identical() -> None:
    """Interleaved line/rectangle drawing stays byte-identical end to end."""
    lines = [(0, 0, WIDTH - 1, HEIGHT - 1, (255, 0, 0), 5, 1.0),
             (WIDTH + 30, 4, WIDTH + 30, 4, (7, 7, 7), 17, 1.0),
             (-50, 10, 40, 50, (0, 255, 0), 3, 0.5),
             (WIDTH // 2, -2, WIDTH // 2, HEIGHT + 2, (0, 0, 255), 9, 0.8)]
    initial = noise(WIDTH, HEIGHT, 33)
    frames = [bytearray(initial), bytearray(initial)]
    for renderer, frame in zip((OriginalLineRenderer(False), StickmanRenderer(False)), frames):
        for line in lines:
            renderer._draw_line(frame, WIDTH, HEIGHT, *line)
        renderer._draw_rect(frame, WIDTH, HEIGHT, 20, 15, 30, 20, (9, 9, 9), 1.0)
        for line in lines:
            renderer._draw_line(frame, WIDTH, HEIGHT, *line)
    assert bytes(frames[0]) == bytes(frames[1])


def test_opacity_clamping_and_args_unchanged() -> None:
    """Opacity clamping stays identical and line arguments are not mutated."""
    for opacity, clamped in ((1.5, 1.0), (-0.5, 0.0), (1.0, 1.0), (0.0, 0.0)):
        high = (10, 10, 60, 50, (10, 60, 200), 5, opacity)
        low = (10, 10, 60, 50, (10, 60, 200), 5, clamped)
        initial = noise(WIDTH, HEIGHT, 4)
        frames = []
        for line in (high, low):
            frame = bytearray(initial)
            StickmanRenderer(False)._draw_line(frame, WIDTH, HEIGHT, *line)
            frames.append(bytes(frame))
        assert frames[0] == frames[1], opacity
        assert_identical(high, f'opacity-{opacity}')
    for _label, line in fixed_cases()[:5]:
        values = list(line)
        StickmanRenderer(False)._draw_line(bytearray(noise(WIDTH, HEIGHT, 2)), WIDTH, HEIGHT, *values)
        assert values == list(line)

