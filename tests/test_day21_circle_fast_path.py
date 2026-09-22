"""Day-21 focused tests: opaque `_draw_circle` row-span fast path.

Pixel-equivalence reference: the frozen pre-Day-21 `_draw_circle` in
scripts/day21_circle_reference.py (verbatim copy taken before the Day-21
change). Effective write counts use the established convention from
scripts/compare_day13_lines.py `_WriteCounter`: one `_blend_pixel` call
contributes one effective write (zero-opacity calls contribute none);
`_blit_span` contributes len(scanline)//3. Opaque spans must therefore
contribute exactly the same pixel count as the per-pixel reference loop.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.compare_day13_lines import difference, noise  # noqa: E402
from scripts.day21_circle_reference import OriginalCircleRenderer  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402

WIDTH = 97
HEIGHT = 61

# (label, (cx, cy, radius, color, opacity)) — interior opaque circles.
INTERIOR_CASES = [
    ('interior-small-r1', (48, 30, 1, (200, 10, 10), 1.0)),
    ('interior-medium-r10', (48, 30, 10, (200, 10, 10), 1.0)),
    ('interior-large-r20', (48, 30, 20, (10, 200, 10), 1.0)),
    ('interior-r3', (20, 15, 3, (10, 10, 200), 1.0)),
    ('interior-r13', (70, 45, 13, (77, 88, 99), 1.0)),
    ('interior-red', (48, 30, 8, (255, 0, 0), 1.0)),
    ('interior-white', (48, 30, 8, (255, 255, 255), 1.0)),
    ('interior-black', (48, 30, 8, (0, 0, 0), 1.0)),
    ('interior-fractional', (48.9, 30.4, 7.5, (222, 111, 0), 1.0)),
    ('opaque-overclamped-1.5', (48, 30, 10, (10, 60, 200), 1.5)),
]

# Stamps that touch or cross a frame edge: clamps must behave identically.
CLIPPED_CASES = [
    ('clip-left', (-3, 30, 10, (30, 30, 240), 1.0)),
    ('clip-right', (WIDTH + 2, 30, 10, (30, 30, 240), 1.0)),
    ('clip-top', (48, -3, 10, (240, 30, 30), 1.0)),
    ('clip-bottom', (48, HEIGHT + 2, 10, (240, 30, 30), 1.0)),
    ('clip-corner-tl', (-3, -3, 12, (120, 240, 30), 1.0)),
    ('clip-corner-tr', (WIDTH + 2, -3, 12, (120, 240, 30), 1.0)),
    ('clip-corner-bl', (-3, HEIGHT + 2, 12, (120, 240, 30), 1.0)),
    ('clip-corner-br', (WIDTH + 2, HEIGHT + 2, 12, (120, 240, 30), 1.0)),
    ('tangent-left-inside', (10, 30, 10, (45, 45, 45), 1.0)),
    ('tangent-right-inside', (WIDTH - 11, 30, 10, (45, 45, 45), 1.0)),
    ('tangent-top-inside', (48, 10, 10, (45, 45, 45), 1.0)),
    ('tangent-bottom-inside', (48, HEIGHT - 11, 10, (45, 45, 45), 1.0)),
    ('center-on-left-edge', (0, 30, 10, (250, 120, 0), 1.0)),
    ('center-on-right-edge', (WIDTH - 1, 30, 10, (250, 120, 0), 1.0)),
    ('center-on-top-edge', (48, 0, 10, (250, 120, 0), 1.0)),
    ('center-on-bottom-edge', (48, HEIGHT - 1, 10, (250, 120, 0), 1.0)),
    ('radius-zero-clamps-to-1', (48, 30, 0, (222, 111, 0), 1.0)),
    ('radius-negative-clamps-to-1', (48, 30, -5, (222, 111, 0), 1.0)),
    ('full-width-span', (48, 30, 400, (60, 60, 60), 1.0)),
]
# Translucent circles must keep the per-pixel `_blend_pixel` path.
NON_OPAQUE_CASES = [
    ('translucent-half', (48, 30, 10, (200, 10, 10), 0.5)),
    ('translucent-quarter', (48, 30, 13, (90, 90, 90), 0.25)),
    ('translucent-clipped', (-3, 30, 10, (10, 60, 200), 0.5)),
    ('translucent-just-below-one', (48, 30, 10, (10, 60, 200), 0.999)),
]
# Zero/negative opacity must keep writing nothing.
ZERO_CASES = [
    ('zero-opacity', (48, 30, 10, (200, 10, 10), 0.0)),
    ('negative-opacity', (48, 30, 10, (200, 10, 10), -0.5)),
    ('zero-opacity-clipped', (-3, 30, 10, (10, 60, 200), 0.0)),
]

class _CircleCounter:
    """Counts `_blend_pixel`/`_blit_span` calls plus effective pixel writes."""

    blend_calls = 0
    span_calls = 0
    span_pixels = 0
    effective_writes = 0

    def _blend_pixel(self, frame, idx, color, opacity):
        self.blend_calls += 1
        if opacity > 0.0:
            self.effective_writes += 1
        StickmanRenderer._blend_pixel(frame, idx, color, opacity)

    def _blit_span(self, frame, base, scanline):
        self.span_calls += 1
        self.span_pixels += len(scanline) // 3
        self.effective_writes += len(scanline) // 3
        StickmanRenderer._blit_span(self, frame, base, scanline)


def _measured(cls, args, seed=0, draws=1):
    class _Counted(_CircleCounter, cls):
        pass

    renderer = _Counted()
    frame = bytearray(noise(WIDTH, HEIGHT, seed))
    for _ in range(draws):
        renderer._draw_circle(frame, WIDTH, HEIGHT, *args)
    return renderer


def _pair(args, seed=0):
    initial = noise(WIDTH, HEIGHT, seed)
    frames = [bytearray(initial), bytearray(initial)]
    for renderer, frame in zip((OriginalCircleRenderer(False),
                                StickmanRenderer(False)), frames):
        renderer._draw_circle(frame, WIDTH, HEIGHT, *args)
    return bytes(frames[0]), bytes(frames[1])


def _visible_pixels(args, width=WIDTH, height=HEIGHT):
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


def _row_count(args, width=WIDTH, height=HEIGHT):
    """Number of written rows (clamped bounding-box rows)."""
    cx, cy, radius, _color, _opacity = args
    cx, cy, radius = int(cx), int(cy), int(radius)
    cx = max(0, min(cx, width - 1))
    cy = max(0, min(cy, height - 1))
    radius = max(1, radius)
    y_min = max(0, cy - radius)
    y_max = min(height - 1, cy + radius)
    return y_max - y_min + 1


def _assert_identical(args, label):
    baseline, optimized = _pair(args)
    report = difference(baseline, optimized)
    assert report['different_pixels'] == 0, (label, report)
    assert report['maximum_channel_difference'] == 0, (label, report)
    assert report['baseline_sha256'] == report['optimized_sha256'], label

def test_opaque_circles_are_pixel_and_write_identical():
    for label, args in INTERIOR_CASES + CLIPPED_CASES:
        _assert_identical(args, label)
        reference = _measured(OriginalCircleRenderer, args)
        production = _measured(StickmanRenderer, args)
        assert production.effective_writes == reference.effective_writes, label
        expected = _visible_pixels(args)
        assert production.effective_writes == expected, \
            (label, production.effective_writes, expected)


def test_opaque_rows_go_through_blit_span():
    """Each opaque row becomes exactly one `_blit_span`; zero blend calls."""
    for label, args in INTERIOR_CASES + CLIPPED_CASES:
        production = _measured(StickmanRenderer, args)
        reference = _measured(OriginalCircleRenderer, args)
        rows = _row_count(args)
        assert production.span_calls == rows, (label, production.span_calls, rows)
        assert production.blend_calls == 0, label
        assert production.span_pixels == _visible_pixels(args), label
        # Reference context: the frozen path blends once per visible pixel.
        assert reference.blend_calls == _visible_pixels(args), label
        assert reference.span_calls == 0, label


def test_non_opaque_circles_keep_blend_pixel_path():
    for label, args in NON_OPAQUE_CASES:
        _assert_identical(args, label)
        reference = _measured(OriginalCircleRenderer, args)
        production = _measured(StickmanRenderer, args)
        assert production.blend_calls == reference.blend_calls > 0, \
            (label, production.blend_calls, reference.blend_calls)
        assert production.span_calls == 0, label
        assert production.effective_writes == reference.effective_writes, label


def test_zero_opacity_remains_write_free():
    for label, args in ZERO_CASES:
        _assert_identical(args, label)
        reference = _measured(OriginalCircleRenderer, args)
        production = _measured(StickmanRenderer, args)
        assert production.effective_writes == 0, (label, production.effective_writes)
        assert reference.effective_writes == 0, label
        assert production.blend_calls == reference.blend_calls, label
        assert production.span_calls == 0, label


def test_step1_probe_counts_are_preserved():
    """Effective writes match the Step-1 probe: r=1→5, r=10→317, r=20→1257."""
    for radius, expected in ((1, 5), (10, 317), (20, 1257)):
        args = (48, 30, radius, (200, 10, 10), 1.0)
        production = _measured(StickmanRenderer, args)
        assert production.effective_writes == expected, \
            (radius, production.effective_writes, expected)
        assert _visible_pixels(args) == expected


def test_overlapping_circles_preserve_effective_writes():
    """Rewriting the same opaque circle doubles effective writes, same bytes."""
    args = (48, 30, 20, (200, 10, 10), 1.0)
    initial = noise(WIDTH, HEIGHT, 0)
    frames = [bytearray(initial), bytearray(initial)]
    for renderer, frame in zip((OriginalCircleRenderer(False),
                                StickmanRenderer(False)), frames):
        renderer._draw_circle(frame, WIDTH, HEIGHT, *args)
        renderer._draw_circle(frame, WIDTH, HEIGHT, *args)
    report = difference(bytes(frames[0]), bytes(frames[1]))
    assert report['different_pixels'] == 0, report
    assert report['baseline_sha256'] == report['optimized_sha256']
    expected = 2 * _visible_pixels(args)
    reference = _measured(OriginalCircleRenderer, args, draws=2)
    production = _measured(StickmanRenderer, args, draws=2)
    assert reference.effective_writes == expected, \
        (reference.effective_writes, expected)
    assert production.effective_writes == expected, \
        (production.effective_writes, expected)



