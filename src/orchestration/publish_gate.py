"""Publish gate – enforces QC-based publishing authorization.

Publishing is allowed ONLY when:
    - qc_report.publish_ready is True
    - The video artifact exists and is readable
    - No existing successful publish for this job (idempotency)

Rules:
    QC PASS       → publish_ready=True  → allowed (if no existing publish)
    QC WARN       → publish_ready=False → blocked
    QC FAIL       → publish_ready=False → blocked (never publish)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.publish import (
    PublishGateResult,
    PublishRequest,
    PublishedVideo,
    PublishStatus,
    PublishVisibility,
)


def evaluate_publish_gate(
    *,
    job_id: str,
    qc_report: QCReport,
    video_path: str | None = None,
    existing_publish: PublishedVideo | None = None,
    skip_publish: bool = False,
) -> PublishGateResult:
    """Evaluate whether publishing is allowed for this job.

    Args:
        job_id: The job identifier.
        qc_report: The final QC report.
        video_path: Optional path to the video artifact for validation.
        existing_publish: Optional existing publish result for idempotency check.
        skip_publish: If True, publishing is explicitly disabled (returns SKIPPED).

    Returns:
        PublishGateResult indicating whether publishing is allowed.
    """
    # 1. Idempotency: if we already have a successful publish, return it
    if existing_publish is not None and existing_publish.status == PublishStatus.COMPLETED:
        return PublishGateResult(
            job_id=job_id,
            allowed=True,
            publish_ready=True,  # Implied by existing successful publish
            qc_status=qc_report.overall_status.value,
            reason=f"Idempotent return: existing publish {existing_publish.video_id}",
            existing_publish=existing_publish,
        )

    # 2. Explicit skip
    if skip_publish:
        return PublishGateResult(
            job_id=job_id,
            allowed=False,
            publish_ready=qc_report.publish_ready,
            qc_status=qc_report.overall_status.value,
            reason="Publishing explicitly disabled (skip_publish=True)",
            existing_publish=None,
        )

    # 3. QC gate: publish_ready must be True
    if not qc_report.publish_ready:
        return PublishGateResult(
            job_id=job_id,
            allowed=False,
            publish_ready=False,
            qc_status=qc_report.overall_status.value,
            reason=f"QC gate blocked: publish_ready=False (QC status: {qc_report.overall_status.value})",
            existing_publish=None,
        )

    # 4. Validate video artifact: a path MUST be provided and must exist.
    #    Day-7 safety: a missing/empty video path blocks publishing — it is
    #    never treated as "nothing to validate".
    if not video_path:
        return PublishGateResult(
            job_id=job_id,
            allowed=False,
            publish_ready=True,  # QC passed but there is no video to upload
            qc_status=qc_report.overall_status.value,
            reason="Video artifact missing: no video path provided",
            existing_publish=None,
        )
    if not os.path.exists(video_path):
        return PublishGateResult(
            job_id=job_id,
            allowed=False,
            publish_ready=True,  # QC passed but video missing
            qc_status=qc_report.overall_status.value,
            reason=f"Video artifact missing: {video_path}",
            existing_publish=None,
        )
    if not os.path.isfile(video_path):
        return PublishGateResult(
            job_id=job_id,
            allowed=False,
            publish_ready=True,
            qc_status=qc_report.overall_status.value,
            reason=f"Video path is not a file: {video_path}",
            existing_publish=None,
        )
    # Check readable
    if not os.access(video_path, os.R_OK):
        return PublishGateResult(
            job_id=job_id,
            allowed=False,
            publish_ready=True,
            qc_status=qc_report.overall_status.value,
            reason=f"Video file not readable: {video_path}",
            existing_publish=None,
        )

    # All gates passed
    return PublishGateResult(
        job_id=job_id,
        allowed=True,
        publish_ready=True,
        qc_status=qc_report.overall_status.value,
        reason="QC passed, video artifact valid, no existing publish",
        existing_publish=None,
    )


def can_publish(qc_report: QCReport) -> bool:
    """Simple check: can this job be published based on QC alone?"""
    return qc_report.publish_ready is True


def get_publish_gate_message(result: PublishGateResult) -> str:
    """Human-readable message for the publish gate result."""
    if result.allowed:
        if result.existing_publish:
            return f"PUBLISH ALLOWED (idempotent): {result.reason}"
        return f"PUBLISH ALLOWED: {result.reason}"
    return f"PUBLISH BLOCKED: {result.reason}"