"""Day-6 tests for YouTube publishing models and metadata generation."""

from __future__ import annotations

import pytest

from src.orchestration.schemas.publish import (
    PublishGateResult,
    PublishRequest,
    PublishedVideo,
    PublishStatus,
    PublishVisibility,
)
from src.orchestration.publish_metadata import generate_publish_metadata
from src.orchestration.schemas.strategy import StrategyPackage
from src.orchestration.schemas.script import ScriptPackage, ScriptSection


class TestPublishRequest:
    """Tests for PublishRequest model."""


    def test_title_too_long(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video")
        with pytest.raises(ValueError, match="100"):
            PublishRequest(job_id="job_001", video_path=str(video), title="x" * 101)


class TestPublishedVideo:
    """Tests for PublishedVideo model."""

    def test_successful_publish(self):
        result = PublishedVideo(
            job_id="job_001", video_id="abc123",
            video_url="https://www.youtube.com/watch?v=abc123",
            title="Test Video", visibility=PublishVisibility.PRIVATE,
            status=PublishStatus.COMPLETED, upload_attempt=1,
        )
        assert result.video_id == "abc123"
        assert result.status == PublishStatus.COMPLETED
        assert result.video_url is not None

    def test_failed_publish(self):
        result = PublishedVideo(
            job_id="job_001", video_id=None, video_url=None,
            title="Test Video", visibility=PublishVisibility.PRIVATE,
            status=PublishStatus.FAILED, error="Upload failed",
        )
        assert result.status == PublishStatus.FAILED
        assert result.error is not None


class TestPublishGateResult:
    """Tests for PublishGateResult model."""

    def test_allowed_result(self):
        result = PublishGateResult(
            job_id="job_001", allowed=True, publish_ready=True,
            qc_status="pass", reason="QC passed",
        )
        assert result.allowed is True
        assert result.publish_ready is True

    def test_blocked_result(self):
        result = PublishGateResult(
            job_id="job_001", allowed=False, publish_ready=False,
            qc_status="fail", reason="QC failed",
        )
        assert result.allowed is False
        assert result.publish_ready is False




class TestPersistenceHelpers:
    """Tests for write/load publish result helpers."""

    def test_write_and_load_publish_result(self, tmp_path):
        from src.orchestration.youtube_publisher import write_publish_result, load_publish_result
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
        from src.orchestration.youtube_publisher import load_publish_result
        result = load_publish_result(tmp_path / "nonexistent")
        assert result is None

class TestPublishMetadata:
    """Tests for publish metadata generation."""

    def test_title_from_script(self):
        script = ScriptPackage(topic="test topic", title="Script Title",
            sections=[ScriptSection(heading="Intro", narration="Some narration")])
        metadata = generate_publish_metadata(script=script, topic="fallback topic")
        assert metadata["title"] == "Script Title"

    def test_title_fallback_to_topic(self):
        metadata = generate_publish_metadata(topic="My Topic")
        assert metadata["title"] == "My Topic"

    def test_description_from_script(self):
        script = ScriptPackage(topic="test topic", title="Title",
            hook="This is a hook", call_to_action="Subscribe now",
            sections=[ScriptSection(heading="Intro", narration="First section content")])
        metadata = generate_publish_metadata(script=script, topic="fallback")
        assert "This is a hook" in metadata["description"]
        assert "Subscribe now" in metadata["description"]

    def test_tags_from_strategy(self):
        strategy = StrategyPackage(topic="test topic", angle="Test angle",
            key_messages=["AI automation", "Productivity tips", "Tech insights"])
        metadata = generate_publish_metadata(strategy=strategy, topic="AI and productivity")
        tags_lower = [t.lower() for t in metadata["tags"]]
        assert "ai_automation" in tags_lower or "ai-automation" in tags_lower
        assert len(metadata["tags"]) > 0

    def test_tags_limit(self):
        strategy = StrategyPackage(topic="test", angle="Test angle",
            key_messages=[f"message {i}" for i in range(20)])
        metadata = generate_publish_metadata(strategy=strategy, topic="test")
        assert len(metadata["tags"]) <= 10

    def test_default_visibility_private(self):
        metadata = generate_publish_metadata(topic="test")
        assert metadata["visibility"] == PublishVisibility.PRIVATE.value

    def test_valid_publish_request(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video")
        request = PublishRequest(
            job_id="job_001",
            video_path=str(video),
            title="Test Video",
            description="Test description",
            tags=["test", "video"],
            visibility=PublishVisibility.PRIVATE,
        )
        assert request.job_id == "job_001"
        assert request.title == "Test Video"
        assert request.visibility == PublishVisibility.PRIVATE

    def test_invalid_video_path(self, tmp_path):
        with pytest.raises(ValueError, match="video_path"):
            PublishRequest(job_id="job_001", video_path="/nonexistent/video.mp4", title="Test")

    def test_empty_title(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video")
        with pytest.raises(ValueError, match="title"):
            PublishRequest(job_id="job_001", video_path=str(video), title="  ")
