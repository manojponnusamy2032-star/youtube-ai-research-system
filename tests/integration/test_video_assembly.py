"""Integration smoke test for video assembly.

This test verifies that VideoAssembler builds correct concat commands
and can combine real scene MP4 files into one final MP4 using FFmpeg.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.models.content_package import RenderConfig
from src.services.video_assembler import VideoAssembler


def _create_output(job_id: str, scene_number: int, output_ref: str) -> dict[str, object]:
    """Create a render output record."""
    return {
        "output_id": f"output_{job_id}",
        "job_id": job_id,
        "scene_number": scene_number,
        "status": "completed",
        "output_reference": output_ref,
        "duration_seconds": 1,
    }


def _create_scene_mp4(path: Path, color: str, duration: int = 1) -> None:
    """Create a tiny deterministic MP4 scene file using FFmpeg.

    Args:
        path: Output file path.
        color: FFmpeg color name (e.g., 'red', 'blue').
        duration: Duration in seconds.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"color=c={color}:s=160x120:r=5:d={duration}",
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


def test_video_assembly_builds_concat_command(tmp_path: Path) -> None:
    """Verify VideoAssembler builds a concat command for real scene files.

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
        filename_template="{job_id}.mp4",
    )

    # Create scene output records (paths need not exist for command building)
    scene_outputs = [
        _create_output("scene-3", 3, str(tmp_path / "scene-3.mp4")),
        _create_output("scene-1", 1, str(tmp_path / "scene-1.mp4")),
        _create_output("scene-2", 2, str(tmp_path / "scene-2.mp4")),
    ]

    assembler = VideoAssembler(config=config)
    result = assembler.assemble(scene_outputs)

    assert result["status"] == "command_built"
    assert result["total_scenes"] == 3

    # Verify concat content has scenes in correct order
    concat_content = result["concat_content"]
    assert concat_content.index("scene-1") < concat_content.index("scene-2")
    assert concat_content.index("scene-2") < concat_content.index("scene-3")

    # Verify command structure
    command = result["command"]
    assert command[0] == "ffmpeg"
    assert "-f" in command
    assert "concat" in command
    assert "-c:v" in command
    assert "libx264" in command

    # Verify output path uses config output directory
    assert result["output_reference"].startswith(str(tmp_path))
    assert result["output_reference"].endswith("final_video.mp4")


@pytest.mark.integration
def test_real_video_assembly_produces_final_mp4(tmp_path: Path) -> None:
    """Verify VideoAssembler combines real scene MP4s into a final MP4.

    Creates two tiny scene MP4 files, assembles them with
    execute_enabled=True, and verifies the final output exists and is
    non-empty.

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
        filename_template="{job_id}.mp4",
    )

    # Create two tiny scene MP4 files
    scene_1_path = tmp_path / "scene-1.mp4"
    scene_2_path = tmp_path / "scene-2.mp4"
    _create_scene_mp4(scene_1_path, "red")
    _create_scene_mp4(scene_2_path, "blue")

    assert scene_1_path.exists()
    assert scene_2_path.exists()
    assert scene_1_path.stat().st_size > 0
    assert scene_2_path.stat().st_size > 0

    # Create render-output records
    scene_outputs = [
        _create_output("scene-1", 1, str(scene_1_path)),
        _create_output("scene-2", 2, str(scene_2_path)),
    ]

    # Assemble with execution enabled
    assembler = VideoAssembler(config=config, execute_enabled=True)
    result = assembler.assemble(scene_outputs)

    assert result["status"] == "completed", \
        f"Assembly failed: {result.get('error', 'unknown')}"
    assert result["assembled_scenes"] == 2
    assert result["total_scenes"] == 2

    # Verify the final MP4 exists and is non-empty
    final_output = Path(result["output_reference"])
    assert final_output.exists(), f"Final output not found: {final_output}"
    assert final_output.stat().st_size > 0, "Final output is empty"

    # Verify execution time was recorded
    assert "execution_time_seconds" in result
    assert result["execution_time_seconds"] > 0