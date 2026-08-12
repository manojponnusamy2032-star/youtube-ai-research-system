"""Tests for VideoAssembler service."""

from __future__ import annotations

import os
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.models.content_package import RenderConfig
from src.services.video_assembler import VideoAssembler


def _create_output(
    job_id: str,
    scene_number: int,
    status: str = "completed",
    output_ref: str | None = None,
) -> dict[str, Any]:
    """Create a test render output record."""
    if output_ref is None:
        output_ref = f"output/scene_{scene_number}.mp4"

    return {
        "output_id": f"output_{job_id}",
        "job_id": job_id,
        "scene_number": scene_number,
        "status": status,
        "output_reference": output_ref,
        "duration_seconds": 10,
    }


# --- Command-building tests (execution disabled) ---


def test_scenes_are_sorted_by_scene_number() -> None:
    """Test that scenes are sorted by scene_number."""
    assembler = VideoAssembler()

    outputs = [
        _create_output("job-3", 3),
        _create_output("job-1", 1),
        _create_output("job-2", 2),
    ]

    result = assembler.assemble(outputs)

    assert result["status"] == "command_built"
    assert result["total_scenes"] == 3

    concat_content = result["concat_content"]
    assert concat_content.index("scene_1") < concat_content.index("scene_2")
    assert concat_content.index("scene_2") < concat_content.index("scene_3")


def test_multiple_scenes_create_correct_concat_command() -> None:
    """Test that multiple scenes create correct concat command."""
    assembler = VideoAssembler()

    outputs = [
        _create_output("job-1", 1, output_ref="scene_1.mp4"),
        _create_output("job-2", 2, output_ref="scene_2.mp4"),
    ]

    result = assembler.assemble(outputs)

    assert result["status"] == "command_built"
    command = result["command"]

    assert "-f" in command
    assert "concat" in command
    assert "-safe" in command
    assert "0" in command
    assert "-c:v" in command
    assert "-movflags" in command
    assert "+faststart" in command
    assert command[-1] == result["output_reference"]


def test_empty_list_rejected() -> None:
    """Test that empty list is rejected."""
    assembler = VideoAssembler()

    with pytest.raises(ValueError, match="cannot be empty"):
        assembler.assemble([])


def test_failed_scene_rejected() -> None:
    """Test that failed scene is rejected."""
    assembler = VideoAssembler()

    outputs = [
        _create_output("job-1", 1, status="failed"),
        _create_output("job-2", 2, status="completed"),
    ]

    with pytest.raises(ValueError, match="not completed"):
        assembler.assemble(outputs)


def test_missing_scene_number_rejected() -> None:
    """Test that missing scene_number is rejected."""
    assembler = VideoAssembler()

    output = _create_output("job-1", 1)
    del output["scene_number"]

    with pytest.raises(ValueError, match="missing scene_number"):
        assembler.assemble([output])


def test_duplicate_scene_number_rejected() -> None:
    """Test that duplicate scene numbers are rejected."""
    assembler = VideoAssembler()

    outputs = [
        _create_output("job-1", 1),
        _create_output("job-2", 1),
    ]

    with pytest.raises(ValueError, match="Duplicate scene_number"):
        assembler.assemble(outputs)


def test_missing_output_reference_rejected() -> None:
    """Test that missing output reference is rejected."""
    assembler = VideoAssembler()

    outputs = [_create_output("job-1", 1, output_ref="")]

    with pytest.raises(ValueError, match="missing output_reference"):
        assembler.assemble(outputs)


def test_deterministic_command_generation() -> None:
    """Test that command generation is deterministic."""
    assembler = VideoAssembler()

    outputs = [
        _create_output("job-1", 1, output_ref="scene_1.mp4"),
        _create_output("job-2", 2, output_ref="scene_2.mp4"),
    ]

    result1 = assembler.assemble(outputs)
    result2 = assembler.assemble(outputs)

    assert result1["command"] == result2["command"]
    assert result1["concat_content"] == result2["concat_content"]
    assert result1["output_reference"] == result2["output_reference"]


def test_render_config_output_directory_used() -> None:
    """Test that RenderConfig output directory is used."""
    config = RenderConfig(output_directory="final_output")
    assembler = VideoAssembler(config=config)

    outputs = [_create_output("job-1", 1)]

    result = assembler.assemble(outputs)

    assert result["status"] == "command_built"
    assert result["output_reference"].startswith("final_output")
    assert result["output_reference"].endswith("final_video.mp4")


def test_video_codec_included() -> None:
    """Test that video codec is included in the concat command."""
    config = RenderConfig(video_codec="libx264")
    assembler = VideoAssembler(config=config)

    outputs = [_create_output("job-1", 1)]

    result = assembler.assemble(outputs)

    command = result["command"]
    assert "-c:v" in command
    idx = command.index("-c:v")
    assert command[idx + 1] == "libx264"


def test_non_list_input_rejected() -> None:
    """Test that non-list input is rejected."""
    assembler = VideoAssembler()

    with pytest.raises(ValueError, match="must be a list"):
        assembler.assemble("not a list")  # type: ignore[arg-type]


def test_video_format_used_in_output_path() -> None:
    """Test that video format is used in the output path."""
    config = RenderConfig(video_format="mkv")
    assembler = VideoAssembler(config=config)

    outputs = [_create_output("job-1", 1)]

    result = assembler.assemble(outputs)

    assert result["output_reference"].endswith("final_video.mkv")


# --- Execution tests (mocked) ---


def test_execution_disabled_by_default() -> None:
    """Test that execution is disabled by default."""
    assembler = VideoAssembler()
    assert assembler.execute_enabled is False


def test_execution_disabled_returns_command_built() -> None:
    """Test that disabled execution preserves command-building behavior."""
    assembler = VideoAssembler(execute_enabled=False)

    outputs = [_create_output("job-1", 1)]

    result = assembler.assemble(outputs)

    assert result["status"] == "command_built"
    assert "command" in result
    assert "concat_content" in result
    assert result["ffmpeg_available"] is not None


def test_successful_execution() -> None:
    """Test successful execution with mocked subprocess."""
    assembler = VideoAssembler(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    outputs = [_create_output("job-1", 1)]

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = assembler.assemble(outputs)

        assert result["status"] == "completed"
        assert result["assembled_scenes"] == 1
        assert result["total_scenes"] == 1
        assert "output_reference" in result
        assert "execution_time_seconds" in result
        assert mock_run.called


def test_subprocess_command_correct() -> None:
    """Test that the correct subprocess command is used."""
    assembler = VideoAssembler(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    outputs = [
        _create_output("job-1", 1, output_ref="scene_1.mp4"),
        _create_output("job-2", 2, output_ref="scene_2.mp4"),
    ]

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        assembler.assemble(outputs)

        # Verify the command passed to subprocess.run
        args, kwargs = mock_run.call_args
        command = args[0]

        assert command[0] == "ffmpeg"
        assert "-f" in command
        assert "concat" in command
        assert "-c:v" in command


def test_shell_false() -> None:
    """Test that subprocess.run is called with shell=False."""
    assembler = VideoAssembler(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    outputs = [_create_output("job-1", 1)]

    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        assembler.assemble(outputs)

        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False


def test_ffmpeg_nonzero_return_code() -> None:
    """Test that FFmpeg non-zero return code is handled."""
    assembler = VideoAssembler(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = "Some error"

    outputs = [_create_output("job-1", 1)]

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = assembler.assemble(outputs)

        assert result["status"] == "failed"
        assert "return code 1" in result["error"]


def test_ffmpeg_timeout() -> None:
    """Test that FFmpeg timeout is handled."""
    assembler = VideoAssembler(execute_enabled=True)

    outputs = [_create_output("job-1", 1)]

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = assembler.assemble(outputs)

        assert result["status"] == "failed"
        assert "timed out" in result["error"]


def test_subprocess_exception() -> None:
    """Test that subprocess exception is handled."""
    import subprocess as sp

    assembler = VideoAssembler(execute_enabled=True)

    outputs = [_create_output("job-1", 1)]

    with patch("subprocess.run", side_effect=sp.SubprocessError("Something broke")), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = assembler.assemble(outputs)

        assert result["status"] == "failed"
        assert "Assembly failed" in result["error"]


def test_missing_output_file() -> None:
    """Test that missing output file is handled."""
    assembler = VideoAssembler(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    outputs = [_create_output("job-1", 1)]

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = assembler.assemble(outputs)

        assert result["status"] == "failed"
        assert "output file not found" in result["error"]


def test_empty_output_file() -> None:
    """Test that empty output file is handled."""
    assembler = VideoAssembler(execute_enabled=True)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    outputs = [_create_output("job-1", 1)]

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=0), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = assembler.assemble(outputs)

        assert result["status"] == "failed"
        assert "empty" in result["error"]


def test_successful_output_reference() -> None:
    """Test that successful execution returns correct output reference."""
    assembler = VideoAssembler(execute_enabled=True)
    config = RenderConfig(output_directory="/tmp/test_out")
    assembler.config = config

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""

    outputs = [_create_output("job-1", 1)]

    expected_path = os.path.normpath("/tmp/test_out/final_video.mp4")

    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=1000), \
         patch("os.makedirs", return_value=None), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):

        result = assembler.assemble(outputs)

        assert result["output_reference"] == expected_path
