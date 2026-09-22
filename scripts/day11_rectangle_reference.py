"""Frozen pre-Day-11 rectangle algorithm for pixel-equivalence evidence.

Copied from StickmanRenderer._draw_rect before optimization. The unchanged
_blend_pixel implementation is inherited from the production renderer.
"""
from src.services.stickman_renderer import StickmanRenderer


class OriginalRectangleRenderer(StickmanRenderer):
    def _draw_rect(
        self,
        frame: bytearray,
        width: int,
        height: int,
        x: int,
        y: int,
        w: int,
        h: int,
        color: tuple[int, int, int],
        opacity: float = 1.0,
    ) -> None:
        """Draw a filled rectangle."""
        r, g, b = color
        x, y, w, h = int(x), int(y), int(w), int(h)
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(0, min(w, width - x))
        h = max(0, min(h, height - y))
        opacity = max(0.0, min(1.0, opacity))

        for row in range(y, y + h):
            base = row * width * 3 + x * 3
            for col in range(w):
                idx = base + col * 3
                self._blend_pixel(frame, idx, (r, g, b), opacity)
