"""QC pipeline stage agent.

Wraps the QC engine behind the common ``StageAgent`` interface so the QC gate
can be registered as a normal pipeline stage (``STAGE_QC``) and executed by
the generic ``VideoPipelineOrchestrator`` after the render stage.

    Render → QC (QCAgent) → QCReport → job.qc_status
"""

from __future__ import annotations

from src.orchestration.base import StageAgent
from src.orchestration.pipeline import STAGE_QC
from src.orchestration.qc.models import QCReport, QCRequest, QCStatus
from src.orchestration.qc.qc_pipeline import QCPipeline
from src.orchestration.schemas.job import QCJobStatus


def qc_job_status_for(report: QCReport) -> QCJobStatus:
    """Map a QCReport's overall status onto the job-level QCJobStatus."""
    if report.overall_status == QCStatus.PASS:
        return QCJobStatus.PASSED
    if report.overall_status == QCStatus.WARN:
        return QCJobStatus.WARNED
    return QCJobStatus.FAILED


class QCAgent(StageAgent[QCRequest, QCReport]):
    """Runs the full QC suite for one job and returns a ``QCReport``."""

    stage = STAGE_QC

    def __init__(self, pipeline: QCPipeline | None = None) -> None:
        """Initialize the agent.

        Args:
            pipeline: Optional custom ``QCPipeline``.  Defaults to a standard
                pipeline running every deterministic validator + FFprobe checks.
        """
        self._pipeline = pipeline or QCPipeline()

    def run(self, request: QCRequest) -> QCReport:
        """Execute the full QC suite for the given request."""
        return self._pipeline.run(request)