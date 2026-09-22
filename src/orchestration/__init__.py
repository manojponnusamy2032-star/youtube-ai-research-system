"""Orchestration package for the modular multi-agent YouTube automation platform.

Day-1 scope: integration foundation.  Stable schemas, a serializable job
state, a common typed agent interface, a minimal orchestrator and an adapter
layer that connects the pipeline to the existing real YAIRS render pipeline.
"""

from src.orchestration.orchestrator import VideoPipelineOrchestrator
from src.orchestration.pipeline import PIPELINE_STAGES, PipelineSpec
from src.orchestration.publish_service import PublishService
from src.orchestration.registry import PipelineRegistry
from src.orchestration.schemas import VideoJob

__all__ = [
    "PIPELINE_STAGES",
    "PipelineRegistry",
    "PipelineSpec",
    "PublishService",
    "VideoJob",
    "VideoPipelineOrchestrator",
]