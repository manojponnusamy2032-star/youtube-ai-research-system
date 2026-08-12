"""Shared generation utilities.

Provide small pure helpers reused across services to avoid duplication.
"""
from __future__ import annotations

from typing import Any, List


def normalize_trends(trend_info: Any) -> List[str]:
    """Normalize trend payload into a list of terms."""
    if trend_info is None:
        return []
    if isinstance(trend_info, str):
        return [trend_info.strip()] if trend_info.strip() else []
    if isinstance(trend_info, list):
        return [str(item).strip() for item in trend_info if str(item).strip()]
    if isinstance(trend_info, dict):
        values: List[str] = []
        for value in trend_info.values():
            if isinstance(value, list):
                values.extend(str(item).strip() for item in value if str(item).strip())
            elif str(value).strip():
                values.append(str(value).strip())
        return values
    return []


def unique(items: List[str]) -> List[str]:
    """Return a deduplicated list preserving order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(item.strip())
    return ordered
