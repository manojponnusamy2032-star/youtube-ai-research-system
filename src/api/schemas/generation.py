"""Schemas for generation endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerationBaseRequest(BaseModel):
    """Common request fields for generation endpoints."""

    topic: str = Field(..., min_length=1, max_length=300)
    audience: str = Field(default="creators")
    niche: str = Field(default="youtube")
    knowledge_base: list[dict[str, Any]] = Field(default_factory=list)
    pattern_report: dict[str, Any] = Field(default_factory=dict)
    generated_titles: list[dict[str, Any]] = Field(default_factory=list)
    trend_info: Any = None


class TitlesRequest(BaseModel):
    """Request for title generation."""

    topic: str = Field(..., min_length=1, max_length=300)
    niche: str | None = None
    audience: str | None = None
    trend_info: Any = None
    count: int = Field(default=20, ge=1, le=50)


class TitlesResponse(BaseModel):
    """Response for title generation."""

    count: int
    titles: list[dict[str, Any]]


class HookResponse(BaseModel):
    """Response for hook generation."""

    hook: dict[str, Any]


class ThumbnailResponse(BaseModel):
    """Response for thumbnail generation."""

    thumbnail: dict[str, Any]


class ScriptResponse(BaseModel):
    """Response for script generation."""

    script: dict[str, Any]


class SeoResponse(BaseModel):
    """Response for seo generation."""

    seo: dict[str, Any]


class ContentPackageResponse(BaseModel):
    """Response for full content package generation."""

    content_package: dict[str, Any]
