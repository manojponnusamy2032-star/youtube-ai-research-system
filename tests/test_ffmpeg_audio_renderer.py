"""Tests for FFmpegAudioRenderer service."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.models.content_package import AudioRequest
from src.services.audio_renderer import AudioRenderRequest
from src.services.ffmpeg_audio_renderer import FFmpegAudioRenderer


def _audio_request(scene_number: int = 1, duration_seconds: int = 10) -> AudioRequest:
    """Create a test AudioRequest."""
    return AudioRequest(
        scene_number=scene_number,
        duration_seconds=duration_seconds,
        narration_text="Test narration",
    )


def _request(scene_number: int = 1, duration_seconds: int = 10) -> AudioRenderRequest:
    """Create a test AudioRenderRequest."""
    return AudioRenderRequest(audio_request=_audio_request(scene_number, duration_seconds))


def test_audio_render_request_accepted() -> None:
    """Test that AudioRenderRequest is accepted."""
    renderer = FFmpegAudioRenderer()
    request = _request()

    result = renderer.render(request)

    assert result["status"] == "command_built"
    assert result["scene_number"] == 1


def test_duration_included_in_command() -> None:
    """Test that duration is included in the command."""
    renderer = FFmpegAudioRenderer()
    request = _request(duration_seconds=15)

    result = renderer.render(request)

    command = result["command"]
    assert any("duration=15" in arg for arg in command)


def test_audio_format_included() -> None:
    """Test that audio format is included in the output path."""
    renderer = FFmpegAudioRenderer()
    request = _request()

    result = renderer.render(request)

    assert result["audio_reference"].endswith(".aac")


def test_deterministic_command() -> None:
    """Test that command generation is deterministic."""
    renderer = FFmpegAudioRenderer()
    request = _request()

    result1 = renderer.render(request)
    result2 = renderer.render(request)

    assert result1["command"] == result2["command"]


def test_output_path_deterministic() -> None:
    """Test that output path is deterministic."""
    renderer = FFmpegAudioRenderer(output_directory="audio_out")
    request = _request(scene_number=3)

    result1 = renderer.render(request)
    result2 = renderer.render(request)

    assert result1["audio_reference"] == result2["audio_reference"]
    assert "audio_out" in result1["audio_reference"]
    assert "audio_scene_3.aac" in result1["audio_reference"]


def test_execution_disabled() -> None:
    """Test that execution is disabled by default."""
    renderer = FFmpegAudioRenderer()
    assert renderer.execute_enabled is False

    request = _request()
    result = renderer.render(request)

    assert result["status"] == "command_built"
    assert "command" in result
    assert result["ffmpeg_available"] is not None


def test_successful_mocked_execution() -> None:
    """Test successful execution with mocked subprocess."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    request = _request()

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = renderer.render(request)

        assert result["status"] == "completed"
        assert "audio_reference" in result
        assert "execution_time_seconds" in result
        assert mock_run.called


def test_correct_subprocess_command() -> None:
    """Test that the correct subprocess command is used."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    request = _request()

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        renderer.render(request)

        args, _ = mock_run.call_args
        command = args[0]

        assert command[0] == "ffmpeg"
        assert "-f" in command
        assert "lavfi" in command
        assert "-c:a" in command


def test_shell_false() -> None:
    """Test that subprocess.run is called with shell=False."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    request = _request()

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        renderer.render(request)

        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False


def test_ffmpeg_unavailable() -> None:
    """Test that unavailable FFmpeg is handled."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)
    request = _request()

    with patch("shutil.which", return_value=None):
        result = renderer.render(request)

        assert result["status"] == "failed"
        assert "not available" in result["error"]


def test_nonzero_ffmpeg_return() -> None:
    """Test that non-zero FFmpeg return code is handled."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = "Some error"

    request = _request()

    with patch("subprocess.run", return_value=mock_process), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = renderer.render(request)

        assert result["status"] == "failed"
        assert "return code 1" in result["error"]


def test_timeout() -> None:
    """Test that FFmpeg timeout is handled."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)
    request = _request()

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = renderer.render(request)

        assert result["status"] == "failed"
        assert "timed out" in result["error"]


def test_subprocess_exception() -> None:
    """Test that subprocess exception is handled."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)
    request = _request()

    with patch("subprocess.run", side_effect=subprocess.SubprocessError("Broke")), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = renderer.render(request)

        assert result["status"] == "failed"
        assert "Audio rendering failed" in result["error"]


def test_missing_output_file() -> None:
    """Test that missing output file is handled."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    request = _request()

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = renderer.render(request)

        assert result["status"] == "failed"
        assert "output file not found" in result["error"]


def test_empty_output_file() -> None:
    """Test that empty output file is handled."""
    renderer = FFmpegAudioRenderer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    request = _request()

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=0), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = renderer.render(request)

        assert result["status"] == "failed"
        assert "empty" in result["error"]


def test_successful_output_reference() -> None:
    """Test that successful execution returns correct output reference."""
    renderer = FFmpegAudioRenderer(output_directory="audio_out", execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    request = _request(scene_number=2)

    expected_path = "audio_out/audio_scene_2.aac"

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = renderer.render(request)

        assert result["audio_reference"].endswith("audio_scene_2.aac")
        assert "audio_out" in result["audio_reference"]