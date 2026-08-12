"""Integration smoke test for FinalMediaOrchestrator.

This test verifies the complete pipeline:
  Render Outputs → VideoAssembler → Final Video
  AudioRequest → FFmpegAudioRenderer → Audio
  MediaMuxer → Final MP4 with video + audio
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.models.content_package import AudioRequest, RenderConfig
from src.services.ffmpeg_audio_renderer import FFmpegAudioRenderer
from src.services.final_media_orchestrator import FinalMediaOrchestrator
from src.services.media_muxer import MediaMuxer
from src.services.tts_audio_renderer import TTSAudioRenderer
from src.services.tts_service import MockTTSService
from src.services.video_assembler import VideoAssembler


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


class FileBackedTTSTestService(MockTTSService):
    """Mock TTS service that writes a real audio file for integration tests."""

    def generate(self, request: Any) -> dict[str, Any]:
        result = super().generate(request)
        audio_path = result["audio_reference"]
        if not isinstance(audio_path, str) or not Path(audio_path).is_absolute():
            return result
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f", "lavfi",
                "-i", "sine=frequency=1000:duration=1",
                "-c:a", "pcm_s16le",
                str(audio_path),
            ],
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return result


@pytest.mark.integration
def test_real_final_media_orchestrator_produces_final_mp4(tmp_path: Path) -> None:
    """Verify FinalMediaOrchestrator produces a final MP4 with video + audio.

    Creates a tiny video, assembles it, renders audio, and muxes them
    into a final MP4. Verifies the output exists and is non-empty.

    Args:
        tmp_path: Pytest temporary directory fixture
    """
    # Verify FFmpeg is available
    muxer = MediaMuxer(execute_enabled=True)
    if not muxer.is_available():
        pytest.skip("FFmpeg is not installed or not available on PATH")

    # Create a tiny test video
    video_path = tmp_path / "scene_1.mp4"
    _create_test_video(video_path)
    assert video_path.exists()
    assert video_path.stat().st_size > 0

    # Create render output metadata pointing to the video
    render_outputs = [
        {
            "job_id": "job-1",
            "scene_number": 1,
            "output_reference": str(video_path),
            "status": "completed",
        },
    ]

    # Create one AudioRequest
    audio_request = AudioRequest(
        scene_number=1,
        duration_seconds=1,
        narration_text="Test",
    )

    # Create the orchestrator with all real components
    orchestrator = FinalMediaOrchestrator(
        video_assembler=VideoAssembler(execute_enabled=True),
        audio_renderer=FFmpegAudioRenderer(
            output_directory=str(tmp_path),
            execute_enabled=True,
        ),
        media_muxer=MediaMuxer(execute_enabled=True),
    )

    # Run the orchestrator
    output_path = str(tmp_path / "final_with_audio.mp4")
    result = orchestrator.create_final_media(
        render_outputs,
        [audio_request],
        output_path,
    )

    # Verify success
    assert result["status"] == "completed", \
        f"Orchestration failed: {result.get('error', 'unknown')}"
    assert result["output_reference"] == output_path

    # Verify the final MP4 exists and is non-empty
    final_output = Path(result["output_reference"])
    assert final_output.exists(), f"Final output not found: {final_output}"
    assert final_output.stat().st_size > 0, "Final output is empty"


@pytest.mark.integration
def test_real_final_media_orchestrator_produces_mp4_with_video_and_audio_via_tts_renderer(tmp_path: Path) -> None:
    """Verify the pipeline produces a final MP4 with both video and audio using TTSAudioRenderer."""
    muxer = MediaMuxer(execute_enabled=True)
    if not muxer.is_available():
        pytest.skip("FFmpeg is not installed or not available on PATH")

    video_path = tmp_path / "scene_1.mp4"
    _create_test_video(video_path)

    render_outputs = [
        {
            "job_id": "job-1",
            "scene_number": 1,
            "output_reference": str(video_path),
            "status": "completed",
        },
    ]

    audio_request = AudioRequest(
        scene_number=1,
        duration_seconds=1,
        narration_text="Hello world",
        voice_reference="default",
        audio_format="wav",
    )

    audio_dir = tmp_path / "tts_audio"
    tts_service = FileBackedTTSTestService(output_directory=str(audio_dir))
    orchestrator = FinalMediaOrchestrator(
        video_assembler=VideoAssembler(
            config=RenderConfig(output_directory=str(tmp_path), video_format="mp4", video_codec="libx264"),
            execute_enabled=True,
        ),
        audio_renderer=TTSAudioRenderer(tts_service=tts_service),
        media_muxer=muxer,
    )

    output_path = str(tmp_path / "final_with_tts_audio.mp4")
    result = orchestrator.create_final_media(render_outputs, [audio_request], output_path)

    assert result["status"] == "completed", f"Orchestration failed: {result.get('error', 'unknown')}"
    assert result["output_reference"] == output_path

    final_output = Path(result["output_reference"])
    assert final_output.exists()
    assert final_output.stat().st_size > 0

    video_streams = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(final_output)],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    audio_streams = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(final_output)],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert video_streams == "video"
    assert audio_streams == "audio"
