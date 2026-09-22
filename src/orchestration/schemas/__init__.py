"""Orchestration schema package.

Stable data contracts exchanged between pipeline stages.  Each module defines
typed Pydantic models describing one stage's input/output.  Where the existing
YAIRS models already define a contract (e.g. ``RenderJobSpec``, ``AudioRequest``
inside ``src.models.content_package``) this package references those structures
instead of re-implementing them.
"""

from src.orchestration.schemas.job import (
    JobStatus,
    QCJobStatus,
    StageRecord,
    StageStatus,
    VideoJob,
)
from src.orchestration.schemas.production import ProductionRequest, VideoArtifact
from src.orchestration.schemas.publish import (
    PublishGateResult,
    PublishRequest,
    PublishedVideo,
    PublishStatus,
    PublishVisibility,
)
from src.orchestration.schemas.research import ResearchPackage, ResearchRequest
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.strategy import StrategyPackage
from src.orchestration.schemas.topic import TopicRequest
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan

__all__ = [
    "JobStatus",
    "QCJobStatus",
    "ProductionRequest",
    "PublishGateResult",
    "PublishRequest",
    "PublishedVideo",
    "PublishStatus",
    "PublishVisibility",
    "ResearchPackage",
    "ResearchRequest",
    "ScriptPackage",
    "ScriptSection",
    "StageRecord",
    "StageStatus",
    "StrategyPackage",
    "TopicRequest",
    "VideoArtifact",
    "VideoJob",
    "VisualPlan",
    "VisualScenePlan",
]