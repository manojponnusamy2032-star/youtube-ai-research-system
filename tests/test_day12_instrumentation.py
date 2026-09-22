"""Validate diagnostic accounting, restoration and unchanged production pixels."""
import copy
import inspect

import pytest

from scripts.day12_instrumentation import FrameProfiler, delta
from src.services.stickman_renderer import StickmanRenderer


@pytest.mark.parametrize('environment', ['default', 'classroom', 'bedroom'])
def test_instrumentation_preserves_pixels_and_accounting(environment):
    renderer = StickmanRenderer(False)
    state = {'environment': {'type': environment},
             'text_specs': [{'text': 'Day 12 profiling', 'x': 0.5, 'y': 0.9}],
             'typed_objects': {'clock': {'type': 'clock', 'x': 200, 'y': 60}},
             'character_opacity': 0.6}
    pose = renderer._compute_pose('walk', 0.5, 2, 320, 180)
    original_font = inspect.getattr_static(StickmanRenderer, '_load_font')
    original_frame = StickmanRenderer._generate_frame
    expected = renderer._generate_frame(320, 180, 0.5, 2, 15, 60, pose,
                                         motion_state=copy.deepcopy(state))
    profiler = FrameProfiler().install()
    try:
        actual = renderer._generate_frame(320, 180, 0.5, 2, 15, 60, pose,
                                          motion_state=copy.deepcopy(state))
    finally:
        profiler.close()
    assert expected == actual
    assert StickmanRenderer._generate_frame is original_frame
    assert inspect.getattr_static(StickmanRenderer, '_load_font') is original_font
    snapshot = profiler.snapshot()
    assert snapshot['frame_count'] == 1
    assert all(v >= 0 for v in snapshot['exclusive'].values())
    assert sum(snapshot['exclusive'].values()) <= snapshot['frame_generation_seconds']
    assert snapshot['primitive_calls']['_draw_line.nonopaque'] >= 5
    assert snapshot['methods']['StickmanRenderer._draw_line']['calls'] >= 5
    assert not profiler.stack


def test_nested_wrappers_exclude_child_span():
    class Work:
        def outer(self):
            return self.inner()

        def inner(self):
            return 42

    profiler = FrameProfiler(clock=iter(range(100)).__next__)
    profiler.wrap(Work, 'outer', 'other')
    profiler.wrap(Work, 'inner', 'other')
    try:
        assert Work().outer() == 42
    finally:
        profiler.close()
    outer = profiler.methods['Work.outer']
    inner = profiler.methods['Work.inner']
    assert outer == {'calls': 1, 'inclusive': 5.0, 'exclusive': 2.0}
    assert inner == {'calls': 1, 'inclusive': 1.0, 'exclusive': 1.0}


def test_snapshot_delta_is_independent():
    assert delta({'x': 8, 'methods': {'a': {'calls': 4}}},
                 {'x': 3, 'methods': {'a': {'calls': 1}}}) == {
                     'x': 5, 'methods': {'a': {'calls': 3}}}
