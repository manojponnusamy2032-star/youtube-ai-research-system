"""Tests for FinalMediaOrchestrator service."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.models.content_package import AudioRequest
from src.services.audio_renderer import AudioRenderRequest, AudioRenderer
from src.services.final_media_orchestrator import FinalMediaOrchestrator
from src.services.media_muxer import MediaMuxer
from src.services.video_assembler import VideoAssembler


def _render_outputs() -> list[dict[str, Any]]:
    """Create test render output records."""
    return [
        {
            "job_id": "job-1",
            "scene_number": 1,
            "output_reference": "scene_1.mp4",
            "status": "completed",
        },
        {
            "job_id": "job-2",
            "scene_number": 2,
            "output_reference": "scene_2.mp4",
            "status": "completed",
        },
    ]


def _audio_request() -> AudioRequest:
    """Create a test AudioRequest."""
    return AudioRequest(
        scene_number=1,
        duration_seconds=10,
        narration_text="Test narration",
    )


class FakeVideoAssembler:
    """Fake VideoAssembler for testing."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.assemble = MagicMock(return_value=result or {
            "status": "completed",
            "output_reference": "final_video.mp4",
            "total_scenes": 2,
        })


class FakeAudioRenderer(AudioRenderer):
    """Fake AudioRenderer for testing."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.render = MagicMock(return_value=result or {
            "scene_number": 1,
            "status": "completed",
            "audio_reference": "mock://audio/scene_1",
            "duration_seconds": 10,
        })


class FakeMediaMuxer:
    """Fake MediaMuxer for testing."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.mux = MagicMock(return_value=result or {
            "status": "completed",
            "output_reference": "final_with_audio.mp4",
            "video_reference": "final_video.mp4",
            "audio_reference": "mock://audio/scene_1",
        })


def test_video_assembler_is_called() -> None:
    """Test that video assembler is called."""
    fake_video = FakeVideoAssembler()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=fake_video,
        audio_renderer=FakeAudioRenderer(),
        media_muxer=FakeMediaMuxer(),
    )

    orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    fake_video.assemble.assert_called_once()


def test_audio_renderer_is_called() -> None:
    """Test that audio renderer is called."""
    fake_audio = FakeAudioRenderer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=fake_audio,
        media_muxer=FakeMediaMuxer(),
    )

    orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    fake_audio.render.assert_called_once()


def test_media_muxer_is_called() -> None:
    """Test that media muxer is called."""
    fake_muxer = FakeMediaMuxer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=fake_muxer,
    )

    orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    fake_muxer.mux.assert_called_once()


def test_correct_video_reference_reaches_muxer() -> None:
    """Test that correct video reference reaches muxer."""
    fake_video = FakeVideoAssembler(result={
        "status": "completed",
        "output_reference": "my_video.mp4",
    })
    fake_muxer = FakeMediaMuxer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=fake_video,
        audio_renderer=FakeAudioRenderer(),
        media_muxer=fake_muxer,
    )

    orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    args, _ = fake_muxer.mux.call_args
    assert args[0] == "my_video.mp4"


def test_correct_audio_reference_reaches_muxer() -> None:
    """Test that correct audio reference reaches muxer."""
    fake_audio = FakeAudioRenderer(result={
        "scene_number": 1,
        "status": "completed",
        "audio_reference": "my_audio.aac",
        "duration_seconds": 10,
    })
    fake_muxer = FakeMediaMuxer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=fake_audio,
        media_muxer=fake_muxer,
    )

    orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    args, _ = fake_muxer.mux.call_args
    assert args[1] == "my_audio.aac"


def test_final_output_path_reaches_muxer() -> None:
    """Test that final output path reaches muxer."""
    fake_muxer = FakeMediaMuxer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=fake_muxer,
    )

    orchestrator.create_final_media(_render_outputs(), [_audio_request()], "final_output.mp4")

    args, _ = fake_muxer.mux.call_args
    assert args[2] == "final_output.mp4"


def test_successful_pipeline_result() -> None:
    """Test that successful pipeline returns mux result."""
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=FakeMediaMuxer(),
    )

    result = orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    assert result["status"] == "completed"
    assert result["output_reference"] == "final_with_audio.mp4"


def test_video_failure_stops_pipeline() -> None:
    """Test that video failure stops the pipeline."""
    fake_video = FakeVideoAssembler(result={
        "status": "failed",
        "error": "Video assembly failed",
    })
    fake_audio = FakeAudioRenderer()
    fake_muxer = FakeMediaMuxer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=fake_video,
        audio_renderer=fake_audio,
        media_muxer=fake_muxer,
    )

    result = orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    assert result["status"] == "failed"
    assert result["stage"] == "video"
    assert "Video assembly failed" in result["error"]
    fake_audio.render.assert_not_called()
    fake_muxer.mux.assert_not_called()


def test_audio_failure_stops_pipeline() -> None:
    """Test that audio failure stops the pipeline."""
    fake_audio = FakeAudioRenderer(result={
        "scene_number": 1,
        "status": "failed",
        "error": "Audio render failed",
    })
    fake_muxer = FakeMediaMuxer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=fake_audio,
        media_muxer=fake_muxer,
    )

    result = orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    assert result["status"] == "failed"
    assert result["stage"] == "audio"
    assert "Audio render failed" in result["error"]
    fake_muxer.mux.assert_not_called()


def test_mux_failure_is_propagated() -> None:
    """Test that mux failure is propagated."""
    fake_muxer = FakeMediaMuxer(result={
        "status": "failed",
        "error": "Muxing failed",
    })
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=fake_muxer,
    )

    result = orchestrator.create_final_media(_render_outputs(), [_audio_request()], "output.mp4")

    assert result["status"] == "failed"
    assert result["stage"] == "mux"
    assert "Muxing failed" in result["error"]


def test_multiple_audio_requests_rejected() -> None:
    """Test that multiple audio requests are rejected."""
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=FakeMediaMuxer(),
    )

    with pytest.raises(ValueError, match="exactly one request"):
        orchestrator.create_final_media(
            _render_outputs(),
            [_audio_request(), _audio_request()],
            "output.mp4",
        )


def test_empty_render_outputs_rejected() -> None:
    """Test that empty render outputs are rejected."""
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=FakeMediaMuxer(),
    )

    with pytest.raises(ValueError, match="render_outputs cannot be empty"):
        orchestrator.create_final_media([], [_audio_request()], "output.mp4")


def test_empty_audio_requests_rejected() -> None:
    """Test that empty audio requests are rejected."""
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=FakeMediaMuxer(),
    )

    with pytest.raises(ValueError, match="audio_requests cannot be empty"):
        orchestrator.create_final_media(_render_outputs(), [], "output.mp4")


def test_empty_output_path_rejected() -> None:
    """Test that empty output path is rejected."""
    orchestrator = FinalMediaOrchestrator(
        video_assembler=FakeVideoAssembler(),
        audio_renderer=FakeAudioRenderer(),
        media_muxer=FakeMediaMuxer(),
    )

    with pytest.raises(ValueError, match="output_path cannot be empty"):
        orchestrator.create_final_media(_render_outputs(), [_audio_request()], "")


def test_injected_dependencies_are_used() -> None:
    """Test that injected dependencies are actually used."""
    fake_video = FakeVideoAssembler()
    fake_audio = FakeAudioRenderer()
    fake_muxer = FakeMediaMuxer()
    orchestrator = FinalMediaOrchestrator(
        video_assembler=fake_video,
        audio_renderer=fake_audio,
        media_muxer=fake_muxer,
    )

    assert orchestrator.video_assembler is fake_video
    assert orchestrator.audio_renderer is fake_audio
    assert orchestrator.media_muxer is fake_muxer
