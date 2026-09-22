"""Deterministic RGB comparisons for the Day-13 off-screen line-stamp guard.

The frozen pre-optimization `_draw_line` lives in scripts/day13_line_reference.py.
Every comparison draws the same sequence into two separate buffers and compares
the raw bytes; no tolerance is applied.
"""
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
from scripts.day13_line_reference import OriginalLineRenderer  # noqa: E402
from src.services.stickman_renderer import StickmanRenderer  # noqa: E402


def difference(a: bytes, b: bytes) -> dict:
    if len(a) != len(b):
        raise AssertionError('Frame buffer length changed')
    count = sum(a[i:i + 3] != b[i:i + 3] for i in range(0, len(a), 3))
    return {'different_pixels': count,
            'maximum_channel_difference': max((abs(x - y) for x, y in zip(a, b)), default=0),
            'baseline_sha256': hashlib.sha256(a).hexdigest(),
            'optimized_sha256': hashlib.sha256(b).hexdigest()}


def _candidate_line_numbers(renderer) -> set:
    """Absolute source-line numbers of the thickness-candidate assignment."""
    from inspect import getsourcelines
    lines, first_line = getsourcelines(renderer._draw_line)
    start = next(i for i, text in enumerate(lines) if text.lstrip().startswith('def _draw_line'))
    return {first_line + i for i, text in enumerate(lines)
            if i > start and text.strip().startswith('px, py =')}


def candidate_events(renderer, frame: bytearray, args: tuple) -> int:
    """Count executed thickness-candidate evaluations for one `_draw_line` call.

    Counts executions of the `px, py = x + tx, y + ty` line, i.e. exactly the
    per-candidate work the guard is allowed to remove. Independent of how many
    physical lines the guard condition spans.
    """
    method = renderer._draw_line
    code = method.__func__.__code__
    candidates = _candidate_line_numbers(renderer)
    assert candidates, 'candidate line not found'
    counter = [0]

    def local(frame_obj, event, arg):
        if event == 'line' and frame_obj.f_lineno in candidates:
            counter[0] += 1
        return local

    def trace(frame_obj, event, arg):
        if event == 'call' and frame_obj.f_code is code:
            return local
        return None

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        method(frame, *args)
    finally:
        sys.settrace(previous)
    return counter[0]


def line_events(renderer, frame: bytearray, args: tuple) -> int:
    """Count all executed source lines inside `_draw_line` (secondary metric).

    `args` are the full positional arguments after `frame` (width, height, ...).
    Traces only the target code object, so helper frames add no events.
    """
    method = renderer._draw_line
    code = method.__func__.__code__
    counter = [0]

    def local(frame_obj, event, arg):
        if event == 'line':
            counter[0] += 1
        return local

    def trace(frame_obj, event, arg):
        if event == 'call' and frame_obj.f_code is code:
            return local
        return None

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        method(frame, *args)
    finally:
        sys.settrace(previous)
    return counter[0]


def fixed_cases(width: int = 97, height: int = 61) -> list[tuple[str, tuple]]:
    """The ten required Day-13 scenarios plus boundary/thickness edge probes.

    Args are (x0, y0, x1, y1, color, thickness, opacity).
    """
    cases: list[tuple[str, tuple]] = [
        # Case 1 - wholly off-screen left: thin, thick and single-point stamps.
        ('case-1-offscreen-left', (-4 * width, 10, -2 * width, 40, (200, 10, 10), 3, 1.0)),
        ('case-1-offscreen-left-thick', (-4 * width, -5, -2 * width, height + 9, (10, 200, 10), 13, 0.5)),
        ('case-1-offscreen-left-point', (-width - 20, height // 2, -width - 20, height // 2, (1, 2, 3), 9, 1.0)),
        # Case 2 - wholly off-screen right.
        ('case-2-offscreen-right', (width + 20, 10, 3 * width, 40, (200, 10, 10), 1, 1.0)),
        ('case-2-offscreen-right-thick', (width + 20, -5, 3 * width, height + 9, (10, 10, 200), 21, 0.75)),
        ('case-2-offscreen-right-point', (width + 30, 4, width + 30, 4, (7, 7, 7), 17, 1.0)),
        # Case 3 - completely above the frame.
        ('case-3-offscreen-above', (10, -4 * height, 60, -height - 10, (200, 200, 10), 5, 1.0)),
        ('case-3-offscreen-above-diagonal', (-30, -height - 40, width + 30, -height - 3, (0, 0, 0), 12, 0.25)),
        # Case 4 - completely below the frame.
        ('case-4-offscreen-below', (10, height + 10, 60, height * 3, (10, 200, 200), 5, 1.0)),
        ('case-4-offscreen-below-diagonal', (-30, height + 4, width + 30, height * 2, (255, 255, 255), 7, 0.6)),
        # Case 5 - thick stamps exactly outside versus just touching each edge.
        ('case-5-thick-touches-right', (width + 4, 20, width + 4, 40, (250, 120, 0), 9, 1.0)),
        ('case-5-thick-miss-right', (width + 5, 20, width + 5, 40, (250, 120, 0), 9, 1.0)),
        ('case-5-thick-touches-left', (-4, 20, -4, 40, (250, 120, 0), 9, 1.0)),
        ('case-5-thick-miss-left', (-5, 20, -5, 40, (250, 120, 0), 9, 1.0)),
        ('case-5-thick-touches-top', (20, -4, 40, -4, (0, 250, 120), 9, 1.0)),
        ('case-5-thick-miss-top', (20, -5, 40, -5, (0, 250, 120), 9, 1.0)),
        ('case-5-thick-touches-bottom', (20, height + 4, 40, height + 4, (0, 250, 120), 9, 1.0)),
        ('case-5-thick-miss-bottom', (20, height + 5, 40, height + 5, (0, 250, 120), 9, 1.0)),
        # Case 6 - thick lines crossing a frame boundary.
        ('case-6-thick-cross-right', (width - 3, 30, width + 60, 30, (30, 30, 240), 15, 1.0)),
        ('case-6-thick-cross-left', (-20, 15, 30, 15, (30, 30, 240), 15, 0.4)),
        ('case-6-thick-cross-top', (20, -20, 40, 30, (240, 30, 30), 15, 1.0)),
        # Case 7 - an endpoint outside while the segment crosses the frame.
        ('case-7-endpoint-outside-left', (-50, 10, 40, 50, (120, 240, 30), 2, 0.5)),
        ('case-7-endpoint-outside-right', (60, 70, 20, -20, (120, 240, 30), 4, 0.9)),
        # Case 8 - diagonals crossing the frame in both directions.
        ('case-8-diagonal-thin', (-40, -30, 130, 90, (255, 255, 0), 1, 1.0)),
        ('case-8-diagonal-thick', (-40, -30, 130, 90, (255, 255, 0), 6, 0.8)),
        ('case-8-diagonal-reverse', (130, -30, -40, 90, (255, 255, 0), 6, 0.8)),
        # Case 9 - very thick stamps.
        ('case-9-very-thick-vertical', (width // 2, 10, width // 2, 12, (60, 60, 60), 41, 1.0)),
        ('case-9-very-thick-point', (width // 2, height // 2, width // 2, height // 2, (60, 60, 60), 65, 0.35)),
        ('case-9-very-thick-span', (0, 30, width - 1, 30, (90, 10, 90), 51, 1.0)),
        # Case 10 - coordinates exactly at the frame boundaries.
        ('case-10-top-row', (0, 0, width - 1, 0, (255, 255, 255), 1, 1.0)),
        ('case-10-bottom-row', (0, height - 1, width - 1, height - 1, (255, 255, 255), 3, 1.0)),
        ('case-10-middle-row', (0, height // 2, width - 1, height // 2, (255, 255, 255), 1, 1.0)),
        ('case-10-right-column', (width - 1, 0, width - 1, height - 1, (200, 0, 200), 3, 1.0)),
        ('case-10-corner-tl', (0, 0, 0, 0, (12, 34, 56), 4, 1.0)),
        ('case-10-corner-br', (width - 1, height - 1, width - 1, height - 1, (12, 34, 56), 4, 1.0)),
        ('case-10-corner-bl', (0, height - 1, 0, height - 1, (12, 34, 56), 4, 1.0)),
        ('case-10-corner-tr', (width - 1, 0, width - 1, 0, (12, 34, 56), 4, 1.0)),
        ('case-10-straddle-left-edge', (-2, height // 2, -2, height // 2, (45, 45, 45), 9, 1.0)),
        ('case-10-straddle-top-edge', (width // 2, -2, width // 2, -2, (45, 45, 45), 8, 1.0)),
        ('case-10-negative-zero', (-1, 0, -1, 0, (99, 99, 99), 1, 1.0)),
    ]
    for t in (-4, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 31):
        cases.append((f'thickness-{t}', (0, 0, width - 1, height - 1, (200, 100, 50), t, 1.0)))
        cases.append((f'thickness-{t}-offscreen', (-width - 6, 5, -width - 6, 40, (200, 100, 50), t, 1.0)))
    for op in (0.0, 0.01, 0.25, 0.5, 0.999, 1.0, 1.5, -0.5):
        cases.append((f'opacity-{op}', (10, 10, 60, 50, (10, 60, 200), 5, op)))
    cases.extend([
        ('fractional-inside', (10.9, 20.7, 60.2, 55.9, (77, 88, 99), 3, 1.0)),
        ('fractional-outside', (-20.6, -10.4, 50.5, 30.1, (77, 88, 99), 3, 1.0)),
        ('fractional-straddle', (width + 0.6, 12.2, width - 0.7, 40.9, (77, 88, 99), 7, 1.0)),
        ('far-away-point', (10 ** 6, 10 ** 6, 10 ** 6, 10 ** 6, (5, 5, 5), 9, 1.0)),
        ('far-away-negative-point', (-10 ** 6, 5, -10 ** 6, 5, (5, 5, 5), 31, 1.0)),
        ('zero-length-inside', (width // 3, height // 3, width // 3, height // 3, (222, 111, 0), 7, 1.0)),
    ])
    return cases
class _WriteCounter:
    """Mixin counting effective pixel writes; blending itself is unchanged.

    Day-16 extension: the opaque fast path writes whole row spans through
    `_blit_span` instead of one `_blend_pixel` call per pixel. Each span of
    N pixels is exactly equivalent to N per-pixel opaque writes, so it
    contributes N to the write count. Byte-identity is enforced separately
    by the buffer comparisons.
    """

    def _blend_pixel(self, frame, idx, color, opacity):
        self.writes += 1
        StickmanRenderer._blend_pixel(frame, idx, color, opacity)

    def _blit_span(self, frame, base, scanline):
        self.writes += len(scanline) // 3
        StickmanRenderer._blit_span(self, frame, base, scanline)


class CountingLineRenderer(_WriteCounter, OriginalLineRenderer):
    def __init__(self) -> None:
        super().__init__(False)
        self.writes = 0


class CountingStickmanRenderer(_WriteCounter, StickmanRenderer):
    def __init__(self) -> None:
        super().__init__(False)
        self.writes = 0


def noise(width: int, height: int, seed: int) -> bytes:
    rng = random.Random(seed)
    return bytes(rng.randrange(256) for _ in range(width * height * 3))


def single_line_pair(args: tuple, width: int = 97, height: int = 61, seed: int = 0) -> tuple[bytes, bytes]:
    """One line drawn onto two identical deterministic noise buffers."""
    initial = noise(width, height, seed)
    frames = [bytearray(initial), bytearray(initial)]
    for renderer, frame in zip((OriginalLineRenderer(False), StickmanRenderer(False)), frames):
        renderer._draw_line(frame, width, height, *args)
    return bytes(frames[0]), bytes(frames[1])


def write_counts(args: tuple, width: int = 97, height: int = 61) -> tuple[int, int]:
    """Baseline vs optimized `_blend_pixel` call counts for a single line."""
    initial = noise(width, height, 1234)
    counts = []
    for renderer in (CountingLineRenderer(), CountingStickmanRenderer()):
        renderer._draw_line(bytearray(initial), width, height, *args)
        counts.append(renderer.writes)
    return counts[0], counts[1]


def sequence_pair(seed: int, width: int = 97, height: int = 61) -> tuple[bytes, bytes]:
    """All named cases plus pseudo-random lines, compared after every draw."""
    initial = noise(width, height, seed)
    frames = [bytearray(initial), bytearray(initial)]
    renderers = [OriginalLineRenderer(False), StickmanRenderer(False)]
    rng = random.Random(seed + 1000)
    lines = [args for _, args in fixed_cases(width, height)]
    for i in range(150):
        lines.append((rng.randrange(-2 * width, 3 * width), rng.randrange(-2 * height, 3 * height),
                      rng.randrange(-2 * width, 3 * width), rng.randrange(-2 * height, 3 * height),
                      tuple(rng.randrange(256) for _ in range(3)),
                      rng.choice([-2, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 16, 24, 40, 61]),
                      [0, 0.01, 0.25, 0.5, 0.999, 1, 1.5][i % 7]))
    for args in lines:
        for renderer, frame in zip(renderers, frames):
            renderer._draw_line(frame, width, height, *args)
        assert frames[0] == frames[1], f'First divergent line: {args}'
    return bytes(frames[0]), bytes(frames[1])

def scene_state(index: int, width: int, height: int, suppress: bool = False) -> dict:
    state = {
        'environment': {'type': ['default', 'classroom', 'bedroom'][index % 3]},
        'camera_zoom': 1 + index * 0.02, 'camera_pan_x': index * 2,
        'object_layers': {'moving': {'x': 25 + index * 10, 'y': 40,
                                    'scale': 1 + index * 0.1, 'opacity': 0.55}},
        'typed_objects': {name: {'type': name, 'x': width * (0.2 + n * 0.12),
                                'y': height * 0.6, 'opacity': 1 if n % 2 else 0.55}
                          for n, name in enumerate(['book', 'desk', 'chair', 'graph', 'laptop'])},
        'text_specs': [{'text': 'Line stamp equivalence', 'x': 0.5, 'y': 0.9}],
    }
    if suppress:
        state['suppress_primary_character'] = True
    return state


def scene_pair(index: int, width: int = 320, height: int = 180) -> tuple[bytes, bytes]:
    """Complete frames from the frozen and optimized renderers."""
    t = index / 3
    frames = []
    for renderer in (OriginalLineRenderer(False), StickmanRenderer(False)):
        local = copy.deepcopy(scene_state(index, width, height))
        pose = renderer._compute_pose('walk', t, 4, width, height, motion_state=local)
        frames.append(renderer._generate_frame(width, height, t, 4, index, 120,
                                              pose, job={}, motion_state=local))
    return tuple(frames)


def suppressed_character_pair(index: int, width: int = 320, height: int = 180) -> tuple[bytes, bytes]:
    """Reproduces the Day-12 amplifier: primary character pushed off-screen."""
    t = index / 3
    frames = []
    for renderer in (OriginalLineRenderer(False), StickmanRenderer(False)):
        local = copy.deepcopy(scene_state(index, width, height, suppress=True))
        pose = renderer._compute_pose('walk', t, 4, width, height, motion_state=local)
        pose.stickman_x = -10000
        pose.stickman_y = -10000
        frames.append(renderer._generate_frame(width, height, t, 4, index, 120,
                                              pose, job={}, motion_state=local))
    return tuple(frames)


def measure_work_elimination(width: int = 97, height: int = 61) -> dict:
    """Candidate-pixel evaluations per implementation, with pixel equality."""
    cases = {
        'offscreen-left-long': (-30000, 8, -28000, 8, (9, 9, 9), 11, 1.0),
        'offscreen-above-long': (10 ** 5, -10 ** 5, 10 ** 5 + 2000, -10 ** 5, (9, 9, 9), 9, 1.0),
        'crossing-frame-long': (-30000, 30, 30000, 35, (9, 9, 9), 9, 1.0),
    }
    results = {}
    for label, line in cases.items():
        initial = noise(width, height, 3)
        baseline = candidate_events(OriginalLineRenderer(False), bytearray(initial), (width, height, *line))
        optimized = candidate_events(StickmanRenderer(False), bytearray(initial), (width, height, *line))
        results[label] = {'baseline_candidates': baseline, 'optimized_candidates': optimized,
                          'candidates_eliminated': baseline - optimized,
                          'reduction_factor': (baseline / optimized) if optimized else None,
                          **difference(*single_line_pair(line, width, height, 3))}
    return results

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'output/day13_optimization')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for label, line in fixed_cases():
        baseline_writes, optimized_writes = write_counts(line)
        assert baseline_writes == optimized_writes, f'Write count changed for {label}'
        results.append({'case': label, 'baseline_writes': baseline_writes,
                        'optimized_writes': optimized_writes, **difference(*single_line_pair(line))})
    for seed in range(20):
        results.append({'case': f'line-sequence-{seed}', **difference(*sequence_pair(seed))})
    for i in range(9):
        results.append({'case': f'full-frame-{i}', **difference(*scene_pair(i))})
    for i in range(3):
        results.append({'case': f'suppressed-character-frame-{i}',
                        **difference(*suppressed_character_pair(i))})
    for i in range(3):
        pair = scene_pair(i, 1920, 1080)
        results.append({'case': f'1080p-frame-{i}', **difference(*pair)})
        from PIL import Image
        for label, data in zip(('baseline', 'optimized'), pair):
            Image.frombytes('RGB', (1920, 1080), data).save(args.output_dir / f'day13-{label}-{i}.png')
    report = {
        'comparison_count': len(results),
        'different_pixels': sum(r['different_pixels'] for r in results),
        'maximum_channel_difference': max(r['maximum_channel_difference'] for r in results),
        'cases': results,
        'work_elimination': measure_work_elimination(),
        'notes': ['Frozen pre-Day-13 `_draw_line` compared byte-for-byte with the production guard.',
                  'No tolerance applied: any differing pixel count or channel value fails.',
                  'Work elimination counts executed `_draw_line` source lines via sys.settrace.'],
    }
    (args.output_dir / 'pixel_equivalence.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))
    return int(report['different_pixels'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())

