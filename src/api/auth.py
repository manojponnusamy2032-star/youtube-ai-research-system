"""Simple API key authentication dependency."""

from __future__ import annotations

from fastapi import Header, HTTPException

from src.api.dependencies import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Validate X-API-Key header when API key auth is configured."""
    settings = get_settings()
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
