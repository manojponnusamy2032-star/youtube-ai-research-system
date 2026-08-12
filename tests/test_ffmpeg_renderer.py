"""Tests for FFmpegRenderer service foundation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.render_job_executor import RenderRequest
from src.models.content_package import RenderConfig
from src.services.ffmpeg_renderer import FFmpegRenderer


def _create_request(config: RenderConfig | None = None) -> RenderRequest:
    """Create a test render request."""
    if config is None:
        config = RenderConfig()
    
    return RenderRequest(
        job={
            "job_id": "test-job",
            "scene_number": 1,
            "duration_seconds": 30,
        },
        render_config=config,
        resolved_assets=["assets/asset1"],
        resolved_characters=["assets/characters/char1"],
    )


def test_ffmpeg_availability_check_can_be_called() -> None:
    """Test that FFmpeg availability check can be called."""
    renderer = FFmpegRenderer()
    
    # Should not raise an exception
    available = renderer.is_available()
    
    # Result should be boolean
    assert isinstance(available, bool)


def test_render_config_is_used() -> None:
    """Test that RenderConfig values are used in command building."""
    renderer = FFmpegRenderer()
    config = RenderConfig(
        width=1280,
        height=720,
        fps=60,
        video_codec="prores",
        audio_format="wav",
    )
    request = _create_request(config)
    
    command = renderer.build_command(request, "output/test.mp4")
    command_str = " ".join(command)
    
    # Verify config values appear in command
    assert "1280x720" in command_str
    assert ":r=60" in command_str
    assert "prores" in command_str
    assert "wav" in command_str


def test_command_is_deterministic() -> None:
    """Test that command building is deterministic."""
    renderer = FFmpegRenderer()
    request = _create_request()
    
    command1 = renderer.build_command(request, "output/test.mp4")
    command2 = renderer.build_command(request, "output/test.mp4")
    command3 = renderer.build_command(request, "output/test.mp4")
    
    assert command1 == command2 == command3


def test_command_contains_configured_width() -> None:
    """Test that command contains configured width."""
    renderer = FFmpegRenderer()
    config = RenderConfig(width=1920, height=1080)
    request = _create_request(config)
    
    command = renderer.build_command(request, "output/test.mp4")
    command_str = " ".join(command)
    
    assert "1920x1080" in command_str


def test_command_contains_configured_height() -> None:
    """Test that command contains configured height."""
    renderer = FFmpegRenderer()
    config = RenderConfig(width=1280, height=720)
    request = _create_request(config)
    
    command = renderer.build_command(request, "output/test.mp4")
    command_str = " ".join(command)
    
    assert "1280x720" in command_str


def test_command_contains_configured_fps() -> None:
    """Test that command contains configured FPS."""
    renderer = FFmpegRenderer()
    config = RenderConfig(fps=60)
    request = _create_request(config)
    
    command = renderer.build_command(request, "output/test.mp4")
    command_str = " ".join(command)
    
    assert ":r=60" in command_str


def test_command_contains_configured_codec() -> None:
    """Test that command contains configured video codec."""
    renderer = FFmpegRenderer()
    config = RenderConfig(video_codec="libx264")
    request = _create_request(config)
    
    command = renderer.build_command(request, "output/test.mp4")
    
    assert "-c:v" in command
    codec_index = command.index("-c:v") + 1
    assert command[codec_index] == "libx264"


def test_output_path_uses_configured_output_directory() -> None:
    """Test that output path uses configured output directory."""
    renderer = FFmpegRenderer()
    config = RenderConfig(output_directory="custom_output")
    request = _create_request(config)
    
    output_path = renderer._build_output_path(config, request.job["job_id"])
    
    assert output_path.startswith("custom_output")


def test_output_path_uses_filename_template() -> None:
    """Test that output path uses filename template."""
    renderer = FFmpegRenderer()
    config = RenderConfig(filename_template="scene_{job_id}.mp4")
    request = _create_request(config)
    
    output_path = renderer._build_output_path(config, request.job["job_id"])
    
    assert "scene_test-job.mp4" in output_path


def test_unsafe_output_path_is_rejected() -> None:
    """Test that unsafe output paths are rejected."""
    renderer = FFmpegRenderer()
    config = RenderConfig()
    request = _create_request(config)
    
    # Test path traversal attempt - should raise ValueError
    with pytest.raises(ValueError):
        renderer.build_command(request, "../../../etc/passwd")
    
    with pytest.raises(ValueError):
        renderer.build_command(request, "output/../../etc/passwd")


def test_command_builder_does_not_execute_ffmpeg() -> None:
    """Test that command builder does not execute FFmpeg."""
    renderer = FFmpegRenderer()
    request = _create_request()
    
    # Mock subprocess to ensure it's not called
    with patch("subprocess.run") as mock_run, \
         patch("subprocess.Popen") as mock_popen:
        
        # Build command (should not execute)
        command = renderer.build_command(request, "output/test.mp4")
        
        # Verify no subprocess methods were called
        mock_run.assert_not_called()
        mock_popen.assert_not_called()
        
        # Verify command is returned as list
        assert isinstance(command, list)
        assert command[0] == "ffmpeg"


def test_render_request_is_accepted() -> None:
    """Test that RenderRequest is accepted by the renderer."""
    renderer = FFmpegRenderer()
    request = _create_request()
    
    # Should not raise an exception
    result = renderer.render(request)
    
    assert result["job_id"] == "test-job"
    assert result["status"] == "command_built"
    assert "command" in result
    assert "ffmpeg_available" in result
    assert result["message"] == "FFmpeg execution not yet implemented"


def test_render_returns_command_information() -> None:
    """Test that render returns command information without execution."""
    renderer = FFmpegRenderer()
    request = _create_request()
    
    result = renderer.render(request)
    
    # Verify command is included
    assert "command" in result
    assert isinstance(result["command"], list)
    assert result["command"][0] == "ffmpeg"
    
    # Verify no actual rendering occurred
    assert result["status"] == "command_built"
    assert "not yet implemented" in result["message"]


def test_default_config_produces_valid_command() -> None:
    """Test that default config produces a valid command structure."""
    renderer = FFmpegRenderer()
    config = RenderConfig()
    request = _create_request(config)
    
    command = renderer.build_command(request, "output/test.mp4")
    
    # Verify basic command structure
    assert command[0] == "ffmpeg"
    assert "-y" in command
    assert "-f" in command
    assert "-i" in command
    assert "-c:v" in command
    assert "-c:a" in command
    assert "output/test.mp4" in command


def test_custom_video_format_in_command() -> None:
    """Test that custom video format is reflected in output path."""
    renderer = FFmpegRenderer()
    config = RenderConfig(video_format="mov", output_directory="renders")
    request = _create_request(config)
    
    output_path = renderer._build_output_path(config, request.job["job_id"])
    
    # The format itself doesn't go in the command flags, but affects the output path
    assert output_path.startswith("renders")
    assert output_path.endswith(".mp4")  # Default template


def test_path_traversal_in_filename_template_is_normalized() -> None:
    """Test that path traversal in filename template is normalized safely."""
    renderer = FFmpegRenderer()
    config = RenderConfig(filename_template="../{job_id}.mp4")
    request = _create_request(config)
    
    # Build the output path - the path traversal should be normalized away
    output_path = renderer._build_output_path(config, request.job["job_id"])
    
    # The normalized path should not contain ".."
    assert ".." not in output_path
    # The path should be safe (just the filename in the output directory)
    assert "test-job.mp4" in output_path


def test_absolute_path_in_output_directory_is_accepted() -> None:
    """Test that absolute paths in output directory are accepted."""
    renderer = FFmpegRenderer()
    config = RenderConfig(output_directory="/tmp/renders")
    request = _create_request(config)
    
    output_path = renderer._build_output_path(config, request.job["job_id"])
    
    # Use Path to handle platform-specific path separators
    assert Path(output_path).parts[0] in ["/", "\\"]
    assert "tmp" in output_path
    assert "renders" in output_path


def test_render_with_failing_config_returns_error() -> None:
    """Test that render with invalid config returns error status."""
    renderer = FFmpegRenderer()
    
    # Create a request with invalid config dict (bypassing RenderConfig validation)
    request = RenderRequest(
        job={"job_id": "test-job", "duration_seconds": 30},
        render_config=RenderConfig(width=1920, height=1080),  # Valid config
    )
    
    # Manually inject invalid width to simulate a bad config
    request.render_config.width = -1920
    
    result = renderer.render(request)
    
    assert result["status"] == "failed"
    assert "error" in result
    assert "Invalid width" in result["error"]


def test_execution_disabled_preserves_current_behavior() -> None:
    """Test that execution disabled preserves current behavior."""
    renderer = FFmpegRenderer(execute_enabled=False)
    request = _create_request()
    
    result = renderer.render(request)
    
    assert result["status"] == "command_built"
    assert "command" in result
    assert "not yet implemented" in result["message"]


def test_successful_mocked_ffmpeg_execution() -> None:
    """Test successful mocked FFmpeg execution."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    # Mock subprocess.run
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    # Mock os.path.exists to return True
    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True) as mock_exists, \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["status"] == "completed"
        assert result["job_id"] == "test-job"
        assert "command" in result
        assert mock_run.called
        # Verify shell=False
        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False


def test_correct_command_passed_to_subprocess() -> None:
    """Test that correct command is passed to subprocess."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    config = RenderConfig(width=1920, height=1080, fps=30)
    request = _create_request(config)
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert mock_run.called
        command = mock_run.call_args[0][0]
        assert command[0] == "ffmpeg"
        assert "1920x1080" in " ".join(command)
        assert ":r=30" in " ".join(command)


def test_shell_false_behavior() -> None:
    """Test that shell=False is used for security."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        renderer.render(request)
        
        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False


def test_ffmpeg_unavailable_returns_error() -> None:
    """Test that unavailable FFmpeg returns error."""
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    with patch("shutil.which", return_value=None):
        result = renderer.render(request)
        
        assert result["status"] == "failed"
        assert "not available" in result["error"]


def test_non_zero_return_code_returns_failure() -> None:
    """Test that non-zero FFmpeg return code returns failure."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = "Error: invalid argument"
    
    with patch("subprocess.run", return_value=mock_process), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["status"] == "failed"
        assert "return code 1" in result["error"]


def test_subprocess_exception_returns_failure() -> None:
    """Test that subprocess exception returns failure."""
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    with patch("subprocess.run", side_effect=OSError("Mocked subprocess error")), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["status"] == "failed"
        assert "execution failed" in result["error"]


def test_timeout_returns_failure() -> None:
    """Test that timeout returns failure."""
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["status"] == "failed"
        assert "timed out" in result["error"]


def test_successful_process_but_missing_output_file() -> None:
    """Test that successful process but missing output file returns failure."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["status"] == "failed"
        assert "output file not found" in result["error"]


def test_successful_process_with_output_file() -> None:
    """Test that successful process with output file returns completed."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["status"] == "completed"
        assert result["return_code"] == 0
        assert "execution_time_seconds" in result


def test_output_reference_is_correct() -> None:
    """Test that output reference is correct."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    config = RenderConfig(output_directory="renders", filename_template="{job_id}.mp4")
    request = _create_request(config)
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        # Use Path to handle platform-specific separators
        assert Path(result["output_reference"]) == Path("renders/test-job.mp4")


def test_result_contains_job_id() -> None:
    """Test that result contains job_id."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    request = _create_request()
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["job_id"] == "test-job"


def test_renderer_does_not_execute_when_disabled() -> None:
    """Test that renderer does not execute when disabled."""
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=False)
    request = _create_request()
    
    mock_process = MagicMock()
    
    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        result = renderer.render(request)
        
        assert result["status"] == "command_built"
        mock_run.assert_not_called()


def test_scene_duration_is_respected() -> None:
    """Test that scene duration is included in command."""
    renderer = FFmpegRenderer()
    config = RenderConfig()
    request = _create_request(config)
    
    # Set duration in job
    request.job["duration_seconds"] = 5
    
    command = renderer.build_command(request, "output/test.mp4")
    command_str = " ".join(command)
    
    # Duration should appear in lavfi input string
    assert ":d=5" in command_str


def test_zero_duration_uses_default() -> None:
    """Test that zero duration uses default of 1 second."""
    renderer = FFmpegRenderer()
    config = RenderConfig()
    request = _create_request(config)
    
    # Set zero duration
    request.job["duration_seconds"] = 0
    
    command = renderer.build_command(request, "output/test.mp4")
    command_str = " ".join(command)
    
    # Should use 1 second default in lavfi input
    assert ":d=1" in command_str


def test_negative_duration_raises_error() -> None:
    """Test that negative duration raises error."""
    renderer = FFmpegRenderer()
    config = RenderConfig()
    request = _create_request(config)
    
    # Set negative duration
    request.job["duration_seconds"] = -5
    
    with pytest.raises(ValueError, match="Invalid duration"):
        renderer.build_command(request, "output/test.mp4")


def test_unsupported_render_type_raises_error() -> None:
    """Test that unsupported render type raises error."""
    renderer = FFmpegRenderer()
    config = RenderConfig()
    request = _create_request(config)
    
    # Set unsupported render type
    request.job["render_type"] = "unsupported_type"
    
    with pytest.raises(ValueError, match="Unsupported render type"):
        renderer.build_command(request, "output/test.mp4")


def test_supported_render_types_are_accepted() -> None:
    """Test that all supported render types are accepted."""
    renderer = FFmpegRenderer()
    config = RenderConfig()
    
    supported_types = ["host_footage", "b-roll", "screen_capture", "comparison", "end_screen"]
    
    for render_type in supported_types:
        request = _create_request(config)
        request.job["render_type"] = render_type
        
        # Should not raise
        command = renderer.build_command(request, "output/test.mp4")
        assert isinstance(command, list)
        assert command[0] == "ffmpeg"


def test_render_request_fields_are_accessible() -> None:
    """Test that RenderRequest fields are accessible in renderer."""
    renderer = FFmpegRenderer()
    config = RenderConfig(width=1280, height=720)
    request = _create_request(config)
    
    # Set various job fields
    request.job["render_type"] = "b-roll"
    request.job["animation_instructions"] = "fade in"
    request.job["camera_instructions"] = "pan left"
    request.job["visual_prompt"] = "Scene description"
    
    # Should be able to build command without errors
    command = renderer.build_command(request, "output/test.mp4")
    assert isinstance(command, list)
