"""Day-6 tests for YouTube Publisher (mock and real adapter)."""

from __future__ import annotations

import pytest

from src.orchestration.schemas.publish import PublishStatus, PublishVisibility, PublishedVideo
from src.orchestration.youtube_publisher import (
    YouTubePublisher,
    write_publish_result,
    load_publish_result,
    get_or_create_mock_publisher,
    _mock_publisher_instance,
)


class TestMockPublisher:
    """Tests for mock mode YouTube publisher."""

    def setup_method(self):
        # Reset the global mock publisher instance for test isolation
        import src.orchestration.youtube_publisher as yt_module
        yt_module._mock_publisher_instance = None

    def test_mock_publish_different_ids_for_different_jobs(self, tmp_path):
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        publisher = get_or_create_mock_publisher()
        result1 = publisher.publish(job_id="job_001", video_path=str(video_path), title="Test")
        result2 = publisher.publish(job_id="job_002", video_path=str(video_path), title="Test")
        assert result1.video_id != result2.video_id

    def test_mock_publish_upload_called(self, tmp_path):
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        publisher = get_or_create_mock_publisher()
        assert publisher.upload_called is False
        publisher.publish(job_id="job_001", video_path=str(video_path), title="Test")
        assert publisher.upload_called is True

    def test_mock_publish_has_service_response(self, tmp_path):
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        publisher = get_or_create_mock_publisher()
        result = publisher.publish(job_id="job_001", video_path=str(video_path), title="Test")
        assert result.service_response is not None
        assert result.service_response.get("mode") == "mock"
        assert "mock_video_id" in result.service_response


class TestFailedVideoPath:
    """Tests for handling missing video files."""

    def test_publish_fails_for_missing_video(self):
        publisher = get_or_create_mock_publisher()
        result = publisher.publish(job_id="job_001", video_path="/nonexistent/video.mp4", title="Test")
        assert result.status == PublishStatus.FAILED
        assert "does not exist" in result.error

    def test_publish_fails_for_nonexistent_path(self):
        publisher = get_or_create_mock_publisher()
        result = publisher.publish(job_id="job_001", video_path="/tmp/nonexistent_dir/video.mp4", title="Test")
        assert result.status == PublishStatus.FAILED


class TestPersistenceHelpers:
    """Tests for write/load publish result helpers."""

    def test_write_and_load_publish_result(self, tmp_path):
        result = PublishedVideo(
            job_id="job_001", video_id="test123",
            video_url="https://www.youtube.com/watch?v=test123",
            title="Test", visibility=PublishVisibility.PRIVATE,
            status=PublishStatus.COMPLETED,
        )
        write_publish_result(result, tmp_path)
        loaded = load_publish_result(tmp_path)
        assert loaded is not None
        assert loaded.video_id == "test123"
        assert loaded.job_id == "job_001"

    def test_load_nonexistent_result(self, tmp_path):
        from src.orchestration.schemas.publish import PublishedVideo
        result = load_publish_result(tmp_path / "nonexistent")
        assert result is None

    def test_load_corrupted_result(self, tmp_path):
        result_path = tmp_path / "publish_result.json"
        result_path.write_text("not valid json {")
        result = load_publish_result(tmp_path)
        assert result is None


class TestIdempotency:
    """Tests for idempotency behavior."""

    def test_mock_publisher_idempotent_returns_same_result(self, tmp_path):
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        publisher = get_or_create_mock_publisher()
        result1 = publisher.publish(job_id="job_001", video_path=str(video_path), title="Test")
        result2 = publisher.publish(job_id="job_001", video_path=str(video_path), title="Test")
        assert result1.video_id == result2.video_id
        assert result1.video_url == result2.video_url


    def test_mock_publish_succeeds(self, tmp_path):
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        publisher = get_or_create_mock_publisher()
        result = publisher.publish(job_id="job_001", video_path=str(video_path), title="Test Video")
        assert result.status == PublishStatus.COMPLETED
        assert result.video_id is not None
        assert result.video_url.startswith("https://www.youtube.com/watch?v=")

    def test_mock_publish_generates_deterministic_id(self, tmp_path):
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        publisher1 = get_or_create_mock_publisher()
        result1 = publisher1.publish(job_id="job_001", video_path=str(video_path), title="Test")
        publisher2 = get_or_create_mock_publisher()
        result2 = publisher2.publish(job_id="job_001", video_path=str(video_path), title="Test")
        assert result1.video_id == result2.video_id
