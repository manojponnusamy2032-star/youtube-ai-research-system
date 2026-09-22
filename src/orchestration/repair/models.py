"""Correction domain models (Day 5).

Typed contracts for the self-correction loop:

    CorrectionTarget   – which pipeline artifact to regenerate
    CorrectionReason   – why the correction is needed
    CorrectionAction   – what kind of regeneration to perform
    CorrectionPlan     – one diagnosed correction (QCReport -> plan)
    CorrectionAttempt  – one recorded correction attempt
    CorrectionReport   – full correction history for one job

These models follow the existing pydantic conventions used throughout
``src/orchestration`` and are fully JSON-serializable for artifact
persistence (``corrections.json``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CorrectionTarget(str, Enum):
    """Smallest pipeline artifact a correction may regenerate.

    Ordered from upstream to downstream; a correction at any target
    invalidates exactly its downstream artifacts (see dependency_map).
    """

    RESEARCH = "research"
    STRATEGY = "strategy"
    SCRIPT = "script"
    STORY_BEATS = "story_beats"
    VISUAL_BEATS = "visual_beats"
    RENDER = "render"


class CorrectionReason(str, Enum):
    """Deterministic reason categories derived from failed QC checks."""

    SCRIPT_QUALITY = "script_quality"
    VISUAL_STATIC = "visual_static"
    VISUAL_MISMATCH = "visual_mismatch"
    VISUAL_MISSING = "visual_missing"
    RENDER_MEDIA = "render_media"
    RENDER_CONFIG = "render_config"
    UNKNOWN = "unknown"


class CorrectionAction(str, Enum):
    """What the executor should do for the targeted artifact."""

    REGENERATE = "regenerate"          # full artifact regeneration
    PARTIAL_REGENERATE = "partial"     # scene-level regeneration (visual only)
    RERENDER = "rerender"              # re-run the renderer as-is


class CorrectionSeverity(str, Enum):
    """Severity of the diagnosed problem (mirrors QCSeverity)."""

    INFO = "info"
    WARN = "warn"
    FAIL = "fail"


class CorrectionTargetDetail(BaseModel):
    """The specific artifact a plan points at, resolved to pipeline terms."""

    target: CorrectionTarget
    stage: str = Field(..., description="Pipeline stage to re-run")
    artifact: str = Field(..., description="VideoJob field holding the artifact")
    affected_scene_ids: list[int] = Field(default_factory=list)


class CorrectionPlan(BaseModel):
    """One diagnosed correction derived deterministically from a QCReport."""

    job_id: str = Field(..., min_length=1)
    target_stage: str = Field(..., min_length=1)
    target_artifact: str = Field(..., min_length=1)
    target: CorrectionTarget
    reason: CorrectionReason
    failed_checks: list[str] = Field(default_factory=list)
    severity: CorrectionSeverity = CorrectionSeverity.FAIL
    action: CorrectionAction = CorrectionAction.REGENERATE
    attempt_number: int = Field(default=0, ge=0)
    affected_scene_ids: list[int] = Field(default_factory=list)
    # Explicit, inspectable context handed to the regenerating agent so the
    # correction actually changes generation (requirement 9).
    correction_context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)

    def context_summary(self) -> str:
        """Human-readable one-line summary of the correction context."""
        checks = ", ".join(self.failed_checks) or "none"
        return (
            f"target={self.target.value} reason={self.reason.value} "
            f"action={self.action.value} failed_checks=[{checks}] "
            f"scenes={self.affected_scene_ids}"
        )


class CorrectionAttempt(BaseModel):
    """Record of one executed correction attempt (lineage entry)."""

    attempt_number: int = Field(..., ge=0)
    failed_checks: list[str] = Field(default_factory=list)
    diagnosis: str = Field(default="")
    target_stage: str = Field(default="")
    target_artifact: str = Field(default="")
    action: str = Field(default="")
    reason: str = Field(default="")
    affected_scene_ids: list[int] = Field(default_factory=list)
    result: str = Field(default="pending", description="pending / qc_failed / passed / skipped")
    qc_status_after: str = Field(default="")
    failed_checks_after: list[str] = Field(default_factory=list)
    # QC-driven retry intelligence (Day-5 extension).
    escalated: bool = Field(
        default=False,
        description="True when a persisting failure escalated the target upstream",
    )
    escalated_from: str = Field(
        default="",
        description="Original target before escalation (empty when not escalated)",
    )
    no_progress: bool = Field(
        default=False,
        description="True when the failed-check set did not shrink after correction",
    )
    applied_at: datetime = Field(default_factory=_utcnow)


class CorrectionReport(BaseModel):
    """Full, append-only correction history for one job (never overwritten)."""

    job_id: str = Field(..., min_length=1)
    initial_qc_status: str = Field(default="")
    final_qc_status: str = Field(default="")
    attempt_count: int = Field(default=0, ge=0)
    attempts: list[CorrectionAttempt] = Field(default_factory=list)
    final_publish_ready: bool = Field(default=False)
    final_outcome: str = Field(
        default="",
        description="SUCCESS / FAILED_QC / FAILED_CORRECTION",
    )
    # QC-driven retry intelligence (Day-5 extension).
    escalation_count: int = Field(
        default=0, ge=0,
        description="Number of attempts whose target was escalated upstream",
    )
    terminal_reason: str = Field(
        default="",
        description=(
            "Why the loop ended: qc_passed / qc_warned / max_attempts_reached "
            "/ no_progress / nothing_actionable / correction_error"
        ),
    )
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
