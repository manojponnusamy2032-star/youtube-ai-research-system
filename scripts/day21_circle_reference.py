"""Frozen pre-Day-21 circle algorithm for pixel-equivalence evidence.

Copied verbatim from StickmanRenderer._draw_circle before the Day-21 opaque
span fast path. The unchanged _blend_pixel / _blit_span implementations are
inherited from the production renderer.
"""
from __future__ import annotations

import math

from src.services.stickman_renderer import StickmanRenderer


class OriginalCircleRenderer(StickmanRenderer):
    def _draw_circle(
        self,
        frame: bytearray,
        width: int,
        height: int,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
        opacity: float = 1.0,
    ) -> None:
        """Draw a filled circle using midpoint circle algorithm."""
        r, g, b = color
        cx, cy, radius = int(cx), int(cy), int(radius)
        cx = max(0, min(cx, width - 1))
        cy = max(0, min(cy, height - 1))
        radius = max(1, radius)
        opacity = max(0.0, min(1.0, opacity))

        # Bounding box
        x_min = max(0, cx - radius)
        x_max = min(width - 1, cx + radius)
        y_min = max(0, cy - radius)
        y_max = min(height - 1, cy + radius)

        r_squared = radius * radius

        for y in range(y_min, y_max + 1):
            dy = y - cy
            dy_squared = dy * dy
            # Calculate x range for this y
            dx_max = int(math.sqrt(max(0, r_squared - dy_squared)))
            x_start = max(x_min, cx - dx_max)
            x_end = min(x_max, cx + dx_max)

            base = y * width * 3 + x_start * 3
            for x in range(x_start, x_end + 1):
                idx = base + (x - x_start) * 3
                self._blend_pixel(frame, idx, (r, g, b), opacity)
