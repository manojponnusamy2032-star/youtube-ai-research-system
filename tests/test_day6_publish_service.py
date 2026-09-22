"""Day-6 tests for the PublishService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import VideoJob, JobStatus
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import (
    PublishedVideo,
    PublishStatus,
    PublishVisibility,
)
from src.orchestration.youtube_publisher import YouTubePublisher


def _make_job(job_id: str = "job_001", video_path: str | None = None) -> VideoJob:
    """Create a minimal VideoJob for testing."""
    artifact = None
    if video_path:
        artifact = VideoArtifact(job_id=job_id, output_path=video_path)
    return VideoJob(
        job_id=job_id,
        topic="Test Topic",
        status=JobStatus.COMPLETED,
        artifact=artifact,
    )


def _make_qc_report(publish_ready: bool = True, status: QCStatus = QCStatus.PASS) -> QCReport:
    return QCReport(job_id="test_job", overall_status=status, publish_ready=publish_ready, checks=[])


class TestPublishServiceSuccess:
    def test_successful_mock_publishing(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")
        job = _make_job(video_path=str(video))
        qc_report = _make_qc_report(publish_ready=True)
        service = PublishService(mock=True, output_dir=str(tmp_path))
        gate_result, published = service.publish(job, qc_report)
        assert published is not None
        assert published.status == PublishStatus.COMPLETED
        assert published.video_id is not None

    def test_publisher_called_exactly_once(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")
        job = _make_job(video_path=str(video))
        qc_report = _make_qc_report(publish_ready=True)
        mock_publisher = YouTubePublisher(mock=True)
        service = PublishService(publisher=mock_publisher, output_dir=str(tmp_path))
        service.publish(job, qc_report)
        assert mock_publisher.upload_called is True
        assert len(mock_publisher._upload_attempts) == 1


class TestPublishServiceGateRejection:
    def test_qc_fail_gate_rejects_publish(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")
        job = _make_job(video_path=str(video))
        qc_report = _make_qc_report(publish_ready=False, status=QCStatus.FAIL)
        mock_publisher = YouTubePublisher(mock=True)
        service = PublishService(publisher=mock_publisher, output_dir=str(tmp_path))
        gate_result, published = service.publish(job, qc_report)
        assert gate_result.allowed is False
        assert published is None
        assert mock_publisher.upload_called is False


class TestPublishServicePublisherFailure:
    def test_publisher_failure_returns_failed_status(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")
        job = _make_job(video_path=str(video))
        qc_report = _make_qc_report(publish_ready=True)
        mock_publisher = MagicMock(spec=YouTubePublisher)
        mock_publisher.mock = True
        mock_publisher.publish.return_value = PublishedVideo(
            job_id="job_001", video_id=None, video_url=None,
            title="Test", visibility=PublishVisibility.PRIVATE,
            status=PublishStatus.FAILED, error="Upload failed",
        )
        service = PublishService(publisher=mock_publisher, output_dir=str(tmp_path))
        gate_result, published = service.publish(job, qc_report)
        assert published is not None
        assert published.status == PublishStatus.FAILED


class TestPublishServicePersistence:
    def test_persistence_writes_result(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")
        job_dir = tmp_path / "job_001"
        job_dir.mkdir(parents=True, exist_ok=True)
        job = _make_job(job_id="job_001", video_path=str(video))
        qc_report = _make_qc_report(publish_ready=True)
        service = PublishService(mock=True, output_dir=str(tmp_path))
        service.publish(job, qc_report)
        result_path = job_dir / "publish_result.json"
        assert result_path.exists()


class TestPublishServiceIdempotency:
    def test_idempotent_publish_returns_existing(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")
        job_dir = tmp_path / "job_001"
        job_dir.mkdir(parents=True, exist_ok=True)
        existing = PublishedVideo(
            job_id="job_001", video_id="existing123",
            video_url="https://www.youtube.com/watch?v=existing123",
            title="Existing", visibility=PublishVisibility.PRIVATE,
            status=PublishStatus.COMPLETED,
        )
        from src.orchestration.youtube_publisher import write_publish_result
        write_publish_result(existing, job_dir)
        job = _make_job(job_id="job_001", video_path=str(video))
        qc_report = _make_qc_report(publish_ready=True)
        mock_publisher = YouTubePublisher(mock=True)
        service = PublishService(publisher=mock_publisher, output_dir=str(tmp_path))
        gate_result, published = service.publish(job, qc_report)
        assert published is not None
        assert published.video_id == "existing123"
        assert mock_publisher.upload_called is False

