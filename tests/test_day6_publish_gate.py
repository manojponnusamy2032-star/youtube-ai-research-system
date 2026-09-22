"""Tests for the publish gate."""

from __future__ import annotations

import pytest

from src.orchestration.publish_gate import evaluate_publish_gate
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.publish import (
    PublishGateResult,
    PublishedVideo,
    PublishStatus,
    PublishVisibility,
)


def _make_qc_report(status: QCStatus, publish_ready: bool) -> QCReport:
    return QCReport(
        job_id="job-1",
        overall_status=status,
        publish_ready=publish_ready,
        checks=[],
    )


class TestPublishGateAllowed:
    def test_pass_and_publish_ready_allowed(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"video")
        qc = _make_qc_report(QCStatus.PASS, publish_ready=True)
        result = evaluate_publish_gate(
            job_id="job-1", qc_report=qc, video_path=str(video)
        )
        assert result.allowed is True
        assert result.publish_ready is True
        assert result.qc_status == QCStatus.PASS.value

    def test_pass_without_video_path_blocked(self):
        """Day-7 safety: QC PASS without a video artifact must NOT publish."""
        qc = _make_qc_report(QCStatus.PASS, publish_ready=True)
        result = evaluate_publish_gate(job_id="job-1", qc_report=qc)
        assert result.allowed is False
        assert result.publish_ready is True
        assert "no video path" in result.reason.lower()


class TestPublishGateBlocked:
    def test_fail_blocked(self):
        qc = _make_qc_report(QCStatus.FAIL, publish_ready=False)
        result = evaluate_publish_gate(job_id="job-1", qc_report=qc)
        assert result.allowed is False
        assert result.publish_ready is False
        assert "QC gate blocked" in result.reason

    def test_warn_blocked(self):
        qc = _make_qc_report(QCStatus.WARN, publish_ready=False)
        result = evaluate_publish_gate(job_id="job-1", qc_report=qc)
        assert result.allowed is False
        assert result.publish_ready is False

    def test_missing_video_blocked(self, tmp_path):
        missing = tmp_path / "missing.mp4"
        qc = _make_qc_report(QCStatus.PASS, publish_ready=True)
        result = evaluate_publish_gate(
            job_id="job-1", qc_report=qc, video_path=str(missing)
        )
        assert result.allowed is False
        assert "missing" in result.reason.lower()

    def test_skip_publish_blocked(self):
        qc = _make_qc_report(QCStatus.PASS, publish_ready=True)
        result = evaluate_publish_gate(
            job_id="job-1", qc_report=qc, skip_publish=True
        )
        assert result.allowed is False
        assert "disabled" in result.reason.lower()


class TestPublishGateIdempotent:
    def test_existing_successful_publish_returns_allowed(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"video")
        qc = _make_qc_report(QCStatus.PASS, publish_ready=True)
        existing = PublishedVideo(
            job_id="job-1",
            video_id="vid-123",
            video_url="https://www.youtube.com/watch?v=vid-123",
            title="Existing",
            visibility=PublishVisibility.PRIVATE,
            status=PublishStatus.COMPLETED,
        )
        result = evaluate_publish_gate(
            job_id="job-1",
            qc_report=qc,
            video_path=str(video),
            existing_publish=existing,
        )
        assert result.allowed is True
        assert result.existing_publish is existing
        assert "idempotent" in result.reason.lower()
