"""QC domain models.

Defines the typed contracts for the quality-control system:

    QCStatus      – overall verdict (PASS / WARN / FAIL)
    QCSeverity    – per-check severity (INFO / WARN / FAIL)
    QCCheck       – one individual validation result
    QCReport      – aggregated report for one job
    QCRequest     – input contract for the QC pipeline
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QCStatus(str, Enum):
    """Overall QC verdict for a job."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class QCSeverity(str, Enum):
    """Severity of an individual QC check."""

    INFO = "info"
    WARN = "warn"
    FAIL = "fail"


class QCCheck(BaseModel):
    """One individual QC validation result."""

    check_name: str = Field(..., min_length=1)
    status: QCStatus = Field(..., description="PASS / WARN / FAIL")
    severity: QCSeverity = Field(default=QCSeverity.INFO, description="info / warn / fail")
    message: str = Field(default="")
    details: dict[str, Any] = Field(default_factory=dict)


class QCReport(BaseModel):
    """Aggregated QC report for one job."""

    job_id: str = Field(..., min_length=1)
    overall_status: QCStatus = Field(default=QCStatus.FAIL)
    checks: list[QCCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    publish_ready: bool = Field(default=False)


class QCRequest(BaseModel):
    """Input contract for the QC pipeline.

    Contains everything the QC system needs to validate a job.
    """

    job_id: str = Field(..., min_length=1)
    script: Any | None = Field(default=None, description="ScriptPackage or None")
    visual_plan: Any | None = Field(default=None, description="VisualPlan or None")
    artifact: Any | None = Field(default=None, description="VideoArtifact or None")
    render_config: dict[str, Any] = Field(default_factory=dict)
    output_dir: str | None = Field(default=None, description="Job output directory")
