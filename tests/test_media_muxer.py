"""Tests for MediaMuxer service."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.services.media_muxer import MediaMuxer


def test_empty_video_rejected() -> None:
    """Test that empty video reference is rejected."""
    muxer = MediaMuxer()

    with pytest.raises(ValueError, match="video_reference cannot be empty"):
        muxer.build_command("", "audio.aac", "output.mp4")


def test_empty_audio_rejected() -> None:
    """Test that empty audio reference is rejected."""
    muxer = MediaMuxer()

    with pytest.raises(ValueError, match="audio_reference cannot be empty"):
        muxer.build_command("video.mp4", "", "output.mp4")


def test_empty_output_rejected() -> None:
    """Test that empty output path is rejected."""
    muxer = MediaMuxer()

    with pytest.raises(ValueError, match="output_path cannot be empty"):
        muxer.build_command("video.mp4", "audio.aac", "")


def test_deterministic_command() -> None:
    """Test that command generation is deterministic."""
    muxer = MediaMuxer()

    cmd1 = muxer.build_command("video.mp4", "audio.aac", "output.mp4")
    cmd2 = muxer.build_command("video.mp4", "audio.aac", "output.mp4")

    assert cmd1 == cmd2


def test_video_input_included() -> None:
    """Test that video input is included in the command."""
    muxer = MediaMuxer()

    command = muxer.build_command("video.mp4", "audio.aac", "output.mp4")

    assert "-i" in command
    idx = command.index("-i")
    assert command[idx + 1] == "video.mp4"


def test_audio_input_included() -> None:
    """Test that audio input is included in the command."""
    muxer = MediaMuxer()

    command = muxer.build_command("video.mp4", "audio.aac", "output.mp4")

    # Second -i should be the audio
    indices = [i for i, arg in enumerate(command) if arg == "-i"]
    assert len(indices) == 2
    assert command[indices[1] + 1] == "audio.aac"


def test_c_v_copy_included() -> None:
    """Test that -c:v copy is included in the command."""
    muxer = MediaMuxer()

    command = muxer.build_command("video.mp4", "audio.aac", "output.mp4")

    assert "-c:v" in command
    idx = command.index("-c:v")
    assert command[idx + 1] == "copy"


def test_aac_audio_codec_included() -> None:
    """Test that AAC audio codec is included in the command."""
    muxer = MediaMuxer()

    command = muxer.build_command("video.mp4", "audio.aac", "output.mp4")

    assert "-c:a" in command
    idx = command.index("-c:a")
    assert command[idx + 1] == "aac"


def test_shortest_included() -> None:
    """Test that -shortest is included in the command."""
    muxer = MediaMuxer()

    command = muxer.build_command("video.mp4", "audio.aac", "output.mp4")

    assert "-shortest" in command


def test_execution_disabled() -> None:
    """Test that execution is disabled by default."""
    muxer = MediaMuxer()
    assert muxer.execute_enabled is False

    result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

    assert result["status"] == "command_built"
    assert "command" in result
    assert result["output_reference"] == "output.mp4"
    assert result["video_reference"] == "video.mp4"
    assert result["audio_reference"] == "audio.aac"


def test_successful_mocked_execution() -> None:
    """Test successful execution with mocked subprocess."""
    muxer = MediaMuxer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

        assert result["status"] == "completed"
        assert "output_reference" in result
        assert "execution_time_seconds" in result
        assert mock_run.called


def test_shell_false() -> None:
    """Test that subprocess.run is called with shell=False."""
    muxer = MediaMuxer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        muxer.mux("video.mp4", "audio.aac", "output.mp4")

        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False


def test_ffmpeg_unavailable() -> None:
    """Test that unavailable FFmpeg is handled."""
    muxer = MediaMuxer(execute_enabled=True)

    with patch("shutil.which", return_value=None):
        result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

        assert result["status"] == "failed"
        assert "not available" in result["error"]


def test_nonzero_return_code() -> None:
    """Test that non-zero return code is handled."""
    muxer = MediaMuxer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = "Error"

    with patch("subprocess.run", return_value=mock_process), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

        assert result["status"] == "failed"
        assert "return code 1" in result["error"]


def test_timeout() -> None:
    """Test that FFmpeg timeout is handled."""
    muxer = MediaMuxer(execute_enabled=True)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

        assert result["status"] == "failed"
        assert "timed out" in result["error"]


def test_subprocess_exception() -> None:
    """Test that subprocess exception is handled."""
    muxer = MediaMuxer(execute_enabled=True)

    with patch("subprocess.run", side_effect=subprocess.SubprocessError("Broke")), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

        assert result["status"] == "failed"
        assert "Muxing failed" in result["error"]


def test_missing_output_file() -> None:
    """Test that missing output file is handled."""
    muxer = MediaMuxer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

        assert result["status"] == "failed"
        assert "output file not found" in result["error"]


def test_empty_output_file() -> None:
    """Test that empty output file is handled."""
    muxer = MediaMuxer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=0), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = muxer.mux("video.mp4", "audio.aac", "output.mp4")

        assert result["status"] == "failed"
        assert "empty" in result["error"]


def test_successful_output_reference() -> None:
    """Test that successful execution returns correct output reference."""
    muxer = MediaMuxer(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = muxer.mux("video.mp4", "audio.aac", "final_output.mp4")

        assert result["output_reference"] == "final_output.mp4"
        assert result["video_reference"] == "video.mp4"
        assert result["audio_reference"] == "audio.aac"