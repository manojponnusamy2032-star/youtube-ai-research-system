"""Research stage contracts for the orchestration pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    """Input for the research stage."""

    topic: str = Field(..., min_length=3, max_length=500)
    niche: str = Field(default="", max_length=200)
    audience: str = Field(default="general", max_length=100)


class ResearchPackage(BaseModel):
    """Structured research output consumed by the strategy stage.

    Future open-source research adapters must return this exact contract so
    the orchestration layer never depends on a specific collector/summarizer.
    """

    topic: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    key_facts: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    sub_topics: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    target_audience: str = Field(default="general")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # -- Day-2 real-adapter pass-through (all optional; mocks leave defaults) --
    # Real YAIRS research produces rich artifacts (viral pattern report,
    # knowledge-base entries) that downstream real stages (strategy/script)
    # consume directly.  They travel inside the contract so no stage ever
    # receives an untyped dict from its predecessor.
    pattern_report: dict[str, Any] = Field(default_factory=dict)
    knowledge_base: list[dict[str, Any]] = Field(default_factory=list)
    videos_collected: int = Field(default=0, ge=0)
    trend_info: dict[str, Any] | None = None