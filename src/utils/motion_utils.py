"""Deterministic motion interpolation helpers."""

from __future__ import annotations

from typing import Any

from src.models.content_package import Motion


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Clamp a value to the provided range."""
    return max(minimum, min(maximum, value))


def apply_easing(progress: float, easing: str) -> float:
    """Apply a small deterministic easing curve."""
    p = clamp(progress)
    easing_name = str(easing).strip().lower()
    if easing_name == "linear":
        return p
    if easing_name == "ease_in":
        return p * p
    if easing_name == "ease_out":
        return 1.0 - (1.0 - p) * (1.0 - p)
    if easing_name == "ease_in_out":
        if p < 0.5:
            return 2.0 * p * p
        return 1.0 - ((-2.0 * p + 2.0) ** 2) / 2.0
    return p


def lerp(start: float, end: float, progress: float) -> float:
    """Linearly interpolate between two numeric values."""
    return start + (end - start) * progress


def interpolate_value(start: Any, end: Any, progress: float) -> Any:
    """Interpolate numeric or x/y mapping values."""
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return lerp(float(start), float(end), progress)
    if isinstance(start, dict) and isinstance(end, dict):
        keys = set(start) | set(end)
        result: dict[str, Any] = {}
        for key in keys:
            start_value = start.get(key, end.get(key, 0))
            end_value = end.get(key, start.get(key, 0))
            result[key] = interpolate_value(start_value, end_value, progress)
        return result
    return end if progress >= 1.0 else start


def motion_progress(motion: Motion, current_time: float) -> float | None:
    """Return normalized progress for a motion or None if inactive."""
    if current_time < motion.start_time:
        return None
    end_time = motion.start_time + motion.duration
    if current_time > end_time:
        return None
    raw = (current_time - motion.start_time) / motion.duration
    return clamp(raw)
