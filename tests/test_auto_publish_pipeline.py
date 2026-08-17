"""Tests for the auto-publish pipeline."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.auto_publish_pipeline import (
    AutoPublishPipeline,
    ScenePlan,
    VideoPlan,
)


class _StubTTS:
    """TTS stub returning a fixed duration per scene."""

    def __init__(self, status: str = "completed") -> None:
        self.status = status
        self.texts: list[str] = []

    def generate(self, request: Any) -> dict[str, Any]:
        self.texts.append(request.text)
        if self.status != "completed":
            return {"status": "failed", "error": "no voice model"}
        return {
            "status": "completed",
            "audio_reference": f"/tmp/audio_{len(self.texts)}.wav",
            "duration_seconds": 3.0,
        }


class _StubRenderer:
    """Scene renderer stub recording its calls."""

    def __init__(self, status: str = "completed") -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def render_scene(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.status != "completed":
            return {"status": "failed", "error": "ffmpeg failed"}
        return {
            "status": "completed",
            "job_id": f"scene-{kwargs['scene_number']}",
            "scene_number": kwargs["scene_number"],
            "output_reference": f"/tmp/scene_{kwargs['scene_number']}.mp4",
            "duration_seconds": kwargs["duration_seconds"],
        }


def _plan(video_format: str = "shorts") -> VideoPlan:
    """Build a two-scene plan."""
    return VideoPlan(
        title="Test Video",
        description="Body",
        tags=["ai"],
        video_format=video_format,
        scenes=[ScenePlan(narration="First line"), ScenePlan(narration="Second line")],
    )


def _pipeline(tmp_path, tts: Any, renderer: Any, upload_service: Any = None):
    """Build a pipeline with stubbed collaborators."""
    muxer = MagicMock()
    muxer.mux.return_value = {"status": "completed"}
    pipeline = AutoPublishPipeline(
        output_directory=str(tmp_path / "publish"),
        tts_service=tts,
        scene_renderer=renderer,
        upload_service=upload_service,
        muxer=muxer,
    )
    return pipeline, muxer


def test_scene_plan_defaults_caption_to_narration() -> None:
    """A scene without a caption displays its narration."""
    assert ScenePlan(narration="Hello").display_caption == "Hello"


def test_scene_plan_rejects_empty_narration() -> None:
    """Blank narration is rejected."""
    with pytest.raises(ValueError):
        ScenePlan(narration="   ")


def test_video_plan_validation() -> None:
    """Titles, scenes and formats are validated."""
    with pytest.raises(ValueError):
        VideoPlan(title=" ", scenes=[ScenePlan(narration="a")])
    with pytest.raises(ValueError):
        VideoPlan(title="Title", scenes=[])
    with pytest.raises(ValueError):
        VideoPlan(
            title="Title", scenes=[ScenePlan(narration="a")], video_format="square"
        )


def test_video_plan_from_file(tmp_path) -> None:
    """A plan round-trips from JSON."""
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "title": "Title",
                "video_format": "long",
                "scenes": [{"narration": "Hello", "caption": "Hi"}],
            }
        ),
        encoding="utf-8",
    )

    plan = VideoPlan.from_file(str(path))

    assert plan.format.width == 1920
    assert plan.scenes[0].display_caption == "Hi"


def test_run_renders_scenes_matching_narration(tmp_path) -> None:
    """Each scene clip is at least as long as its narration."""
    tts, renderer = _StubTTS(), _StubRenderer()
    pipeline, muxer = _pipeline(tmp_path, tts, renderer)

    with patch.object(
        AutoPublishPipeline,
        "_assemble",
        return_value={"status": "completed", "output_reference": "/tmp/silent.mp4"},
    ), patch.object(
        AutoPublishPipeline,
        "_concat_audio",
        return_value={"status": "completed", "audio_reference": "/tmp/all.wav"},
    ):
        result = pipeline.run(_plan())

    assert result["status"] == "completed"
    assert result["scene_count"] == 2
    assert result["duration_seconds"] == 6.0
    assert [call["duration_seconds"] for call in renderer.calls] == [3.4, 3.4]
    assert muxer.mux.called


def test_run_uses_requested_format(tmp_path) -> None:
    """Long-form plans render with landscape geometry."""
    tts, renderer = _StubTTS(), _StubRenderer()
    pipeline, _ = _pipeline(tmp_path, tts, renderer)

    with patch.object(
        AutoPublishPipeline,
        "_assemble",
        return_value={"status": "completed", "output_reference": "/tmp/silent.mp4"},
    ), patch.object(
        AutoPublishPipeline,
        "_concat_audio",
        return_value={"status": "completed", "audio_reference": "/tmp/all.wav"},
    ):
        pipeline.run(_plan("long"))

    assert renderer.calls[0]["video_format"].width == 1920


def test_run_fails_when_narration_fails(tmp_path) -> None:
    """A TTS failure stops the run before rendering."""
    renderer = _StubRenderer()
    pipeline, _ = _pipeline(tmp_path, _StubTTS(status="failed"), renderer)

    result = pipeline.run(_plan())

    assert result["status"] == "failed"
    assert result["stage"] == "narration"
    assert renderer.calls == []


def test_run_fails_when_scene_render_fails(tmp_path) -> None:
    """A scene render failure is surfaced with its stage."""
    pipeline, _ = _pipeline(tmp_path, _StubTTS(), _StubRenderer(status="failed"))

    result = pipeline.run(_plan())

    assert result["status"] == "failed"
    assert result["stage"] == "scene_render"


def test_run_uploads_when_requested(tmp_path) -> None:
    """Upload is delegated to the upload service with plan metadata."""
    upload_service = MagicMock()
    upload_service.upload.return_value = {
        "status": "completed",
        "video_id": "abc",
        "video_url": "https://www.youtube.com/watch?v=abc",
    }
    pipeline, _ = _pipeline(tmp_path, _StubTTS(), _StubRenderer(), upload_service)
    video_path = tmp_path / "publish" / "final_with_audio.mp4"
    os.makedirs(video_path.parent, exist_ok=True)
    video_path.write_bytes(b"mp4")

    with patch.object(
        AutoPublishPipeline,
        "_assemble",
        return_value={"status": "completed", "output_reference": "/tmp/silent.mp4"},
    ), patch.object(
        AutoPublishPipeline,
        "_concat_audio",
        return_value={"status": "completed", "audio_reference": "/tmp/all.wav"},
    ):
        result = pipeline.run(_plan(), upload=True)

    assert result["status"] == "completed"
    assert result["upload"]["video_id"] == "abc"
    request = upload_service.upload.call_args[0][0]
    assert request.title == "Test Video"
    assert request.privacy_status == "public"


def test_run_reports_upload_failure(tmp_path) -> None:
    """An upload exception marks the run as failed."""
    upload_service = MagicMock()
    upload_service.upload.side_effect = RuntimeError("quota exceeded")
    pipeline, _ = _pipeline(tmp_path, _StubTTS(), _StubRenderer(), upload_service)
    video_path = tmp_path / "publish" / "final_with_audio.mp4"
    os.makedirs(video_path.parent, exist_ok=True)
    video_path.write_bytes(b"mp4")

    with patch.object(
        AutoPublishPipeline,
        "_assemble",
        return_value={"status": "completed", "output_reference": "/tmp/silent.mp4"},
    ), patch.object(
        AutoPublishPipeline,
        "_concat_audio",
        return_value={"status": "completed", "audio_reference": "/tmp/all.wav"},
    ):
        result = pipeline.run(_plan(), upload=True)

    assert result["status"] == "failed"
    assert "quota exceeded" in result["upload"]["error"]
