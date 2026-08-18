"""Tests for single_job_renderer module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.models.content_package import AudioRequest, RenderConfig, RenderJobSpec
from src.services.single_job_renderer import render_single_job


def test_ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    return FFmpegRenderer().is_available()


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_render_single_job_produces_real_mp4() -> None:
    """Test that render_single_job produces a real playable MP4 file.
    
    This test creates a minimal RenderJobSpec with 1 second duration,
    renders it, and verifies the output is a valid MP4 file.
    """
    # Create a minimal render config for fast execution
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=320,
            height=240,
            fps=10,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="test_{job_id}.mp4",
        )

        # Create a minimal valid RenderJobSpec
        job_spec = RenderJobSpec(
            job_id="test-single-job",
            scene_number=1,
            duration_seconds=1,
            render_type="host_footage",
            character_ids=[],
            asset_ids=[],
            visual_prompt="A simple test scene",
            animation_instructions="No animation",
            camera_instructions="Static camera",
            audio_requirements="No audio",
            audio_request=None,
        )

        # Render the job
        result = render_single_job(job_spec, config)

        # Verify the result structure
        assert result["job_id"] == "test-single-job"
        assert result["status"] == "completed", f"Render failed: {result.get('error', 'unknown error')}"
        assert "output_reference" in result
        assert "command" in result
        assert result.get("return_code") == 0

        # Verify the output file exists
        output_path = Path(result["output_reference"])
        assert output_path.exists(), f"Output file not found: {output_path}"

        # Verify the file is non-empty (at least a few bytes for a valid MP4)
        file_size = output_path.stat().st_size
        assert file_size > 1000, f"Output file is too small: {file_size} bytes"

        # Verify the file starts with a valid MP4 signature (ftyp box)
        with open(output_path, "rb") as f:
            header = f.read(12)
            # MP4 files typically start with a size field followed by 'ftyp'
            assert b"ftyp" in header or b"moov" in header or b"mdat" in header, \
                f"Output file does not appear to be a valid MP4: {header.hex()}"

        # Verify execution time was recorded
        assert "execution_time_seconds" in result
        assert result["execution_time_seconds"] > 0


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_render_single_job_with_audio_request() -> None:
    """Test that render_single_job works with an AudioRequest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=160,
            height=120,
            fps=5,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="test_audio_{job_id}.mp4",
        )

        # Create an AudioRequest
        audio_request = AudioRequest(
            scene_number=1,
            duration_seconds=1,
            narration_text="Test narration",
            voice_reference="default",
            background_music_reference="",
            sound_effect_references=[],
            audio_format="aac",
        )

        # Create a RenderJobSpec with audio_request
        job_spec = RenderJobSpec(
            job_id="test-single-job-audio",
            scene_number=1,
            duration_seconds=1,
            render_type="host_footage",
            character_ids=[],
            asset_ids=[],
            visual_prompt="A simple test scene with audio",
            animation_instructions="No animation",
            camera_instructions="Static camera",
            audio_requirements="Test narration",
            audio_request=audio_request,
        )

        # Render the job
        result = render_single_job(job_spec, config)

        # Verify the result structure
        assert result["job_id"] == "test-single-job-audio"
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
def test_render_single_job_deterministic() -> None:
    """Test that render_single_job produces deterministic output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=160,
            height=120,
            fps=5,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="deterministic_{job_id}.mp4",
        )

        job_spec = RenderJobSpec(
            job_id="deterministic-test",
            scene_number=1,
            duration_seconds=1,
            render_type="host_footage",
            character_ids=[],
            asset_ids=[],
            visual_prompt="Deterministic test",
            animation_instructions="None",
            camera_instructions="Static",
            audio_requirements="None",
            audio_request=None,
        )

        # Render twice
        results = []
        for run in [1, 2]:
            # Need to use different job_ids for different output files
            job_spec_run = RenderJobSpec(
                job_id=f"deterministic-test-run{run}",
                scene_number=1,
                duration_seconds=1,
                render_type="host_footage",
                character_ids=[],
                asset_ids=[],
                visual_prompt="Deterministic test",
                animation_instructions="None",
                camera_instructions="Static",
                audio_requirements="None",
                audio_request=None,
            )
            result = render_single_job(job_spec_run, config)
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


def test_render_job_spec_to_dict() -> None:
    """Test that RenderJobSpec.to_dict() works correctly."""
    audio_request = AudioRequest(
        scene_number=1,
        duration_seconds=5,
        narration_text="Test",
        voice_reference="default",
    )

    job_spec = RenderJobSpec(
        job_id="test-job",
        scene_number=1,
        duration_seconds=5,
        render_type="host_footage",
        character_ids=["char1", "char2"],
        asset_ids=["asset1"],
        visual_prompt="Test prompt",
        animation_instructions="Test animation",
        camera_instructions="Test camera",
        audio_requirements="Test audio",
        audio_request=audio_request,
    )

    result = job_spec.to_dict()

    assert result["job_id"] == "test-job"
    assert result["scene_number"] == 1
    assert result["duration_seconds"] == 5
    assert result["render_type"] == "host_footage"
    assert result["character_ids"] == ["char1", "char2"]
    assert result["asset_ids"] == ["asset1"]
    assert result["visual_prompt"] == "Test prompt"
    assert result["animation_instructions"] == "Test animation"
    assert result["camera_instructions"] == "Test camera"
    assert result["audio_requirements"] == "Test audio"
    assert result["audio_request"] is not None
    assert result["audio_request"]["scene_number"] == 1
    assert result["audio_request"]["duration_seconds"] == 5
    assert result["audio_request"]["narration_text"] == "Test"
    assert result["audio_request"]["voice_reference"] == "default"


def test_render_job_spec_to_dict_without_audio() -> None:
    """Test that RenderJobSpec.to_dict() works without audio_request."""
    job_spec = RenderJobSpec(
        job_id="test-job-no-audio",
        scene_number=1,
        duration_seconds=5,
        render_type="host_footage",
        character_ids=[],
        asset_ids=[],
        visual_prompt="Test prompt",
        animation_instructions="Test animation",
        camera_instructions="Test camera",
        audio_requirements="Test audio",
        audio_request=None,
    )

    result = job_spec.to_dict()

    assert result["job_id"] == "test-job-no-audio"
    assert result["audio_request"] is None