"""Tests for AudioRenderer service abstraction."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models.content_package import AudioRequest
from src.services.audio_renderer import (
    AudioRenderRequest,
    AudioRenderer,
    MockAudioRenderer,
)


def _audio_request(scene_number: int = 1, duration_seconds: int = 10) -> AudioRequest:
    """Create a test AudioRequest."""
    return AudioRequest(
        scene_number=scene_number,
        duration_seconds=duration_seconds,
        narration_text="Test narration",
    )


def test_audio_render_request_creation() -> None:
    """Test AudioRenderRequest creation."""
    audio = _audio_request()
    request = AudioRenderRequest(audio_request=audio)

    assert request.audio_request is audio
    assert request.job == {}


def test_audio_render_request_with_job() -> None:
    """Test AudioRenderRequest with an associated job."""
    audio = _audio_request()
    job = {"job_id": "job-1"}
    request = AudioRenderRequest(audio_request=audio, job=job)

    assert request.audio_request is audio
    assert request.job == {"job_id": "job-1"}


def test_audio_request_reaches_renderer() -> None:
    """Test that AudioRequest reaches the renderer."""
    renderer = MockAudioRenderer()
    audio = _audio_request(scene_number=5, duration_seconds=30)
    request = AudioRenderRequest(audio_request=audio)

    result = renderer.render(request)

    assert result["scene_number"] == 5
    assert result["duration_seconds"] == 30


def test_mock_audio_renderer_deterministic_output() -> None:
    """Test that MockAudioRenderer produces deterministic output."""
    renderer = MockAudioRenderer()
    audio = _audio_request(scene_number=1)
    request = AudioRenderRequest(audio_request=audio)

    result = renderer.render(request)

    assert result["audio_reference"] == "mock://audio/scene_1"


def test_scene_number_included() -> None:
    """Test that scene number is included in result."""
    renderer = MockAudioRenderer()
    audio = _audio_request(scene_number=7)
    request = AudioRenderRequest(audio_request=audio)

    result = renderer.render(request)

    assert result["scene_number"] == 7


def test_duration_included() -> None:
    """Test that duration is included in result."""
    renderer = MockAudioRenderer()
    audio = _audio_request(scene_number=1, duration_seconds=45)
    request = AudioRenderRequest(audio_request=audio)

    result = renderer.render(request)

    assert result["duration_seconds"] == 45


def test_successful_status() -> None:
    """Test that successful render returns completed status."""
    renderer = MockAudioRenderer()
    audio = _audio_request()
    request = AudioRenderRequest(audio_request=audio)

    result = renderer.render(request)

    assert result["status"] == "completed"


def test_repeated_render_same_reference() -> None:
    """Test that repeated renders produce the same reference."""
    renderer = MockAudioRenderer()
    audio = _audio_request(scene_number=3)
    request = AudioRenderRequest(audio_request=audio)

    result1 = renderer.render(request)
    result2 = renderer.render(request)

    assert result1["audio_reference"] == result2["audio_reference"]
    assert result1["audio_reference"] == "mock://audio/scene_3"


def test_missing_request_handled() -> None:
    """Test that a missing request is handled."""
    renderer = MockAudioRenderer()

    with pytest.raises(ValueError, match="cannot be None"):
        renderer.render(None)  # type: ignore[arg-type]


def test_invalid_scene_request_handled() -> None:
    """Test that an invalid scene request is handled."""
    renderer = MockAudioRenderer()

    # AudioRequest itself validates scene_number > 0, so simulate an invalid
    # request by constructing one with scene_number 0 (raises at construction).
    with pytest.raises(ValueError, match="scene_number must be positive"):
        AudioRequest(scene_number=0)


def test_no_external_calls_made() -> None:
    """Test that no external calls are made during mock rendering."""
    renderer = MockAudioRenderer()
    audio = _audio_request()
    request = AudioRenderRequest(audio_request=audio)

    with patch("subprocess.run") as mock_subprocess, \
         patch("shutil.which") as mock_which:
        result = renderer.render(request)

        mock_subprocess.assert_not_called()
        mock_which.assert_not_called()

    assert result["status"] == "completed"


def test_abstract_renderer_raises_not_implemented() -> None:
    """Test that the abstract AudioRenderer raises NotImplementedError."""
    renderer = AudioRenderer()
    audio = _audio_request()
    request = AudioRenderRequest(audio_request=audio)

    with pytest.raises(NotImplementedError):
        renderer.render(request)