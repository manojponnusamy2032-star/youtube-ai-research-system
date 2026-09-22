"""Factory for the default Day-1 pipeline stage agents.

Research / Strategy / Script / Visual planning use deterministic mocks.
The render stage uses the real ``YairsRendererAdapter`` wrapping the existing
YAIRS render pipeline.
"""

from __future__ import annotations

from typing import Any

from src.adapters.renderer.yairs import YairsRendererAdapter
from src.orchestration.agents.research.mock import MockResearchAgent
from src.orchestration.agents.script.mock import MockScriptAgent
from src.orchestration.agents.strategy.mock import MockStrategyAgent
from src.orchestration.agents.visual.mock import MockVisualPlannerAgent
from src.orchestration.pipeline import (
    STAGE_QC,
    STAGE_RENDER,
    STAGE_RESEARCH,
    STAGE_SCRIPT,
    STAGE_STRATEGY,
    STAGE_VISUAL_PLAN,
)
from src.orchestration.qc.agent import QCAgent


def _qc_agent_if(include_qc: bool) -> dict[str, Any]:
    """Return ``{STAGE_QC: QCAgent()}`` when QC is enabled, else ``{}``.

    QC gates do not change ``JobStatus`` semantics — the render stage already
    produced a completed artifact.  Callers that need a bare 5-stage pipeline
    (no QC) pass ``include_qc=False``.
    """
    if include_qc:
        return {STAGE_QC: QCAgent()}
    return {}


def build_default_stage_agents(
    renderer_adapter: Any | None = None,
    include_qc: bool = True,
) -> dict[str, Any]:
    """Return ``{stage: agent}`` for the Day-1 pipeline.

    Args:
        renderer_adapter: Optional renderer adapter.  Defaults to the real
            ``YairsRendererAdapter`` backed by StickmanRenderer + VideoAssembler.
        include_qc: When True (default) register the final ``QCAgent`` gate.
    """
    agents: dict[str, Any] = {
        STAGE_RESEARCH: MockResearchAgent(),
        STAGE_STRATEGY: MockStrategyAgent(),
        STAGE_SCRIPT: MockScriptAgent(),
        STAGE_VISUAL_PLAN: MockVisualPlannerAgent(),
        STAGE_RENDER: renderer_adapter or YairsRendererAdapter(),
    }
    agents.update(_qc_agent_if(include_qc))
    return agents


def build_real_stage_agents(
    renderer_adapter: Any | None = None,
    trending_research_service: Any | None = None,
    title_generation_service: Any | None = None,
    content_generation_service: Any | None = None,
    visual_story_planner: Any | None = None,
    include_qc: bool = True,
) -> dict[str, Any]:
    """Return ``{stage: agent}`` for the real Day-2 pipeline.

    Args:
        renderer_adapter: Optional renderer adapter. Defaults to ``YairsRendererAdapter``.
        trending_research_service: Required for RealResearchAgent.
        title_generation_service: Required for RealStrategyAgent.
        content_generation_service: Required for RealStrategyAgent and RealScriptAgent.
        visual_story_planner: Optional for RealVisualPlannerAgent.
        include_qc: When True (default) register the final ``QCAgent`` gate.
    """
    from src.adapters.research.yairs import RealResearchAgent
    from src.adapters.script.yairs import RealScriptAgent
    from src.adapters.strategy.yairs import RealStrategyAgent
    from src.adapters.visual.yairs import RealVisualPlannerAgent

    research_agent = RealResearchAgent(trending_research_service=trending_research_service)
    strategy_agent = RealStrategyAgent(
        title_generation_service=title_generation_service,
        content_generation_service=content_generation_service,
    )
    script_agent = RealScriptAgent(content_generation_service=content_generation_service)
    visual_agent = RealVisualPlannerAgent(visual_story_planner=visual_story_planner)

    agents: dict[str, Any] = {
        STAGE_RESEARCH: research_agent,
        STAGE_STRATEGY: strategy_agent,
        STAGE_SCRIPT: script_agent,
        STAGE_VISUAL_PLAN: visual_agent,
        STAGE_RENDER: renderer_adapter or YairsRendererAdapter(),
    }
    agents.update(_qc_agent_if(include_qc))
    return agents


def build_intelligent_stage_agents(
    renderer_adapter: Any | None = None,
    include_qc: bool = True,
) -> dict[str, Any]:
    """Return ``{stage: agent}`` for the Day-4 intelligent visual pipeline.

    Uses mock research/strategy/script agents but the new
    ``IntelligentVisualPlannerAgent`` for beat-driven scene planning.
    """
    from src.orchestration.agents.visual.intelligent import (
        IntelligentVisualPlannerAgent,
    )

    agents: dict[str, Any] = {
        STAGE_RESEARCH: MockResearchAgent(),
        STAGE_STRATEGY: MockStrategyAgent(),
        STAGE_SCRIPT: MockScriptAgent(),
        STAGE_VISUAL_PLAN: IntelligentVisualPlannerAgent(),
        STAGE_RENDER: renderer_adapter or YairsRendererAdapter(),
    }
    agents.update(_qc_agent_if(include_qc))
    return agents


def build_stage_agents(mode: str = "mock", **kwargs: Any) -> dict[str, Any]:
    """Return ``{stage: agent}`` for the given mode.

    Args:
        mode: ``"mock"`` for Day-1 mocks, ``"real"`` for Day-2 real adapters,
              ``"intelligent"`` for Day-4 beat-driven visual planning.
        **kwargs: Passed to the underlying builder (e.g. ``include_qc=False``).
    """
    if mode == "real":
        return build_real_stage_agents(**kwargs)
    if mode == "intelligent":
        return build_intelligent_stage_agents(**kwargs)
    return build_default_stage_agents(**kwargs)
