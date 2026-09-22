"""Diagnostic-only, reversible Day-16 method timers; no raster replacements."""
from __future__ import annotations

import inspect
import time
from collections import defaultdict
from functools import wraps

from src.services.stickman_renderer import StickmanRenderer
from PIL import Image


class FrameProfiler:
    """Single-threaded renderer profiler with inclusive and exclusive accounting.

    Exclusive time subtracts child wrapper spans (including their bookkeeping).
    Uninstrumented pixel helpers remain in their primitive caller, intentionally.
    """

    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.stack = []
        self.restore = []
        self.methods = defaultdict(lambda: {'calls': 0, 'inclusive': 0.0, 'exclusive': 0.0})
        self.scenes = []
        self.active_scene = None
        self.in_frame = False
        self.frame_seconds = 0.0
        self.frame_count = 0
        self.exclusive = defaultdict(float)
        self.owners = defaultdict(float)
        self.primitive_calls = defaultdict(int)

    def wrap(self, cls, name, category):
        descriptor = inspect.getattr_static(cls, name)
        original = getattr(cls, name)
        label = cls.__name__ + '.' + name

        @wraps(original)
        def measured(*args, **kwargs):
            entry = self.clock()
            is_frame = name == '_generate_frame'
            if is_frame:
                self.in_frame = True
                self.frame_count += 1
            inside = self.in_frame
            owner = None
            if inside and name in ('_draw_rect', '_draw_line', '_draw_circle'):
                caller = inspect.currentframe().f_back
                if caller.f_code.co_name == '_generate_frame':
                    if 1145 <= caller.f_lineno <= 1196:
                        owner = 'primary_character'
                    elif caller.f_lineno <= 1120:
                        owner = 'floor_or_sun'
                del caller
                opacity = kwargs.get('opacity', args[-1] if len(args) > {'_draw_rect': 9, '_draw_line': 10, '_draw_circle': 8}[name] else 1.0)
                self.primitive_calls[name + ('.opaque' if opacity >= 1 else '.nonopaque')] += 1
            slot = [0.0]
            self.stack.append(slot)
            start = self.clock()
            try:
                return original(*args, **kwargs)
            finally:
                elapsed = self.clock() - start
                own = elapsed - slot[0]
                self.stack.pop()
                rec = self.methods[label]
                rec['calls'] += 1
                rec['inclusive'] += elapsed
                rec['exclusive'] += own
                if inside:
                    self.exclusive[category] += own
                if owner:
                    self.owners[owner] += elapsed
                if inside and name in ('_draw_named_character', '_draw_typed_object', '_draw_environment_layers', '_draw_scene_effects'):
                    self.owners[name] += elapsed
                if is_frame:
                    self.frame_seconds += elapsed
                    self.in_frame = False
                if self.stack:
                    self.stack[-1][0] += self.clock() - entry

        setattr(cls, name, staticmethod(measured) if isinstance(descriptor, staticmethod) else measured)
        self.restore.append((cls, name, descriptor))

    def install(self):
        categories = {
            '_generate_frame': 'other', '_draw_rect': 'rectangles',
            '_draw_line': 'lines', '_draw_circle': 'ellipses',
            '_draw_text_elements': 'text', '_draw_caption_overlay': 'text',
            '_decorate_classroom_board': 'text', '_draw_text_lines_on_frame': 'text',
            '_load_font': 'text', '_draw_named_character': 'characters',
            '_draw_environment_layers': 'background',
            '_draw_typed_object': 'geometry', '_draw_scene_effects': 'geometry',
            '_effect_target_bounds': 'geometry', '_evaluate_motion_state': 'geometry',
            '_resolve_named_characters': 'geometry', '_compute_pose': 'geometry',
            '_apply_camera_pattern': 'geometry',
        }
        categories.update({n: 'geometry' for n in vars(StickmanRenderer) if n.startswith('_obj_')})
        for name, category in categories.items():
            self.wrap(StickmanRenderer, name, category)
        for name in ('paste', 'alpha_composite'):
            self.wrap(Image.Image, name, 'compositing')
        for name in ('tobytes', 'frombytes', 'copy', 'convert'):
            self.wrap(Image.Image, name, 'image_copies')
        return self

    def snapshot(self):
        return {
            'frame_generation_seconds': self.frame_seconds,
            'frame_count': self.frame_count,
            'exclusive': dict(self.exclusive),
            'owners_inclusive': dict(self.owners),
            'primitive_calls': dict(self.primitive_calls),
            'methods': {k: dict(v) for k, v in self.methods.items()},
        }

    def close(self):
        for cls, name, descriptor in reversed(self.restore):
            setattr(cls, name, descriptor)
        self.restore.clear()


def delta(after, before):
    """Recursive numeric snapshot difference for each sequential scene."""
    return {key: delta(value, before.get(key, {})) if isinstance(value, dict)
            else value - before.get(key, 0) for key, value in after.items()}
