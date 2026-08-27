"""Integration smoke test for video assembly.

This test verifies that VideoAssembler builds correct concat commands
and can combine real scene MP4 files into one final MP4 using FFmpeg.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

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


def _create_scene_mp4(path: Path, color: str, duration: int = 1, with_audio: bool = False) -> None:
    """Create a tiny deterministic MP4 scene file using FFmpeg.

    Args:
        path: Output file path.
        color: FFmpeg color name (e.g., 'red', 'blue').
        duration: Duration in seconds.
    """
    command = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s=160x120:r=5:d={duration}",
    ]
    if with_audio:
        command.extend([
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=44100:d={duration}",
        ])
    command.extend([
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    ])
    if with_audio:
        command.extend([
            "-c:a",
            "aac",
            "-shortest",
        ])
    command.append(str(path))
    subprocess.run(
        command,
        shell=False,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )


def _extract_frame(video_path: Path, timestamp: str, output_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            timestamp,
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(output_path),
        ],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    )


def _probe_duration(video_path: Path) -> float:
    """Return the duration of a media file in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return float(result) if result else 0.0


def _probe_streams(path: Path) -> tuple[str, str]:
    """Return (video_stream, audio_stream) from ffprobe."""
    video = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    audio = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return video, audio


def _probe_resolution_fps(path: Path) -> tuple[int, int, float]:
    """Return (width, height, fps) from ffprobe."""
    info = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-of", "csv=p=0",
            str(path),
        ],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    parts = info.split(",")
    width = int(parts[0])
    height = int(parts[1])
    fps_parts = parts[2].split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 and float(fps_parts[1]) else float(fps_parts[0])
    return width, height, fps


def _frame_difference(left: Path, right: Path) -> int:
    image_a = Image.open(left).convert("RGB")
    image_b = Image.open(right).convert("RGB")
    diff = ImageChops.difference(image_a, image_b)
    bbox = diff.getbbox()
    if bbox is None:
        return 0
    crop = diff.crop(bbox)
    stat = ImageStat.Stat(crop)
    return int(sum(stat.sum))


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


@pytest.mark.integration
def test_real_video_assembly_applies_crossfade_transition(tmp_path: Path) -> None:
    """Verify VideoAssembler applies a structured transition between scenes."""
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

    scene_1_path = tmp_path / "scene-1.mp4"
    scene_2_path = tmp_path / "scene-2.mp4"
    _create_scene_mp4(scene_1_path, "red", duration=2, with_audio=True)
    _create_scene_mp4(scene_2_path, "blue", duration=2, with_audio=True)

    scene_outputs = [
        {
            "output_id": "output_scene-1",
            "job_id": "scene-1",
            "scene_number": 1,
            "status": "completed",
            "output_reference": str(scene_1_path),
            "duration_seconds": 2,
            "transition_to_next": {
                "type": "crossfade",
                "duration": 0.5,
                "parameters": {"curve": "smooth"},
            },
        },
        {
            "output_id": "output_scene-2",
            "job_id": "scene-2",
            "scene_number": 2,
            "status": "completed",
            "output_reference": str(scene_2_path),
            "duration_seconds": 2,
        },
    ]

    assembler = VideoAssembler(config=config, execute_enabled=True)
    result = assembler.assemble(scene_outputs)

    assert result["status"] == "completed", f"Assembly failed: {result.get('error', 'unknown')}"
    final_output = Path(result["output_reference"])
    assert final_output.exists()

    duration = _probe_duration(final_output)
    assert abs(duration - 3.5) < 0.75

    first_frame = tmp_path / "transition_first.png"
    mid_frame = tmp_path / "transition_mid.png"
    last_frame = tmp_path / "transition_last.png"
    _extract_frame(final_output, "0.5", first_frame)
    _extract_frame(final_output, "1.8", mid_frame)
    _extract_frame(final_output, "3.0", last_frame)

    assert _frame_difference(first_frame, mid_frame) > 0
    assert _frame_difference(mid_frame, last_frame) > 0


@pytest.mark.integration
def test_real_video_assembly_multi_transition_mp4(tmp_path: Path) -> None:
    """Render a 4-scene MP4 with multiple transition types and verify with ffprobe.

    Scenes are solid colors (red, green, blue, yellow) at 160x120, 5 fps,
    2 seconds each. Transitions:
      - scene 1 -> 2: crossfade (0.5s)
      - scene 2 -> 3: slide_left  (0.5s)
      - scene 3 -> 4: fade_to_black (0.5s)

    Expected final duration: 8 - 3 * 0.5 = 6.5s.
    Resolution and fps must be preserved from the inputs.
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

    scene_paths = []
    colors = ["red", "blue", "green", "black"]
    for i, color in enumerate(colors, start=1):
        path = tmp_path / f"scene-{i}.mp4"
        _create_scene_mp4(path, color, duration=2, with_audio=True)
        scene_paths.append(path)

    transitions = [
        {"type": "crossfade", "duration": 0.5, "parameters": {}},
        {"type": "slide_left", "duration": 0.5, "parameters": {}},
        {"type": "fade_to_black", "duration": 0.5, "parameters": {}},
    ]
    scene_outputs = []
    for i, path in enumerate(scene_paths, start=1):
        record = {
            "output_id": f"output_scene-{i}",
            "job_id": f"scene-{i}",
            "scene_number": i,
            "status": "completed",
            "output_reference": str(path),
            "duration_seconds": 2,
        }
        if i <= len(transitions):
            record["transition_to_next"] = transitions[i - 1]
        scene_outputs.append(record)

    assembler = VideoAssembler(config=config, execute_enabled=True)
    result = assembler.assemble(scene_outputs)

    assert result["status"] == "completed", f"Assembly failed: {result.get('error', 'unknown')}"
    final_output = Path(result["output_reference"])
    assert final_output.exists()
    assert final_output.stat().st_size > 0

    # Verify streams
    video, audio = _probe_streams(final_output)
    assert video == "video"
    assert audio == "audio"

    # Verify duration: 8s total - 3 * 0.5s overlap = 6.5s
    duration = _probe_duration(final_output)
    assert abs(duration - 6.5) < 1.0, f"Duration {duration} != expected ~6.5"

    # Verify resolution and fps preserved
    width, height, fps = _probe_resolution_fps(final_output)
    assert width == 160
    assert height == 120
    assert abs(fps - 5.0) < 0.5

    # Verify transitions produce intermediate frames (not hard cuts).
    # Extract frame before the crossfade (scene 1 solid red) and during
    # the crossfade window. If a hard cut was used, both frames would be
    # identical (red). With a real crossfade, the second frame differs.
    pre_fade_frame = tmp_path / "pre_fade.png"
    mid_fade_frame = tmp_path / "mid_fade.png"
    _extract_frame(final_output, "1.0", pre_fade_frame)
    _extract_frame(final_output, "1.8", mid_fade_frame)
    assert _frame_difference(pre_fade_frame, mid_fade_frame) > 0, \
        "No visible difference across transition boundary (hard cut detected)"

    # Verify the transition plan is recorded in the assembly result.
    # (The command includes filter_complex with xfade and acrossfade.)
    assert "-filter_complex" in result["command"]
    filter_args = result["command"]
    fc_index = filter_args.index("-filter_complex")
    assert "xfade" in filter_args[fc_index + 1]
    assert "acrossfade" in filter_args[fc_index + 1]
    assert "slideleft" in filter_args[fc_index + 1]
    assert "fadeblack" in filter_args[fc_index + 1]
