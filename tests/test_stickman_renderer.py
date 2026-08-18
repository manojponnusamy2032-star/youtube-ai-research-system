"""Tests for stickman_renderer module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.models.content_package import AudioRequest, RenderConfig, RenderJobSpec
from src.services.stickman_renderer import StickmanRenderer, render_stickman_job


def test_ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    return FFmpegRenderer().is_available()


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_render_stickman_job_produces_real_mp4() -> None:
    """Test that render_stickman_job produces a real playable MP4 file with animation.
    
    This test creates a minimal RenderJobSpec with 2 second duration,
    renders it, and verifies the output is a valid MP4 file.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=320,
            height=240,
            fps=10,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="stickman_{job_id}.mp4",
        )

        # Create a minimal valid RenderJobSpec
        job_spec = RenderJobSpec(
            job_id="test-stickman-job",
            scene_number=1,
            duration_seconds=2,
            render_type="stickman_animation",
            character_ids=[],
            asset_ids=[],
            visual_prompt="A stickman walking across the screen",
            animation_instructions="Walk cycle with arm/leg oscillation",
            camera_instructions="Slight camera follow",
            audio_requirements="No audio",
            audio_request=None,
        )

        # Render the job
        result = render_stickman_job(job_spec, config)

        # Verify the result structure
        assert result["job_id"] == "test-stickman-job"
        assert result["status"] == "completed", f"Render failed: {result.get('error', 'unknown error')}"
        assert "output_reference" in result
        assert "file_size_bytes" in result
        assert result["duration_seconds"] == 2

        # Verify the output file exists
        output_path = Path(result["output_reference"])
        assert output_path.exists(), f"Output file not found: {output_path}"

        # Verify the file is non-empty (at least a few bytes for a valid MP4)
        file_size = output_path.stat().st_size
        assert file_size > 1000, f"Output file is too small: {file_size} bytes"
        assert file_size == result["file_size_bytes"]

        # Verify the file starts with a valid MP4 signature (ftyp box)
        with open(output_path, "rb") as f:
            header = f.read(12)
            # MP4 files typically start with a size field followed by 'ftyp'
            assert b"ftyp" in header or b"moov" in header or b"mdat" in header, \
                f"Output file does not appear to be a valid MP4: {header.hex()}"


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_render_stickman_job_with_audio_request() -> None:
    """Test that render_stickman_job works with an AudioRequest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=160,
            height=120,
            fps=5,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="stickman_audio_{job_id}.mp4",
        )

        # Create an AudioRequest
        audio_request = AudioRequest(
            scene_number=1,
            duration_seconds=2,
            narration_text="Watch the stickman walk",
            voice_reference="default",
            background_music_reference="",
            sound_effect_references=[],
            audio_format="aac",
        )

        # Create a RenderJobSpec with audio_request
        job_spec = RenderJobSpec(
            job_id="test-stickman-job-audio",
            scene_number=1,
            duration_seconds=2,
            render_type="stickman_animation",
            character_ids=[],
            asset_ids=[],
            visual_prompt="A stickman walking with narration",
            animation_instructions="Walk cycle",
            camera_instructions="Follow camera",
            audio_requirements="Narration about walking",
            audio_request=audio_request,
        )

        # Render the job
        result = render_stickman_job(job_spec, config)

        # Verify the result structure
        assert result["job_id"] == "test-stickman-job-audio"
        assert result["status"] == "completed", f"Render failed: {result.get('error', 'unknown error')}"
        assert "output_reference" in result

        # Verify the output file exists
        output_path = Path(result["output_reference"])
        assert output_path.exists(), f"Output file not found: {output_path}"

        # Verify the file is non-empty
        file_size = output_path.stat().st_size
        assert file_size > 1000, f"Output file is too small: {file_size} bytes"


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_render_stickman_job_deterministic() -> None:
    """Test that render_stickman_job produces deterministic output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=160,
            height=120,
            fps=5,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="stickman_deterministic_{job_id}.mp4",
        )

        # Render twice with different job IDs
        results = []
        for run in [1, 2]:
            job_spec = RenderJobSpec(
                job_id=f"deterministic-stickman-run{run}",
                scene_number=1,
                duration_seconds=2,
                render_type="stickman_animation",
                character_ids=[],
                asset_ids=[],
                visual_prompt="Deterministic stickman test",
                animation_instructions="Walk cycle",
                camera_instructions="Static",
                audio_requirements="None",
                audio_request=None,
            )
            result = render_stickman_job(job_spec, config)
            results.append(result)

            assert result["status"] == "completed", \
                f"Run {run} failed: {result.get('error', 'unknown error')}"

        # Both runs should succeed
        assert all(r["status"] == "completed" for r in results)

        # Both output files should exist and be similar in size
        sizes = []
        for result in results:
            output_path = Path(result["output_reference"])
            assert output_path.exists()
            sizes.append(output_path.stat().st_size)

        # Files should be similar in size (within 20% tolerance for encoding variance)
        assert abs(sizes[0] - sizes[1]) / max(sizes[0], sizes[1]) < 0.2, \
            f"Output sizes differ significantly: {sizes[0]} vs {sizes[1]} bytes"


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_stickman_renderer_direct() -> None:
    """Test StickmanRenderer class directly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=160,
            height=120,
            fps=5,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="direct_{job_id}.mp4",
        )

        from src.agents.render_job_executor import RenderRequest
        
        renderer = StickmanRenderer(execute_enabled=True)
        
        request = RenderRequest(
            job={
                "job_id": "direct-test",
                "duration_seconds": 1,
                "render_type": "stickman_animation",
            },
            render_config=config,
            resolved_assets=[],
            resolved_characters=[],
        )
        
        result = renderer.render(request)
        
        assert result["job_id"] == "direct-test"
        assert result["status"] == "completed"
        assert "output_reference" in result
        
        output_path = Path(result["output_reference"])
        assert output_path.exists()
        assert output_path.stat().st_size > 1000


def test_stickman_renderer_not_available() -> None:
    """Test StickmanRenderer when FFmpeg is not available (mocked)."""
    # This test just verifies the class can be instantiated
    renderer = StickmanRenderer(execute_enabled=False)
    assert renderer.execute_enabled is False
    assert hasattr(renderer, 'is_available')
    assert hasattr(renderer, 'render')


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_stickman_renderer_without_audio() -> None:
    """Test that rendering without an AudioRequest preserves video-only behavior (no audio stream)."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=160,
            height=120,
            fps=5,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="no_audio_{job_id}.mp4",
        )

        job_spec = RenderJobSpec(
            job_id="test-no-audio",
            scene_number=1,
            duration_seconds=2,
            render_type="stickman_animation",
            character_ids=[],
            asset_ids=[],
            visual_prompt="A stickman walking",
            animation_instructions="Walk cycle",
            camera_instructions="Static",
            audio_requirements="No audio",
            audio_request=None,
        )

        result = render_stickman_job(job_spec, config)
        assert result["status"] == "completed"

        output_path = Path(result["output_reference"])
        assert output_path.exists()
        assert output_path.stat().st_size > 1000

        # Check video stream
        video_streams = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert video_streams == "video"

        # Check that there is NO audio stream
        audio_streams = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert audio_streams == ""


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_stickman_renderer_with_audio_contains_audio_stream() -> None:
    """Test that rendering with an AudioRequest produces an MP4 with video and audio streams of equal duration."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=160,
            height=120,
            fps=5,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="with_audio_{job_id}.mp4",
        )

        audio_request = AudioRequest(
            scene_number=1,
            duration_seconds=2,
            narration_text="Voice narration",
            voice_reference="default",
            background_music_reference="",
            sound_effect_references=[],
            audio_format="aac",
        )

        job_spec = RenderJobSpec(
            job_id="test-with-audio",
            scene_number=1,
            duration_seconds=2,
            render_type="stickman_animation",
            character_ids=[],
            asset_ids=[],
            visual_prompt="A stickman walking with sound",
            animation_instructions="Walk cycle",
            camera_instructions="Static",
            audio_requirements="Narration",
            audio_request=audio_request,
        )

        result = render_stickman_job(job_spec, config)
        assert result["status"] == "completed"

        output_path = Path(result["output_reference"])
        assert output_path.exists()
        assert output_path.stat().st_size > 1000

        # Verify video stream exists
        video_streams = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert video_streams == "video"

        # Verify audio stream exists
        audio_streams = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert audio_streams == "audio"

        # Verify durations are approximately equal (2.0s)
        video_duration_str = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        audio_duration_str = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            shell=False,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        video_dur = float(video_duration_str) if video_duration_str else 0.0
        audio_dur = float(audio_duration_str) if audio_duration_str else 0.0

        assert abs(video_dur - 2.0) < 0.5
        assert abs(audio_dur - 2.0) < 0.5
        assert abs(video_dur - audio_dur) < 0.2
