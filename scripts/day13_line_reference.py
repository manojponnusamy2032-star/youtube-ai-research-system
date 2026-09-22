"""Frozen pre-Day-13 line algorithm for pixel-equivalence evidence.

Copied verbatim from StickmanRenderer._draw_line before the off-screen
thickness-stamp optimization. The unchanged _blend_pixel implementation is
inherited from the production renderer.
"""
from src.services.stickman_renderer import StickmanRenderer


class OriginalLineRenderer(StickmanRenderer):
    def _draw_line(
        self,
        frame: bytearray,
        width: int,
        height: int,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: tuple[int, int, int],
        thickness: int = 1,
        opacity: float = 1.0,
    ) -> None:
        """Draw a line using Bresenham's algorithm with thickness."""
        r, g, b = color
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        opacity = max(0.0, min(1.0, opacity))

        # Bresenham's line algorithm
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        x, y = x0, y0

        while True:
            # Draw thickness around the point
            for ty in range(-thickness // 2, thickness // 2 + 1):
                for tx in range(-thickness // 2, thickness // 2 + 1):
                    px, py = x + tx, y + ty
                    if 0 <= px < width and 0 <= py < height:
                        idx = (py * width + px) * 3
                        self._blend_pixel(frame, idx, (r, g, b), opacity)

            if x == x1 and y == y1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
