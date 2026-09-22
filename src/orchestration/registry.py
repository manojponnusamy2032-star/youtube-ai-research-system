"""Stage registry for the orchestration pipeline.

Mirrors the existing ``src.core.agent_registry`` pattern but keys agents by
their pipeline stage name instead of a free-form agent name.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.base import StageAgent


class PipelineRegistry:
    """Stores and retrieves stage agents by pipeline stage."""

    def __init__(self, stages: list[str] | None = None) -> None:
        if stages is None:
            from src.orchestration.pipeline import PIPELINE_STAGES

            stages = list(PIPELINE_STAGES)
        self._stages: list[str] = list(stages)
        self._agents: dict[str, StageAgent[Any, Any]] = {}

    def register(self, agent: StageAgent[Any, Any], stage: str | None = None) -> "PipelineRegistry":
        """Register an agent for its declared (or explicit) stage."""
        stage_name = stage or getattr(agent, "stage", "")
        if not stage_name:
            raise ValueError("agent must declare a stage (or pass stage explicitly)")
        if stage_name not in self._stages:
            raise ValueError(f"unknown pipeline stage: {stage_name!r} (known: {self._stages})")
        self._agents[stage_name] = agent
        return self

    def get(self, stage: str) -> StageAgent[Any, Any] | None:
        """Return the agent registered for a stage, or None."""
        return self._agents.get(stage)

    def has(self, stage: str) -> bool:
        """Return True when a stage has a registered agent."""
        return stage in self._agents

    def all(self) -> dict[str, StageAgent[Any, Any]]:
        """Return all registered agents keyed by stage."""
        return dict(self._agents)

    def ordered_stages(self) -> list[str]:
        """Return pipeline stages in execution order."""
        return list(self._stages)