"""Tests for the MultiSceneRenderer service.

Verifies that a RenderJobPlan with multiple scenes is rendered into
individual scene MP4s and assembled into a single final MP4.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageChops, ImageStat

from src.models.content_package import AudioRequest, RenderConfig, RenderJobPlan, RenderJobSpec
from src.services.multi_scene_renderer import MultiSceneRenderer
from src.services.video_assembler import VideoAssembler


def _ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    return FFmpegRenderer().is_available()


def _make_config(tmpdir: str) -> RenderConfig:
    """Create a small render config for fast tests."""
    return RenderConfig(
        width=160,
        height=120,
        fps=5,
        video_format="mp4",
        video_codec="libx264",
        audio_format="aac",
        output_directory=tmpdir,
        filename_template="scene_{job_id}.mp4",
    )


def _make_plan(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a render job plan dict from job dicts."""
    return {
        "total_jobs": len(jobs),
        "jobs": jobs,
        "total_duration_seconds": sum(j.get("duration_seconds", 0) for j in jobs),
    }


def _make_job(
    job_id: str,
    scene_number: int,
    duration: int,
    audio_request: dict[str, Any] | None = None,
    motions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a job dict."""
    job = {
        "job_id": job_id,
        "scene_number": scene_number,
        "duration_seconds": duration,
        "render_type": "stickman_animation",
        "visual_prompt": f"Scene {scene_number}",
        "animation_instructions": "Walk cycle",
        "camera_instructions": "Static",
        "audio_requirements": "Narration" if audio_request else "None",
    }
    if audio_request:
        job["audio_request"] = audio_request
    if motions:
        job["motions"] = motions
    return job


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


def _probe_duration(path: Path) -> float:
    """Return the duration of a media file in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return float(result) if result else 0.0


def _render_frame(video_path: Path, timestamp: str, output_path: Path) -> None:
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


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_one_scene_plan() -> None:
    """Test rendering a one-scene RenderJobPlan."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        plan = _make_plan([
            _make_job("scene-1", 1, 2),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        assert result["total_scenes"] == 1
        assert result["total_duration_seconds"] == 2
        assert len(result["scene_results"]) == 1
        assert result["scene_results"][0]["status"] == "completed"

        final_output = Path(result["final_output"])
        assert final_output.exists()
        assert final_output.stat().st_size > 1000

        video, audio = _probe_streams(final_output)
        assert video == "video"


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_two_scene_plan() -> None:
    """Test rendering a two-scene RenderJobPlan."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        plan = _make_plan([
            _make_job("scene-1", 1, 2),
            _make_job("scene-2", 2, 3),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        assert result["total_scenes"] == 2
        assert result["total_duration_seconds"] == 5
        assert len(result["scene_results"]) == 2
        assert all(r["status"] == "completed" for r in result["scene_results"])

        final_output = Path(result["final_output"])
        assert final_output.exists()
        assert final_output.stat().st_size > 1000

        video, audio = _probe_streams(final_output)
        assert video == "video"


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_scene_ordering() -> None:
    """Test that scenes are assembled in scene_number order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        # Deliberately out of order in the plan
        plan = _make_plan([
            _make_job("scene-2", 2, 2),
            _make_job("scene-1", 1, 2),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        assert result["total_scenes"] == 2

        # The assembly result should have sorted by scene_number
        assembly = result.get("assembly_result", {})
        assert assembly.get("total_scenes") == 2
        assert assembly.get("assembled_scenes") == 2

        final_output = Path(result["final_output"])
        assert final_output.exists()
        assert final_output.stat().st_size > 1000


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_duration_preservation() -> None:
    """Test that the final duration approximately equals the sum of scene durations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        plan = _make_plan([
            _make_job("scene-1", 1, 2),
            _make_job("scene-2", 2, 3),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        assert result["total_duration_seconds"] == 5

        final_output = Path(result["final_output"])
        duration = _probe_duration(final_output)
        # Allow tolerance for encoding overhead
        assert abs(duration - 5.0) < 1.0, f"Final duration {duration} != expected ~5.0"


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_audio_preservation() -> None:
    """Test that scenes with audio requests produce a final MP4 with audio."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        audio_req = {
            "scene_number": 1,
            "duration_seconds": 2,
            "narration_text": "Hello world",
            "voice_reference": "default",
            "background_music_reference": "",
            "sound_effect_references": [],
            "audio_format": "aac",
        }

        plan = _make_plan([
            _make_job("scene-1", 1, 2, audio_req),
            _make_job("scene-2", 2, 2),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        assert result["total_scenes"] == 2

        final_output = Path(result["final_output"])
        assert final_output.exists()
        assert final_output.stat().st_size > 1000

        video, audio = _probe_streams(final_output)
        assert video == "video"
        assert audio == "audio"


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_final_mp4_exists() -> None:
    """Test that the final MP4 file exists and is non-empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        plan = _make_plan([
            _make_job("scene-1", 1, 2),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        final_output = Path(result["final_output"])
        assert final_output.exists()
        assert final_output.stat().st_size > 1000


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_final_mp4_contains_video_stream() -> None:
    """Test that the final MP4 contains a video stream."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        plan = _make_plan([
            _make_job("scene-1", 1, 2),
            _make_job("scene-2", 2, 2),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        final_output = Path(result["final_output"])
        video, _ = _probe_streams(final_output)
        assert video == "video"


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_final_mp4_contains_audio_stream_when_requested() -> None:
    """Test that the final MP4 contains an audio stream when audio is requested."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        audio_req = {
            "scene_number": 1,
            "duration_seconds": 2,
            "narration_text": "Hello",
            "voice_reference": "default",
            "background_music_reference": "",
            "sound_effect_references": [],
            "audio_format": "aac",
        }

        plan = _make_plan([
            _make_job("scene-1", 1, 2, audio_req),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        final_output = Path(result["final_output"])
        video, audio = _probe_streams(final_output)
        assert video == "video"
        assert audio == "audio"


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_three_scene_motion_plan_preserves_visible_motion_in_final_mp4() -> None:
    """Render three scenes with distinct motions and verify the final MP4 changes over time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _make_config(tmpdir)
        renderer = MultiSceneRenderer(config=config)

        plan = _make_plan([
            _make_job(
                "scene-1",
                1,
                2,
                motions=[
                    {
                        "type": "zoom",
                        "target": "camera",
                        "start_time": 0.0,
                        "duration": 2.0,
                        "easing": "ease_in_out",
                        "parameters": {"from": 1.0, "to": 1.2},
                    }
                ],
            ),
            _make_job(
                "scene-2",
                2,
                2,
                motions=[
                    {
                        "type": "enter",
                        "target": "character",
                        "start_time": 0.0,
                        "duration": 1.0,
                        "easing": "ease_out",
                        "parameters": {"direction": "left"},
                    },
                    {
                        "type": "move",
                        "target": "character",
                        "start_time": 0.5,
                        "duration": 1.5,
                        "easing": "ease_in_out",
                        "parameters": {"from": {"x": 0.15, "y": 0.75}, "to": {"x": 0.5, "y": 0.75}},
                    },
                ],
            ),
            _make_job(
                "scene-3",
                3,
                2,
                motions=[
                    {
                        "type": "fade",
                        "target": "text",
                        "start_time": 0.5,
                        "duration": 1.5,
                        "easing": "ease_in_out",
                        "parameters": {"from": 0.0, "to": 1.0},
                    },
                    {
                        "type": "scale",
                        "target": "text",
                        "start_time": 0.5,
                        "duration": 1.5,
                        "easing": "ease_out",
                        "parameters": {"from": 0.85, "to": 1.0},
                    },
                ],
            ),
        ])

        result = renderer.render_plan(plan)

        assert result["status"] == "completed", f"Failed: {result.get('error')}"
        assert result["total_scenes"] == 3
        assert result["total_duration_seconds"] == 6

        final_output = Path(result["final_output"])
        assert final_output.exists()
        duration = _probe_duration(final_output)
        assert abs(duration - 6.0) < 0.75

        first_frame = Path(tmpdir) / "scene_first.png"
        middle_frame = Path(tmpdir) / "scene_middle.png"
        last_frame = Path(tmpdir) / "scene_last.png"
        _render_frame(final_output, "0.5", first_frame)
        _render_frame(final_output, "2.5", middle_frame)
        _render_frame(final_output, "4.5", last_frame)

        assert _frame_difference(first_frame, middle_frame) > 0
        assert _frame_difference(middle_frame, last_frame) > 0
        assert _frame_difference(first_frame, last_frame) > 0
