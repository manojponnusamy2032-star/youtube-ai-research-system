"""Integration smoke test for real FFmpeg execution.

This test verifies that FFmpegRenderer can produce a real playable video
when FFmpeg is available on the system.

This test is SKIPPED by default unless:
1. FFmpeg is installed and available
2. The test is explicitly run with: pytest -m integration
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.agents.render_job_executor import RenderRequest
from src.models.content_package import RenderConfig
from src.services.ffmpeg_renderer import FFmpegRenderer


def test_ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    return FFmpegRenderer().is_available()


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_real_ffmpeg_render_produces_video(tmp_path: Path) -> None:
    """Smoke test: verify FFmpegRenderer can produce a real MP4 file.
    
    This test creates a minimal 1-second video using FFmpeg's built-in
    test pattern generator and verifies the output is valid.
    
    Args:
        tmp_path: Pytest temporary directory fixture
    """
    # Create a minimal render config for fast execution
    config = RenderConfig(
        width=320,
        height=240,
        fps=10,
        video_format="mp4",
        video_codec="libx264",
        audio_format="aac",
        output_directory=str(tmp_path),
        filename_template="smoke_test_{job_id}.mp4",
    )
    
    # Create a simple render request
    request = RenderRequest(
        job={
            "job_id": "smoke-test",
            "duration_seconds": 1,
        },
        render_config=config,
    )
    
    # Create renderer with execution enabled
    renderer = FFmpegRenderer(execute_enabled=True)
    
    # Execute the render
    result = renderer.render(request)
    
    # Verify the result structure
    assert result["job_id"] == "smoke-test"
    assert result["status"] == "completed", f"Render failed: {result.get('error', 'unknown error')}"
    assert "output_reference" in result
    assert "command" in result
    assert result["return_code"] == 0
    
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
def test_real_ffmpeg_render_with_render_job_executor(tmp_path: Path) -> None:
    """Smoke test: verify FFmpegRenderer works through RenderJobExecutor.
    
    This test verifies the full integration path:
    RenderJobExecutor → FFmpegRenderer → FFmpeg → real MP4 file
    
    Args:
        tmp_path: Pytest temporary directory fixture
    """
    from src.agents.render_job_executor import RenderJobExecutor
    
    # Create a minimal render config
    config = RenderConfig(
        width=160,
        height=120,
        fps=5,
        video_format="mp4",
        video_codec="libx264",
        audio_format="aac",
        output_directory=str(tmp_path),
        filename_template="executor_smoke_{job_id}.mp4",
    )
    
    # Create executor with FFmpegRenderer
    renderer = FFmpegRenderer(execute_enabled=True)
    executor = RenderJobExecutor(renderer=renderer)
    
    # Create workflow context with a simple render job
    from src.core.context import WorkflowContext
    context = WorkflowContext()
    context.set("render_jobs", [
        {
            "job_id": "executor-smoke",
            "scene_number": 1,
            "duration_seconds": 1,
        }
    ])
    context.set("render_config", config)
    
    # Execute the render
    result = executor.run(context)
    
    # Verify the executor succeeded
    assert result.success is True
    assert len(result.data["render_results"]) == 1
    
    # Verify the render result
    render_result = result.data["render_results"][0]
    assert render_result["job_id"] == "executor-smoke"
    assert render_result["status"] == "completed", \
        f"Render failed: {render_result.get('error', 'unknown error')}"
    
    # Verify the output file exists
    output_path = Path(render_result["output_reference"])
    assert output_path.exists(), f"Output file not found: {output_path}"
    
    # Verify the file is non-empty
    file_size = output_path.stat().st_size
    assert file_size > 1000, f"Output file is too small: {file_size} bytes"


@pytest.mark.integration
@pytest.mark.skipif(
    not test_ffmpeg_available(),
    reason="FFmpeg is not installed or not available on PATH",
)
def test_ffmpeg_renderer_deterministic_output(tmp_path: Path) -> None:
    """Smoke test: verify FFmpegRenderer produces deterministic output.
    
    This test renders the same job twice and verifies both outputs
    are valid and have similar sizes (deterministic encoding).
    
    Args:
        tmp_path: Pytest temporary directory fixture
    """
    config = RenderConfig(
        width=160,
        height=120,
        fps=5,
        video_format="mp4",
        video_codec="libx264",
        audio_format="aac",
        output_directory=str(tmp_path),
        filename_template="deterministic_{job_id}.mp4",
    )
    
    renderer = FFmpegRenderer(execute_enabled=True)
    
    # Render twice with different job IDs
    results = []
    for run in [1, 2]:
        request = RenderRequest(
            job={
                "job_id": f"deterministic-test-run{run}",
                "duration_seconds": 1,
            },
            render_config=config,
        )
        
        result = renderer.render(request)
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