"""Integration smoke test for real media muxing.

This test verifies that MediaMuxer can combine a real video file and a
real audio file into a single output MP4 using FFmpeg.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.services.media_muxer import MediaMuxer


def _create_test_video(path: Path) -> None:
    """Create a tiny deterministic MP4 video file using FFmpeg.

    Args:
        path: Output file path.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=red:s=160x120:r=5:d=1",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        shell=False,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )


def _create_test_audio(path: Path) -> None:
    """Create a tiny deterministic AAC audio file using FFmpeg.

    Args:
        path: Output file path.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=1",
            "-c:a", "aac",
            str(path),
        ],
        shell=False,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )


@pytest.mark.integration
def test_real_media_muxer_produces_final_mp4(tmp_path: Path) -> None:
    """Verify MediaMuxer combines real video and audio into a final MP4.

    Creates a tiny video and audio file, muxes them with
    execute_enabled=True, and verifies the final output exists and is
    non-empty.

    Args:
        tmp_path: Pytest temporary directory fixture
    """
    muxer = MediaMuxer(execute_enabled=True)

    # Skip if FFmpeg is not available
    if not muxer.is_available():
        pytest.skip("FFmpeg is not installed or not available on PATH")

    # Create tiny test video and audio files
    video_path = tmp_path / "test_video.mp4"
    audio_path = tmp_path / "test_audio.aac"
    _create_test_video(video_path)
    _create_test_audio(audio_path)

    assert video_path.exists()
    assert audio_path.exists()
    assert video_path.stat().st_size > 0
    assert audio_path.stat().st_size > 0

    # Mux them into a final MP4
    output_path = str(tmp_path / "final_with_audio.mp4")
    result = muxer.mux(str(video_path), str(audio_path), output_path)

    assert result["status"] == "completed", \
        f"Mux failed: {result.get('error', 'unknown')}"
    assert result["output_reference"] == output_path
    assert result["video_reference"] == str(video_path)
    assert result["audio_reference"] == str(audio_path)

    # Verify the final MP4 exists and is non-empty
    final_output = Path(result["output_reference"])
    assert final_output.exists(), f"Final output not found: {final_output}"
    assert final_output.stat().st_size > 0, "Final output is empty"

    # Verify execution time was recorded
    assert "execution_time_seconds" in result
    assert result["execution_time_seconds"] > 0