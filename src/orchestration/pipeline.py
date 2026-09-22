"""Pipeline stage definitions and default wiring.

Defines the ordered Day-1 pipeline:

    Topic -> Research -> Strategy -> Script -> Visual Plan -> Render

The render stage is backed by the real YAIRS render pipeline through the
``YairsRendererAdapter``; every other stage uses deterministic mock agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.orchestration.registry import PipelineRegistry

# Stage names (stable string constants shared everywhere).
STAGE_RESEARCH = "research"
STAGE_STRATEGY = "strategy"
STAGE_SCRIPT = "script"
STAGE_VISUAL_PLAN = "visual_plan"
STAGE_RENDER = "render"
STAGE_QC = "qc"

# Execution order of the pipeline.
#
#   … render → QC
#
# QC is a normal final stage backed by ``QCAgent``.  Progressing through it
# does NOT change ``JobStatus`` semantics — the render already produced a
# completed artifact; QC records a dedicated ``qc_status`` and ``qc_report``
# on the job.  Consumers that want a bare 5-stage pipeline can build an
# explicit ``PipelineSpec`` with ``include_qc=False``.
PIPELINE_STAGES: list[str] = [
    STAGE_RESEARCH,
    STAGE_STRATEGY,
    STAGE_SCRIPT,
    STAGE_VISUAL_PLAN,
    STAGE_RENDER,
    STAGE_QC,
]


@dataclass
class PipelineSpec:
    """Immutable description of one pipeline run."""

    stages: list[str] = field(default_factory=lambda: list(PIPELINE_STAGES))
    registry: PipelineRegistry | None = None

    @classmethod
    def default(cls, renderer_adapter: Any | None = None, include_qc: bool = True) -> "PipelineSpec":
        """Build the default pipeline.

        Args:
            renderer_adapter: Optional renderer adapter.  Defaults to the real
                ``YairsRendererAdapter`` wrapping the existing YAIRS render path.
            include_qc: When True (default) append the QC gate as the final
                stage (``STAGE_QC``) backed by ``QCAgent``.
        """
        # Imported lazily to avoid a circular import (factory -> adapters ->
        # pipeline constants) at module import time.
        from src.orchestration.agents.factory import build_default_stage_agents

        stages = list(PIPELINE_STAGES)
        if not include_qc:
            stages = [s for s in stages if s != STAGE_QC]

        agents = build_default_stage_agents(renderer_adapter=renderer_adapter, include_qc=include_qc)
        registry = PipelineRegistry(stages=stages)
        for stage, agent in agents.items():
            if stage in stages:
                registry.register(agent, stage=stage)
        return cls(stages=stages, registry=registry)