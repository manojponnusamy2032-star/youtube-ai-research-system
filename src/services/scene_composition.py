"""Scene composition abstraction for the procedural video renderer.

Provides a clean data model for describing what appears in a scene so that
layout (characters, objects, environment, text, camera, effects) is no longer
mixed directly into the renderer's frame-generation logic.

All coordinates are *normalized* (0.0--1.0) unless otherwise noted, keeping
scene descriptions resolution-independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Re-usable vocabulary constants
# ---------------------------------------------------------------------------

SUPPORTED_POSES = {
    "idle", "walk", "run", "point", "wave", "jump", "talk", "surprised",
}

SUPPORTED_EMOTIONS = {
    "neutral", "happy", "frustrated", "focused", "surprised", "sad", "excited",
}

SUPPORTED_OBJECT_TYPES = {
    "book", "stack_of_books", "desk", "chair", "clock", "phone", "laptop",
    "light_bulb", "arrow", "check_mark", "cross_mark", "graph", "screen",
    "folder", "document", "brain", "thought_bubble", "calendar", "timer",
    "notebook", "pen", "box",
}

SUPPORTED_ENVIRONMENTS = {
    "default", "bedroom", "study_desk", "office", "classroom",
    "workspace", "abstract_info_space",
}

SUPPORTED_EFFECTS = {
    "highlight", "spotlight", "glow", "pulse", "shake", "scale_up",
    "fade", "reveal", "circle_highlight",
}

SUPPORTED_CAMERA_PATTERNS = {
    "static", "slow_zoom_in", "slow_zoom_out",
    "pan_left", "pan_right", "pan_up", "pan_down",
    "zoom_then_pan", "focus_on_character", "focus_on_object",
}

# Emotion -> (tint color); the renderer blends these into character color.
EMOTION_TINTS: dict[str, tuple[int, int, int]] = {
    "neutral": (255, 255, 255),       # white
    "happy": (100, 255, 100),         # greenish -- energy
    "frustrated": (255, 100, 100),    # reddish -- tension
    "focused": (100, 220, 255),       # cyan -- attention
    "surprised": (255, 255, 100),     # yellow -- shock
    "sad": (120, 120, 255),           # blue -- melancholy
    "excited": (255, 165, 0),         # orange -- enthusiasm
}

SAFE_MARGIN_RATIO = 0.08  # 8% inset on each side for mobile-safe text


def resolve_text_placement(
    nx: float,
    ny: float,
    block_w: float,
    block_h: float,
    width: int,
    height: int,
    blocked_rects: list[tuple[int, int, int, int]] | None = None,
    anchor: str = "center",
) -> tuple[int, int]:
    """Resolve a text block's top-left pixel position.

    Enforces the mobile-safe margin and, since V1.2.1, avoids any blocked
    screen rect (environment decor such as boards/windows, registered by the
    renderer in screen pixels) by shifting the block to the nearest free band
    above/below the obstacle. Falls back to the safe-clamped original
    position when no free band exists.
    """
    margin_x = int(width * SAFE_MARGIN_RATIO)
    margin_y = int(height * SAFE_MARGIN_RATIO)
    bw, bh = int(block_w), int(block_h)
    if anchor == "left":
        x0 = margin_x
    elif anchor == "right":
        x0 = width - margin_x - bw
    else:
        x0 = int(float(nx) * width - bw / 2)
    x0 = max(margin_x, min(x0, width - margin_x - bw))
    y_base = int(float(ny) * height - bh / 2)
    y0 = max(margin_y, min(y_base, height - margin_y - bh))
    rects = [tuple(r) for r in (blocked_rects or [])]
    if not rects:
        return x0, y0

    def _hits(y: int) -> list[tuple[int, int, int, int]]:
        return [
            r for r in rects
            if x0 < r[2] and x0 + bw > r[0] and y < r[3] and y + bh > r[1]
        ]

    if not _hits(y0):
        return x0, y0
    gap = max(4, margin_y // 3)
    candidates: list[int] = []
    for rect in _hits(y0):
        candidates.append(int(rect[3]) + gap)        # below the obstacle
        candidates.append(int(rect[1]) - bh - gap)   # above the obstacle
    valid = [
        c for c in candidates
        if margin_y <= c <= height - margin_y - bh and not _hits(c)
    ]
    if valid:
        y0 = min(valid, key=lambda c: abs(c - y_base))
    return x0, y0


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------

@dataclass
class CharacterSpec:
    """A single character described in normalized coordinates."""

    name: str = "character"
    pose: str = "idle"
    emotion: str = "neutral"
    x: float = 0.5          # normalized horizontal (0 = left, 1 = right)
    y: float = 0.75         # normalized vertical (0 = top, 1 = bottom)
    scale: float = 1.0      # relative to a "standard" character
    color: tuple[int, int, int] = (255, 255, 255)
    visible: bool = True

    def __post_init__(self) -> None:
        self.name = str(self.name).strip() or "character"
        self.pose = str(self.pose).strip().lower() or "idle"
        if self.pose not in SUPPORTED_POSES:
            self.pose = "idle"
        self.emotion = str(self.emotion).strip().lower() or "neutral"
        if self.emotion not in SUPPORTED_EMOTIONS:
            self.emotion = "neutral"
        self.x = max(0.0, min(1.0, float(self.x)))
        self.y = max(0.0, min(1.0, float(self.y)))
        self.scale = max(0.1, min(3.0, float(self.scale)))

    @property
    def effective_color(self) -> tuple[int, int, int]:
        """Return the emotion-adjusted color for this character."""
        tint = EMOTION_TINTS.get(self.emotion)
        if tint is None:
            return self.color
        # Blend the emotion tint with the base color at 25%.
        r, g, b = self.color
        tr, tg, tb = tint
        return (
            int(r * 0.75 + tr * 0.25),
            int(g * 0.75 + tg * 0.25),
            int(b * 0.75 + tb * 0.25),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pose": self.pose,
            "emotion": self.emotion,
            "x": self.x,
            "y": self.y,
            "scale": self.scale,
            "color": self.color,
                        "visible": self.visible,
        }


# ---------------------------------------------------------------------------
# Object
# ---------------------------------------------------------------------------

@dataclass
class ObjectSpec:
    """A procedural object positioned in normalized coordinates."""

    name: str = "object"
    type: str = "generic"
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    rotation: float = 0.0   # degrees
    opacity: float = 1.0
    visible: bool = True
    color: tuple[int, int, int] = (200, 150, 80)

    def __post_init__(self) -> None:
        self.name = str(self.name).strip() or "object"
        self.type = str(self.type).strip().lower() or "generic"
        self.x = max(0.0, min(1.0, float(self.x)))
        self.y = max(0.0, min(1.0, float(self.y)))
        self.scale = max(0.0, float(self.scale))
        self.opacity = max(0.0, min(1.0, float(self.opacity)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "scale": self.scale,
            "rotation": self.rotation,
            "opacity": self.opacity,
            "visible": self.visible,
                        "color": self.color,
        }


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

@dataclass
class EnvironmentSpec:
    """Procedural environment definition."""

    type: str = "default"
    background_color: tuple[int, int, int] = (173, 216, 230)   # sky blue
    ground_color: tuple[int, int, int] = (60, 140, 60)         # grass
    ground_y: float = 0.75     # normalized Y where ground starts
    accent_color: tuple[int, int, int] = (255, 223, 100)       # warm accent
    show_grid: bool = False
    furniture: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.type = str(self.type).strip().lower() or "default"
        if self.type not in SUPPORTED_ENVIRONMENTS:
            self.type = "default"
        self.ground_y = max(0.5, min(0.95, float(self.ground_y)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "background_color": self.background_color,
            "ground_color": self.ground_color,
            "ground_y": self.ground_y,
            "accent_color": self.accent_color,
            "show_grid": self.show_grid,
                        "furniture": self.furniture,
        }


# ---------------------------------------------------------------------------
# Text / caption
# ---------------------------------------------------------------------------

@dataclass
class TextSpec:
    """A structured on-screen text element with animation support."""

    text: str = ""
    x: float = 0.5          # normalized -- 0 = left, 1 = right
    y: float = 0.9          # normalized -- 0 = top, 1 = bottom
    size: str = "normal"    # small, normal, large, headline
    color: tuple[int, int, int] = (255, 255, 255)
    opacity: float = 1.0
    style: str = "normal"   # normal, bold, emphasized
    anchor: str = "center"  # left, center, right
    max_width: float = 0.8  # normalized -- maximum text width
    fade_in: float = 0.0    # seconds to fade in
    fade_out: float = 0.0   # seconds to fade out
    appear_at: float = 0.0  # time when text becomes visible
    duration: float = 0.0   # 0 = visible for whole scene

    def __post_init__(self) -> None:
        self.text = str(self.text)
        self.size = str(self.size).strip().lower() or "normal"
        if self.size not in {"small", "normal", "large", "headline"}:
            self.size = "normal"
        self.style = str(self.style).strip().lower() or "normal"
        self.anchor = str(self.anchor).strip().lower() or "center"
        if self.anchor not in {"left", "center", "right"}:
            self.anchor = "center"
        self.x = max(0.0, min(1.0, float(self.x)))
        self.y = max(0.0, min(1.0, float(self.y)))
        self.opacity = max(0.0, min(1.0, float(self.opacity)))

    @property
    def scale_factor(self) -> float:
        return {
            "small": 0.7,
            "normal": 1.0,
            "large": 1.4,
            "headline": 2.0,
        }.get(self.size, 1.0)

    def effective_opacity(self, t: float, scene_duration: float) -> float:
        """Compute time-dependent opacity respecting fade-in/out."""
        if t < self.appear_at:
            return 0.0
        opacity = self.opacity
        # Fade in
        if self.fade_in > 0:
            local = (t - self.appear_at) / self.fade_in
            opacity *= max(0.0, min(1.0, local))
        # Fade out
        end_time = self.appear_at + self.duration if self.duration > 0 else scene_duration
        if self.fade_out > 0 and t > end_time - self.fade_out:
            fade_progress = (end_time - t) / self.fade_out
            opacity *= max(0.0, min(1.0, fade_progress))
        return opacity

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "size": self.size,
            "color": self.color,
            "opacity": self.opacity,
            "style": self.style,
            "anchor": self.anchor,
            "max_width": self.max_width,
            "fade_in": self.fade_in,
            "fade_out": self.fade_out,
            "appear_at": self.appear_at,
                        "duration": self.duration,
        }


# ---------------------------------------------------------------------------
# Visual effects / emphasis
# ---------------------------------------------------------------------------

@dataclass
class EffectSpec:
    """A procedural visual effect (highlight, spotlight, glow, etc.)."""

    type: str = "highlight"
    target: str = "scene"
    start: float = 0.0
    duration: float = 1.0
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.type = str(self.type).strip().lower() or "highlight"
        if self.type not in SUPPORTED_EFFECTS:
            self.type = "highlight"
        self.target = str(self.target).strip().lower() or "scene"
        self.start = max(0.0, float(self.start))
        self.duration = max(0.0, float(self.duration))

    def is_active(self, t: float) -> bool:
        return self.start <= t <= self.start + self.duration

    def progress(self, t: float) -> float:
        """Normalized progress 0->1 within the effect (ease-out curve)."""
        if self.duration <= 0:
            return 1.0 if self.is_active(t) else 0.0
        raw = max(0.0, min(1.0, (t - self.start) / self.duration))
        return 1.0 - (1.0 - raw) * (1.0 - raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "start": self.start,
            "duration": self.duration,
                        "parameters": self.parameters,
        }


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

@dataclass
class CameraSpec:
    """Camera movement specification with start/end states, duration and easing."""

    pattern: str = "static"
    focus_target: str | None = None  # name of character or object
    start_state: dict[str, Any] = field(default_factory=dict)
    end_state: dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0
    easing: str = "ease_in_out"

    def __post_init__(self) -> None:
        self.pattern = str(self.pattern).strip().lower() or "static"
        if self.pattern not in SUPPORTED_CAMERA_PATTERNS:
            self.pattern = "static"
        self.easing = str(self.easing).strip().lower() or "ease_in_out"
        if self.easing not in {"linear", "ease_in", "ease_out", "ease_in_out"}:
            self.easing = "ease_in_out"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "focus_target": self.focus_target,
            "start_state": self.start_state,
            "end_state": self.end_state,
            "duration": self.duration,
            "easing": self.easing,
        }


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

@dataclass
class SceneComposition:
    """High-level composition for a single rendered scene.

    This is the bridge between the declarative ``VisualScene`` and the
    imperative ``StickmanRenderer``.  It keeps the renderer focused on
    *drawing* while the composition layer owns *what to draw*.
    """

    environment: EnvironmentSpec | None = None
    characters: list[CharacterSpec] = field(default_factory=list)
    objects: list[ObjectSpec] = field(default_factory=list)
    text_elements: list[TextSpec] = field(default_factory=list)
    effects: list[EffectSpec] = field(default_factory=list)
    camera: CameraSpec | None = None

    @classmethod
    def from_visual_description(cls, desc: dict[str, Any] | None) -> SceneComposition:
        """Build a composition from a plain dict (e.g. from RenderJobSpec)."""
        if not desc:
            return cls()

        env = desc.get("environment")
        env_spec = EnvironmentSpec(**env) if isinstance(env, dict) else None

        characters: list[CharacterSpec] = []
        for c in desc.get("characters", []):
            if isinstance(c, dict):
                characters.append(CharacterSpec(**c))
            elif isinstance(c, CharacterSpec):
                characters.append(c)

        objects: list[ObjectSpec] = []
        for o in desc.get("objects", []):
            if isinstance(o, dict):
                objects.append(ObjectSpec(**o))
            elif isinstance(o, ObjectSpec):
                objects.append(o)

        text_elements: list[TextSpec] = []
        for t in desc.get("text_elements", []):
            if isinstance(t, dict):
                text_elements.append(TextSpec(**t))
            elif isinstance(t, TextSpec):
                text_elements.append(t)

        effects: list[EffectSpec] = []
        for e in desc.get("effects", []):
            if isinstance(e, dict):
                effects.append(EffectSpec(**e))
            elif isinstance(e, EffectSpec):
                effects.append(e)

        cam = desc.get("camera")
        camera_spec = CameraSpec(**cam) if isinstance(cam, dict) else None

        return cls(
            environment=env_spec,
            characters=characters,
            objects=objects,
            text_elements=text_elements,
            effects=effects,
            camera=camera_spec,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a plain dict."""
        result: dict[str, Any] = {}
        if self.environment:
            result["environment"] = self.environment.to_dict()
        result["characters"] = [c.to_dict() for c in self.characters]
        result["objects"] = [o.to_dict() for o in self.objects]
        result["text_elements"] = [t.to_dict() for t in self.text_elements]
        result["effects"] = [e.to_dict() for e in self.effects]
        if self.camera:
            result["camera"] = self.camera.to_dict()
        return result

