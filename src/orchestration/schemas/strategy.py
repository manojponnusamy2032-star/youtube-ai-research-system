"""Strategy stage contract for the orchestration pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StrategyPackage(BaseModel):
    """Structured content strategy consumed by the script stage."""

    topic: str = Field(..., min_length=1)
    angle: str = Field(..., min_length=1, description="The chosen creative angle")
    narrative_outline: list[str] = Field(default_factory=list, description="Beat-by-beat outline")
    key_messages: list[str] = Field(default_factory=list)
    emotional_triggers: list[str] = Field(default_factory=list)
    hook_idea: str = Field(default="")
    call_to_action: str = Field(default="")
    target_audience: str = Field(default="general")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # -- Day-2 real-adapter pass-through (all optional; mocks leave defaults) --
    # Real YAIRS strategy artifacts (selected title, scored hook, ranked title
    # candidates, viral pattern report, knowledge base) that the real script
    # stage consumes.  Carried inside the contract, never as bare dicts.
    best_title: dict[str, Any] = Field(default_factory=dict)
    hook: dict[str, Any] = Field(default_factory=dict)
    generated_titles: list[dict[str, Any]] = Field(default_factory=list)
    pattern_report: dict[str, Any] = Field(default_factory=dict)
    knowledge_base: list[dict[str, Any]] = Field(default_factory=list)