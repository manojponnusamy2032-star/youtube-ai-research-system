"""QC Pipeline coordinator.

Runs the full QC suite:

    Script QC
        ↓
    Visual QC
    Repetition QC
        ↓
    Cross-stage QC
        ↓
    Media QC
    Render Configuration QC
        ↓
    Overall QC Decision
        ↓
    QCReport
"""

from __future__ import annotations

from typing import Any

from src.orchestration.qc.models import (
    QCCheck,
    QCReport,
    QCRequest,
    QCStatus,
    QCSeverity,
)
from src.orchestration.qc.script_qc import run_script_qc
from src.orchestration.qc.visual_qc import run_visual_qc
from src.orchestration.qc.repetition_qc import run_repetition_qc
from src.orchestration.qc.cross_stage_qc import run_cross_stage_qc
from src.orchestration.qc.media_qc import run_media_qc
from src.orchestration.qc.render_config_qc import run_render_config_qc


def _compute_overall_status(checks: list[QCCheck]) -> QCStatus:
    """Compute overall QC status from individual checks.

    Policy:
        - Any FAIL severity check → FAIL overall
        - Any WARN severity check (no FAIL) → WARN overall
        - All INFO/PASS → PASS overall
    """
    has_warn = False
    for check in checks:
        if check.severity == QCSeverity.FAIL or check.status == QCStatus.FAIL:
            return QCStatus.FAIL
        if check.severity == QCSeverity.WARN or check.status == QCStatus.WARN:
            has_warn = True

    return QCStatus.WARN if has_warn else QCStatus.PASS


def _aggregate_errors_warnings(checks: list[QCCheck]) -> tuple[list[str], list[str]]:
    """Aggregate error and warning messages from checks."""
    errors: list[str] = []
    warnings: list[str] = []

    for check in checks:
        if check.severity == QCSeverity.FAIL or check.status == QCStatus.FAIL:
            errors.append(f"{check.check_name}: {check.message}")
        elif check.severity == QCSeverity.WARN or check.status == QCStatus.WARN:
            warnings.append(f"{check.check_name}: {check.message}")

    return errors, warnings


def _compute_metrics(checks: list[QCCheck]) -> dict[str, Any]:
    """Compute aggregate metrics from checks."""
    total = len(checks)
    passed = sum(1 for c in checks if c.status == QCStatus.PASS)
    warned = sum(1 for c in checks if c.status == QCStatus.WARN)
    failed = sum(1 for c in checks if c.status == QCStatus.FAIL)

    return {
        "total_checks": total,
        "passed": passed,
        "warned": warned,
        "failed": failed,
    }


class QCPipeline:
    """Coordinates the full QC suite for one job."""

    def run(self, request: QCRequest) -> QCReport:
        """Run all QC checks and return a ``QCReport``."""
        job_id = request.job_id
        script = request.script
        visual_plan = request.visual_plan
        artifact = request.artifact
        render_config = request.render_config or {}

        # Determine the planned duration.
        planned_duration: float | None = None
        if visual_plan is not None:
            planned_duration = float(getattr(visual_plan, "total_duration_seconds", 0) or 0)
        if planned_duration == 0 and artifact is not None:
            planned_duration = float(getattr(artifact, "total_duration_seconds", 0) or 0)

        # Determine the output path.
        output_path: str | None = None
        if artifact is not None:
            output_path = getattr(artifact, "output_path", None) or None

        # Run all QC checks.
        all_checks: list[QCCheck] = []

        all_checks.extend(run_script_qc(script))
        all_checks.extend(run_visual_qc(visual_plan))
        all_checks.extend(run_repetition_qc(visual_plan))
        all_checks.extend(run_cross_stage_qc(script, visual_plan, artifact))

        # Media QC only runs if there is an output path.
        if output_path:
            all_checks.extend(run_media_qc(output_path, planned_duration))
            all_checks.extend(run_render_config_qc(output_path, render_config))
        else:
            all_checks.append(
                QCCheck(
                    check_name="media_qc_skipped",
                    status=QCStatus.FAIL,
                    severity=QCSeverity.FAIL,
                    message="No MP4 output path; media QC cannot run",
                )
            )

        # Compute overall status.
        overall_status = _compute_overall_status(all_checks)
        errors, warnings = _aggregate_errors_warnings(all_checks)
        metrics = _compute_metrics(all_checks)

        # Publish-ready gate.
        # PASS → publish_ready = True
        # WARN/FAIL → publish_ready = False
        publish_ready = overall_status == QCStatus.PASS

        return QCReport(
            job_id=job_id,
            overall_status=overall_status,
            checks=all_checks,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
            publish_ready=publish_ready,
        )


def run_qc(request: QCRequest) -> QCReport:
    """Convenience function to run the QC pipeline.

    Args:
        request: The QC request containing all artifacts to validate.

    Returns:
        A ``QCReport`` with the full QC result.
    """
    pipeline = QCPipeline()
    return pipeline.run(request)
