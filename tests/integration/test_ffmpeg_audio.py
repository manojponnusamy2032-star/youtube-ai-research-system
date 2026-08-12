"""Integration smoke test for real FFmpeg audio rendering.

This test verifies that FFmpegAudioRenderer can produce a real audio file
using FFmpeg's built-in sine source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models.content_package import AudioRequest
from src.services.audio_renderer import AudioRenderRequest
from src.services.ffmpeg_audio_renderer import FFmpegAudioRenderer


@pytest.mark.integration
def test_real_ffmpeg_audio_renderer_produces_audio_file(tmp_path: Path) -> None:
    """Verify FFmpegAudioRenderer produces a real audio file.

    Creates a short deterministic audio file using FFmpegAudioRenderer
    with execute_enabled=True, and verifies the file exists and is
    non-empty.

    Args:
        tmp_path: Pytest temporary directory fixture
    """
    renderer = FFmpegAudioRenderer(
        output_directory=str(tmp_path),
        execute_enabled=True,
    )

    # Skip if FFmpeg is not available
    if not renderer.is_available():
        pytest.skip("FFmpeg is not installed or not available on PATH")

    audio_request = AudioRequest(
        scene_number=1,
        duration_seconds=1,
        narration_text="Test",
    )
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert result["status"] == "completed", \
        f"Audio render failed: {result.get('error', 'unknown')}"
    assert result["scene_number"] == 1
    assert result["duration_seconds"] == 1

    # Verify the audio file exists and is non-empty
    audio_file = Path(result["audio_reference"])
    assert audio_file.exists(), f"Audio file not found: {audio_file}"
    assert audio_file.stat().st_size > 0, "Audio file is empty"

    # Verify execution time was recorded
    assert "execution_time_seconds" in result
    assert result["execution_time_seconds"] > 0