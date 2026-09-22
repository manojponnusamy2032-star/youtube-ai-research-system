from __future__ import annotations



"""Day-22 text-path investigation instrumentation (measurement only).

Nothing in this module is imported by production code. Every probe wraps an
existing function at runtime and is removed again by ``close()``; the
production renderer file is never edited.

Two independent probes are provided:

* ``TextLineProbe`` -- per-source-line self time inside the text path only,
  using Python 3.12+ ``sys.monitoring`` local events (LINE / PY_START /
  PY_RETURN) enabled on the text-path code objects exclusively. Nested
  instrumented calls are subtracted from their caller, so every measured
  segment is attributed exactly once.
* ``TextPathProbe`` -- call counts, time, bytes and repetition keys for the
  PIL / ImageDraw operations the text path performs, plus a per-call record
  for every ``_draw_text_elements`` invocation.
"""


import hashlib
import inspect
import sys
import threading
import time
from collections import Counter, defaultdict
from functools import wraps

from PIL import Image, ImageDraw, ImageFont

from src.services import stickman_renderer as sr
from src.services.scene_composition import resolve_text_placement
from src.services.stickman_renderer import StickmanRenderer

TEXT_PATH_METHODS = (
    '_draw_text_elements',
    '_draw_caption_overlay',
    '_draw_text_lines_on_frame',
    '_decorate_classroom_board',
)

TEXT_CODE_NAMES = (
    'StickmanRenderer._draw_text_elements',
    'StickmanRenderer._draw_caption_overlay',
    'StickmanRenderer._draw_text_lines_on_frame',
    'StickmanRenderer._decorate_classroom_board',
    'StickmanRenderer._load_font',
    'StickmanRenderer._chalk_color',
    'StickmanRenderer._blit_span',
    'module._text_opacity',
    'module.resolve_text_placement',
)

_BPP = {'1': 1, 'L': 1, 'P': 1, 'RGB': 3, 'RGBA': 4, 'LA': 2, 'CMYK': 4, 'I': 4, 'F': 4}


def _bpp(mode: str) -> int:
    return _BPP.get(str(mode).upper(), 0)


def text_code_objects() -> dict:
    """Resolve the text-path code objects that exist in this build."""
    resolved: dict = {}
    for name in TEXT_CODE_NAMES:
        if name == 'module._text_opacity':
            owner, attr = sr, '_text_opacity'
        elif name == 'module.resolve_text_placement':
            owner, attr = sr, 'resolve_text_placement'
        else:
            owner, attr = StickmanRenderer, name.split('.', 1)[1]
        code = getattr(getattr(owner, attr, None), '__code__', None)
        if code is not None:
            resolved[name] = code
    return resolved


def source_lines(module_file: str) -> dict:
    with open(module_file, 'r', encoding='utf-8') as handle:
        return {i: line.rstrip('\n') for i, line in enumerate(handle, start=1)}


class TextLineProbe:
    """Per-source-line self timings for the text path (sys.monitoring)."""

    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.mon = sys.monitoring
        self.tool_id = self.mon.PROFILER_ID
        self.codes = text_code_objects()
        self.calls: Counter = Counter()
        self.line_seconds: defaultdict = defaultdict(float)
        self.line_hits: Counter = Counter()
        self.errors = 0
        self._local = threading.local()
        self.installed = False

    def _stack(self) -> list:
        stack = getattr(self._local, 'stack', None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    def _on_line(self, code, line_number):
        try:
            stack = self._stack()
            if not stack:
                return
            frame = stack[-1]
            if frame[0] is not code:
                return
            now = self.clock()
            if frame[2] is not None:
                own = (now - frame[3]) - frame[4]
                if own > 0.0:
                    self.line_seconds[(frame[1], frame[2])] += own
                    self.line_hits[(frame[1], frame[2])] += 1
            frame[3] = now
            frame[4] = 0.0
            frame[2] = line_number
        except Exception:  # pragma: no cover - never break the render
            self.errors += 1

    def _on_start(self, code, instruction_offset):
        try:
            name = self.codes.get(code)
            if name is None:
                return
            now = self.clock()
            self.calls[name] += 1
            self._stack().append([code, name, None, now, 0.0, now])
        except Exception:  # pragma: no cover
            self.errors += 1

    def _on_return(self, code, instruction_offset, retval):
        try:
            stack = self._stack()
            if not stack:
                return
            frame = stack.pop()
            if frame[0] is not code:
                return
            now = self.clock()
            if frame[2] is not None:
                own = (now - frame[3]) - frame[4]
                if own > 0.0:
                    self.line_seconds[(frame[1], frame[2])] += own
            if stack:
                stack[-1][4] += now - frame[5]
        except Exception:  # pragma: no cover
            self.errors += 1

    def install(self):
        self.mon.use_tool_id(self.tool_id, 'day22_text_lines')
        self.mon.register_callback(self.tool_id, self.mon.events.LINE, self._on_line)
        self.mon.register_callback(self.tool_id, self.mon.events.PY_START, self._on_start)
        self.mon.register_callback(self.tool_id, self.mon.events.PY_RETURN, self._on_return)
        self.mon.set_events(self.tool_id, self.mon.events.NO_EVENTS)
        events = (self.mon.events.LINE | self.mon.events.PY_START
                  | self.mon.events.PY_RETURN)
        for code in self.codes.values():
            self.mon.set_local_events(self.tool_id, code, events)
        self.installed = True
        return self

    def close(self):
        if not self.installed:
            return
        for code in self.codes.values():
            self.mon.set_local_events(self.tool_id, code, self.mon.events.NO_EVENTS)
        self.mon.register_callback(self.tool_id, self.mon.events.LINE, None)
        self.mon.register_callback(self.tool_id, self.mon.events.PY_START, None)
        self.mon.register_callback(self.tool_id, self.mon.events.PY_RETURN, None)
        self.mon.free_tool_id(self.tool_id)
        self.installed = False

    def snapshot(self) -> dict:
        by_function: dict = {}
        for (name, line), seconds in self.line_seconds.items():
            entry = by_function.setdefault(name, {'total': 0.0, 'lines': {}})
            entry['total'] += seconds
            hits = self.line_hits[(name, line)]
            entry['lines'][str(line)] = {
                'seconds': seconds,
                'hits': hits,
                'avg_seconds': seconds / hits if hits else 0.0,
            }
        for name, code in self.codes.items():
            entry = by_function.setdefault(name, {'total': 0.0, 'lines': {}})
            entry['calls'] = self.calls[name]
            entry['avg_seconds'] = (entry['total'] / self.calls[name]
                                    if self.calls[name] else 0.0)
            entry['firstlineno'] = code.co_firstlineno
            entry['filename'] = code.co_filename
            entry['lines_attributed'] = len(entry['lines'])
        return {
            'tool': 'sys.monitoring local LINE/PY_START/PY_RETURN',
            'python': sys.version,
            'callback_errors': self.errors,
            'functions': by_function,
        }


class TextPathProbe:
    """Counts, timings, bytes and repetition keys for the renderer text path."""

    def __init__(self, clock=time.perf_counter, hash_bitmaps: bool = True):
        self.clock = clock
        self.hash_bitmaps = hash_bitmaps
        self.restore: list = []
        self.ops: dict = {}
        self.path_stack: list = []
        self.renderer_calls: Counter = Counter()
        self.current_scene = None
        self.frame_index = 0
        self.calls: list = []
        self._call_stack: list = []
        self.text_ops: list = []
        self.textlength_keys: Counter = Counter()
        self.textlength_calls = 0
        self.font_keys: Counter = Counter()
        self.font_paths: Counter = Counter()
        self.font_sizes: Counter = Counter()
        self.font_load_calls = 0
        self.font_truetype_calls = 0
        self.font_default_calls = 0
        self.bitmap_keys: dict = {}
        self.bitmap_calls = 0
        self.bitmap_hashed = 0
        self.bitmap_errors = 0
        self.scene_markers: dict = {}
        self._in_bitmap = False

    # -- helpers ---------------------------------------------------------
    def _record(self, name: str, seconds: float, nbytes: int = 0) -> None:
        entry = self.ops.get(name)
        if entry is None:
            entry = self.ops[name] = {'calls': 0, 'seconds': 0.0, 'bytes': 0,
                                      'contexts': Counter()}
        entry['calls'] += 1
        entry['seconds'] += seconds
        entry['bytes'] += nbytes
        entry['contexts'][self.context()] += 1

    def context(self) -> str:
        if self.path_stack:
            return 'text:' + self.path_stack[-1]
        return 'other'

    def _wrap(self, cls, name: str, factory) -> None:
        descriptor = inspect.getattr_static(cls, name)
        original = getattr(cls, name)
        measured = factory(original)
        setattr(cls, name, staticmethod(measured) if isinstance(descriptor, staticmethod)
                else measured)
        self.restore.append((cls, name, descriptor))

    def _wrap_module(self, module, name: str, factory) -> None:
        original = getattr(module, name)
        setattr(module, name, factory(original))
        self.restore.append((module, name, original))

    def install(self):
        for method in TEXT_PATH_METHODS:
            self._wrap(StickmanRenderer, method, self._renderer_factory(method))
        self._wrap(ImageDraw.ImageDraw, 'text', self._draw_text_factory)
        self._wrap(ImageDraw.ImageDraw, 'textlength', self._textlength_factory)
        self._wrap(ImageDraw.ImageDraw, 'textbbox', self._textbbox_factory)
        self._wrap(ImageDraw.ImageDraw, 'rectangle', self._rectangle_factory)
        self._wrap(Image.Image, 'tobytes', self._image_buf_factory('Image.Image.tobytes'))
        self._wrap(Image.Image, 'convert', self._image_buf_factory('Image.Image.convert'))
        self._wrap(Image.Image, 'copy', self._image_buf_factory('Image.Image.copy'))
        self._wrap(Image.Image, 'crop', self._crop_factory)
        self._wrap(Image.Image, 'paste', self._paste_factory)
        self._wrap_module(Image, 'frombytes', self._frombytes_factory)
        self._wrap_module(Image, 'new', self._new_factory)
        self._wrap_module(Image, 'alpha_composite', self._alpha_composite_factory)
        self._wrap(StickmanRenderer, '_load_font', self._load_font_factory)
        return self

    def close(self):
        for owner, name, descriptor in reversed(self.restore):
            setattr(owner, name, descriptor)
        self.restore.clear()


# -- renderer method context ----------------------------------------
    def _renderer_factory(self, method: str):
        def factory(original):
            @wraps(original)
            def measured(self_renderer, *args, **kwargs):
                self.renderer_calls[method] += 1
                self.path_stack.append(method)
                call = None
                if method == '_draw_text_elements':
                    call = self._open_text_call(args, kwargs)
                try:
                    return original(self_renderer, *args, **kwargs)
                finally:
                    self.path_stack.pop()
                    if call is not None:
                        self._close_text_call(call)
            return measured
        return factory

    def _open_text_call(self, args, kwargs) -> dict:
        self.frame_index += 1
        state = None
        t = duration = width = height = None
        if len(args) >= 6:
            _frame, width, height, state, t, duration = args[:6]
        else:  # pragma: no cover - defensive
            state = kwargs.get('state')
        specs = list((state or {}).get('text_specs') or [])
        call = {
            'scene': self.current_scene,
            'frame_index': self.frame_index,
            't': t,
            'duration': duration,
            'width': width,
            'height': height,
            'n_specs': len(specs),
            'specs': [self._spec_snapshot(spec) for spec in specs],
            'board_hosted': sorted((state or {}).get('_board_hosted') or []),
            'n_blocked_rects': len((state or {}).get('blocked_rects') or []),
            'op_counts': Counter(),
            'blocks': [],
            'textlength_calls': 0,
            'crop': None,
            'paste': [],
            'start': self.clock(),
        }
        self._call_stack.append(call)
        return call

    def _close_text_call(self, call: dict) -> None:
        call['seconds'] = self.clock() - call.pop('start')
        if self._call_stack and self._call_stack[-1] is call:
            self._call_stack.pop()
        call['op_counts'] = dict(call['op_counts'])
        self.calls.append(call)

    @staticmethod
    def _spec_snapshot(spec: dict) -> dict:
        return {
            'text': str(spec.get('text', '')),
            'size': str(spec.get('size', 'normal')),
            'color': list(spec.get('color', (255, 255, 255))),
            'anchor': str(spec.get('anchor', 'center')),
            'x': spec.get('x', 0.5),
            'y': spec.get('y', 0.9),
            'opacity': spec.get('opacity', 1.0),
            'appear_at': spec.get('appear_at', 0.0),
            'fade_in': spec.get('fade_in', 0.0),
            'fade_out': spec.get('fade_out', 0.0),
            'duration': spec.get('duration', 0.0),
            'max_width': spec.get('max_width', 0.8),
        }

    def _current_call(self):
        return self._call_stack[-1] if self._call_stack else None


    # -- ImageDraw wrappers ----------------------------------------------
    @property
    def _draw_text_factory(self):
        def factory(original):
            @wraps(original)
            def measured(self_draw, xy, text, *args, **kwargs):
                start = self.clock()
                try:
                    return original(self_draw, xy, text, *args, **kwargs)
                finally:
                    seconds = self.clock() - start
                    fill = kwargs.get('fill')
                    if fill is None and args:
                        fill = args[0]
                    font = kwargs.get('font')
                    if font is None and len(args) > 1:
                        font = args[1]
                    px = getattr(font, 'size', None)
                    path = str(getattr(font, 'path', ''))
                    key = (str(text), px, path,
                           tuple(fill) if isinstance(fill, (tuple, list)) else fill)
                    self._record('ImageDraw.text', seconds)
                    self.bitmap_calls += 1
                    self.text_ops.append({
                        'scene': self.current_scene,
                        'frame_index': self.frame_index,
                        'context': self.context(),
                        'text': str(text),
                        'x': xy[0] if isinstance(xy, (tuple, list)) else xy,
                        'y': xy[1] if isinstance(xy, (tuple, list)) else None,
                        'px_size': px,
                        'font_path': path,
                        'fill': list(fill) if isinstance(fill, (tuple, list)) else fill,
                        'key': key,
                        'seconds': seconds,
                    })
                    call = self._current_call()
                    if call is not None:
                        call['op_counts']['text'] += 1
                    if self.hash_bitmaps and self.context().startswith('text:'):
                        self._hash_bitmap(key, text, font, fill)
            return measured
        return factory

    def _hash_bitmap(self, key, text, font, fill) -> None:
        """Hash the standalone glyph bitmap for one rendered style unit."""
        if key in self.bitmap_keys or self._in_bitmap:
            return
        try:
            self._in_bitmap = True
            probe = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
            try:
                bbox = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
            except Exception:
                bbox = None
            if bbox is None:
                px = getattr(font, 'size', None) or 10
                width = max(1, int(len(str(text)) * px * 0.7))
                height = max(1, int(px * 1.4))
            else:
                width = max(1, bbox[2] - bbox[0])
                height = max(1, bbox[3] - bbox[1])
                offset = (-bbox[0], -bbox[1])
            bitmap = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            ImageDraw.Draw(bitmap).text((offset[0], offset[1]), text, fill=fill, font=font)
            payload = bitmap.tobytes()
            self.bitmap_keys[key] = {
                'w': width, 'h': height, 'bytes': len(payload),
                'sha256': hashlib.sha256(payload).hexdigest(),
            }
            self.bitmap_hashed += 1
        except Exception:
            self.bitmap_errors += 1
        finally:
            self._in_bitmap = False

    # -- PIL buffer wrappers ----------------------------------------------
    def _image_buf_factory(self, name: str):
        def factory(original):
            @wraps(original)
            def measured(*args, **kwargs):
                start = self.clock()
                try:
                    result = original(*args, **kwargs)
                    nbytes = 0
                    mode = getattr(result, 'mode', None)
                    size = getattr(result, 'size', None)
                    if mode is not None and size is not None:
                        nbytes = _bpp(mode) * size[0] * size[1]
                    if name == 'Image.Image.tobytes' and result is not None:
                        try:
                            nbytes = max(nbytes, len(result))
                        except Exception:
                            pass
                except Exception:
                    result = None
                    nbytes = 0
                finally:
                    seconds = self.clock() - start
                    self._record(name, seconds, nbytes)
                    call = self._current_call()
                    if call is not None:
                        call['op_counts'][name] = call['op_counts'].get(name, 0) + 1
                return result
            return measured
        return factory

    def _crop_factory(self, original):
        @wraps(original)
        def measured(self_img, box, *args, **kwargs):
            start = self.clock()
            try:
                return original(self_img, box, *args, **kwargs)
            finally:
                seconds = self.clock() - start
                nbytes = 0
                try:
                    mode = getattr(self_img, 'mode', None)
                    size = getattr(self_img, 'size', None)
                    if mode is not None and size is not None:
                        nbytes = _bpp(mode) * size[0] * size[1]
                except Exception:
                    pass
                self._record('Image.Image.crop', seconds, nbytes)
                call = self._current_call()
                if call is not None:
                    call['op_counts']['Image.Image.crop'] = call['op_counts'].get('Image.Image.crop', 0) + 1
            return measured
        return measured

    def _paste_factory(self, original):
        @wraps(original)
        def measured(self_img, im, box=None, mask=None):
            start = self.clock()
            try:
                return original(self_img, im, box=box, mask=mask)
            finally:
                seconds = self.clock() - start
                nbytes = 0
                try:
                    mode = getattr(im, 'mode', None)
                    size = getattr(im, 'size', None)
                    if mode is not None and size is not None:
                        nbytes = _bpp(mode) * size[0] * size[1]
                except Exception:
                    pass
                self._record('Image.Image.paste', seconds, nbytes)
                call = self._current_call()
                if call is not None:
                    call['op_counts']['Image.Image.paste'] = call['op_counts'].get('Image.Image.paste', 0) + 1
            return measured
        return measured

    def _frombytes_factory(self, original):
        @wraps(original)
        def measured(mode, size, data, *args, **kwargs):
            start = self.clock()
            try:
                return original(mode, size, data, *args, **kwargs)
            finally:
                seconds = self.clock() - start
                nbytes = len(data) if isinstance(data, (bytes, bytearray)) else 0
                self._record('Image.frombytes', seconds, nbytes)
                call = self._current_call()
                if call is not None:
                                        call['op_counts']['Image.frombytes'] = call['op_counts'].get('Image.frombytes', 0) + 1
        return measured

    def _new_factory(self, original):
        @wraps(original)
        def measured(mode, size, *args, **kwargs):
            start = self.clock()
            try:
                result = original(mode, size, *args, **kwargs)
            finally:
                seconds = self.clock() - start
                nbytes = _bpp(mode) * size[0] * size[1]
                self._record('Image.new', seconds, nbytes)
                call = self._current_call()
                if call is not None:
                    call['op_counts']['Image.new'] = call['op_counts'].get('Image.new', 0) + 1
            return result
        return measured

    def _alpha_composite_factory(self, original):
        @wraps(original)
        def measured(im1, im2):
            start = self.clock()
            nbytes = 0
            try:
                mode = getattr(im1, 'mode', None)
                size = getattr(im1, 'size', None)
                if mode is not None and size is not None:
                    nbytes = _bpp(mode) * size[0] * size[1]
            except Exception:
                pass
            try:
                return original(im1, im2)
            finally:
                seconds = self.clock() - start
                self._record('Image.alpha_composite', seconds, nbytes)
                call = self._current_call()
                if call is not None:
                    call['op_counts']['Image.alpha_composite'] = call['op_counts'].get('Image.alpha_composite', 0) + 1
        return measured

    def _textlength_factory(self, original):
        @wraps(original)
        def measured(self_draw, text, font=None, *args, **kwargs):
            start = self.clock()
            try:
                result = original(self_draw, text, font=font, *args, **kwargs)
            finally:
                seconds = self.clock() - start
                self.textlength_calls += 1
                key = (str(text),
                       str(getattr(font, 'size', None)),
                       str(getattr(font, 'path', '')))
                self.textlength_keys[key] += 1
                self._record('ImageDraw.textlength', seconds)
                call = self._current_call()
                if call is not None:
                    call['textlength_calls'] += 1
            return result
        return measured

    def _textbbox_factory(self, original):
        @wraps(original)
        def measured(self_draw, xy, text, font=None, *args, **kwargs):
            start = self.clock()
            try:
                return original(self_draw, xy, text, font=font, *args, **kwargs)
            finally:
                seconds = self.clock() - start
                self._record('ImageDraw.textbbox', seconds)
                call = self._current_call()
                if call is not None:
                    call['op_counts']['ImageDraw.textbbox'] = call['op_counts'].get('ImageDraw.textbbox', 0) + 1
        return measured

    def _rectangle_factory(self, original):
        @wraps(original)
        def measured(self_draw, xy, fill=None, outline=None, width=0):
            start = self.clock()
            try:
                return original(self_draw, xy, fill=fill, outline=outline, width=width)
            finally:
                seconds = self.clock() - start
                self._record('ImageDraw.rectangle', seconds)
                call = self._current_call()
                if call is not None:
                    call['op_counts']['ImageDraw.rectangle'] = call['op_counts'].get('ImageDraw.rectangle', 0) + 1
        return measured

    def _load_font_factory(self, original):
        @wraps(original)
        def measured(self_renderer, *args, **kwargs):
            start = self.clock()
            try:
                result = original(self_renderer, *args, **kwargs)
            finally:
                seconds = self.clock() - start
                self.font_load_calls += 1
                # _load_font is a @staticmethod(px_size). When invoked as
                # self._load_font(px_size) the staticmethod descriptor delivers
                # px_size as the first positional arg (bound to the
                # `self_renderer` slot), leaving `*args` empty. Recover px_size
                # from whichever slot holds it.
                px_size = args[0] if args else self_renderer
                try:
                    px_size_key = int(px_size)
                except Exception:
                    px_size_key = px_size
                self.font_sizes[px_size_key] += 1
                key = ('px_size', px_size_key)
                self.font_keys[key] += 1
                self._record('_load_font', seconds)
            return result
        return measured


    def scene(self, scene):
        self.current_scene = scene
        self.scene_markers[scene] = self.clock()


# -- bitmap hash routine callable from text_op wrappers --------------
def _probe_bitmap_for_text(text, font, fill):
    """Standalone glyph-bitmap probe without touching the live probe instance."""
    try:
        probe = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
        try:
            bbox = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
        except Exception:
            bbox = None
        if bbox is None:
            px = getattr(font, 'size', None) or 10
            width = max(1, int(len(str(text)) * px * 0.7))
            height = max(1, int(px * 1.4))
            offset = (0, 0)
        else:
            width = max(1, bbox[2] - bbox[0])
            height = max(1, bbox[3] - bbox[1])
            offset = (-bbox[0], -bbox[1])
        bitmap = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(bitmap).text(offset, text, fill=fill, font=font)
        payload = bitmap.tobytes()
        return {
            'w': width, 'h': height, 'bytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
        }
    except Exception:
        return None


# END_OF_FILE