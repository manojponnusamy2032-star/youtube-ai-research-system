"""Video job state contracts for the orchestration pipeline.

A ``VideoJob`` is the central, serializable state object of the pipeline
(Principle 2).  Every stage's output is attached to the job as a typed field;
the orchestrator persists the job after every state change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.research import ResearchPackage
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.strategy import StrategyPackage
from src.orchestration.schemas.visual import VisualPlan


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    """Top-level status of a video job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class QCJobStatus(str, Enum):
    """QC gate status for a video job.

    A dedicated status field so QC results do not distort the existing
    ``JobStatus`` lifecycle (render succeeded → ``COMPLETED`` remains true
    even when QC warns/fails).
    """

    NOT_RUN = "not_run"
    RUNNING = "running"
    PASSED = "passed"
    WARNED = "warned"
    FAILED = "failed"


class StageStatus(str, Enum):
    """Per-stage status recorded inside a VideoJob."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StageRecord(BaseModel):
    """Execution record for a single pipeline stage."""

    stage: str = Field(..., min_length=1)
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    artifact_path: str | None = None


class VideoJob(BaseModel):
    """Central serializable state for one orchestrated video production."""

    job_id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    niche: str = Field(default="")
    audience: str = Field(default="general")
    status: JobStatus = JobStatus.PENDING
    current_stage: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    error: str | None = None

    stages: dict[str, StageRecord] = Field(default_factory=dict)
    research: ResearchPackage | None = None
    strategy: StrategyPackage | None = None
    script: ScriptPackage | None = None
    visual_plan: VisualPlan | None = None
    artifact: VideoArtifact | None = None

    # Quality-control gate (dedicated status, doesn't alter JobStatus lifecycle).
    qc_status: QCJobStatus = QCJobStatus.NOT_RUN
    qc_report_path: str | None = Field(
        default=None, description="Path to persisted qc_report.json"
    )