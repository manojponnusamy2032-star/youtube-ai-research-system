"""Renderer adapter interface.

A renderer adapter turns a ``ProductionRequest`` into a ``VideoArtifact``.
The orchestration layer only ever depends on this interface, so the concrete
YAIRS implementation (or any future renderer) is fully replaceable.
"""

from __future__ import annotations

from src.orchestration.base import StageAgent
from src.orchestration.pipeline import STAGE_RENDER
from src.orchestration.schemas.production import ProductionRequest, VideoArtifact


class RendererAdapter(StageAgent[ProductionRequest, VideoArtifact]):
    """Produces a final VideoArtifact (MP4) from a ProductionRequest."""

    stage: str = STAGE_RENDER

    def run(self, request: ProductionRequest) -> VideoArtifact:
        raise NotImplementedError