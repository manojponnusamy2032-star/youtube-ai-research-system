from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from src.agents.render_job_executor import RenderRequest
from src.models.content_package import Motion, RenderConfig, RenderJobSpec
from src.services.stickman_renderer import StickmanRenderer, render_stickman_job
from src.utils.motion_utils import apply_easing, interpolate_value, motion_progress


def _ffmpeg_available() -> bool:
    from src.services.ffmpeg_renderer import FFmpegRenderer

    return FFmpegRenderer().is_available()


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


def test_motion_model_creation_and_roundtrip() -> None:
    motion = Motion(
        type="zoom",
        target="camera",
        start_time=0.0,
        duration=2.5,
        easing="ease_in_out",
        parameters={"from": 1.0, "to": 1.2},
    )

    motion_dict = motion.to_dict()
    assert motion_dict["type"] == "zoom"
    assert motion_dict["target"] == "camera"
    assert motion_dict["parameters"]["to"] == 1.2


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"type": "spin", "target": "camera", "start_time": 0.0, "duration": 1.0, "parameters": {"from": 0, "to": 1}}, "unknown motion type"),
        ({"type": "zoom", "target": "galaxy", "start_time": 0.0, "duration": 1.0, "parameters": {"from": 1.0, "to": 1.1}}, "invalid motion target"),
        ({"type": "zoom", "target": "camera", "start_time": 0.0, "duration": 1.0, "easing": "bounce", "parameters": {"from": 1.0, "to": 1.1}}, "invalid easing"),
        ({"type": "zoom", "target": "camera", "start_time": 0.0, "duration": -1.0, "parameters": {"from": 1.0, "to": 1.1}}, "duration must be positive"),
        ({"type": "move", "target": "character", "start_time": 0.0, "duration": 1.0, "parameters": {"from": {"x": 0.0, "y": 0.0}}}, "requires 'from' and 'to'"),
        ({"type": "enter", "target": "text", "start_time": 0.0, "duration": 1.0, "parameters": {}}, "requires a direction"),
    ],
)
def test_motion_validation_errors(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Motion(**kwargs)


def test_motion_utils_easing_and_interpolation() -> None:
    assert apply_easing(0.5, "linear") == 0.5
    assert apply_easing(0.5, "ease_in") < 0.5
    assert apply_easing(0.5, "ease_out") > 0.5
    assert math.isclose(apply_easing(0.5, "ease_in_out"), 0.5, rel_tol=1e-6)
    assert interpolate_value(0.0, 10.0, 0.25) == 2.5
    assert motion_progress(
        Motion(
            type="zoom",
            target="camera",
            start_time=1.0,
            duration=2.0,
            parameters={"from": 1.0, "to": 1.2},
        ),
        2.0,
    ) == 0.5


def test_overlapping_motion_state() -> None:
    renderer = StickmanRenderer(execute_enabled=False)
    motions = [
        Motion(
            type="zoom",
            target="camera",
            start_time=0.0,
            duration=3.0,
            easing="linear",
            parameters={"from": 1.0, "to": 1.25},
        ),
        Motion(
            type="pan",
            target="camera",
            start_time=1.0,
            duration=2.0,
            easing="linear",
            parameters={"from": {"x": 0.0, "y": 0.0}, "to": {"x": 0.1, "y": 0.0}},
        ),
    ]

    state = renderer._evaluate_motion_state(motions, current_time=1.5, duration=3.0, width=320, height=240, base_action="walk")
    assert state["camera_zoom"] > 1.0
    assert state["camera_pan_x"] > 0


def test_structured_motion_precedence_over_legacy_text() -> None:
    renderer = StickmanRenderer(execute_enabled=False)
    request = RenderRequest(
        job={
            "job_id": "precedence",
            "duration_seconds": 2,
            "camera_instructions": "slow zoom in",
            "animation_instructions": "walk cycle",
            "visual_prompt": "A stickman on screen",
            "motions": [
                {
                    "type": "zoom",
                    "target": "camera",
                    "start_time": 0.0,
                    "duration": 2.0,
                    "easing": "linear",
                    "parameters": {"from": 1.0, "to": 1.15},
                }
            ],
        }
    )

    motions = renderer._collect_motions(request)
    camera_zoom_motions = [motion for motion in motions if motion.target == "camera" and motion.type == "zoom"]
    assert len(camera_zoom_motions) == 1


def test_camera_character_object_and_text_state() -> None:
    renderer = StickmanRenderer(execute_enabled=False)
    motions = [
        Motion(
            type="zoom",
            target="camera",
            start_time=0.0,
            duration=2.0,
            easing="linear",
            parameters={"from": 1.0, "to": 1.2},
        ),
        Motion(
            type="pan",
            target="camera",
            start_time=0.0,
            duration=2.0,
            easing="linear",
            parameters={"from": {"x": 0.0, "y": 0.0}, "to": {"x": 0.05, "y": 0.0}},
        ),
        Motion(
            type="move",
            target="character",
            start_time=0.5,
            duration=1.0,
            easing="linear",
            parameters={"from": {"x": 0.1, "y": 0.75}, "to": {"x": 0.5, "y": 0.75}},
        ),
        Motion(
            type="fade",
            target="text",
            start_time=1.0,
            duration=1.0,
            easing="linear",
            parameters={"from": 0.0, "to": 1.0},
        ),
        Motion(
            type="move",
            target="object",
            start_time=0.0,
            duration=2.0,
            easing="linear",
            parameters={"from": {"x": 0.8, "y": 0.3}, "to": {"x": 0.4, "y": 0.3}},
            target_id="floating-box",
        ),
    ]

    state = renderer._evaluate_motion_state(motions, current_time=1.5, duration=2.0, width=320, height=240, base_action="walk")
    assert state["camera_zoom"] > 1.0
    assert state["camera_pan_x"] > 0
    assert state["character_x"] is not None
    assert state["text_visible"] is True
    assert state["text_opacity"] > 0
    assert "floating-box" in state["object_layers"]


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_structured_motion_renders_real_mp4_and_changes_frames() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config = RenderConfig(
            width=320,
            height=240,
            fps=10,
            video_format="mp4",
            video_codec="libx264",
            audio_format="aac",
            output_directory=tmpdir,
            filename_template="structured_{job_id}.mp4",
        )
        job_spec = RenderJobSpec(
            job_id="structured-motion",
            scene_number=1,
            duration_seconds=2,
            render_type="stickman_animation",
            character_ids=[],
            asset_ids=[],
            visual_prompt="Structured motion validation",
            animation_instructions="Character enters and moves across the frame",
            camera_instructions="Camera zooms in slowly",
            audio_requirements="No audio",
            motions=[
                Motion(
                    type="zoom",
                    target="camera",
                    start_time=0.0,
                    duration=2.0,
                    easing="ease_in_out",
                    parameters={"from": 1.0, "to": 1.2},
                ),
                Motion(
                    type="enter",
                    target="character",
                    start_time=0.5,
                    duration=1.0,
                    easing="ease_out",
                    parameters={"direction": "left"},
                ),
                Motion(
                    type="move",
                    target="character",
                    start_time=1.0,
                    duration=1.0,
                    easing="ease_in_out",
                    parameters={"from": {"x": 0.2, "y": 0.75}, "to": {"x": 0.5, "y": 0.75}},
                ),
                Motion(
                    type="fade",
                    target="text",
                    start_time=1.5,
                    duration=0.5,
                    easing="ease_in_out",
                    parameters={"from": 0.0, "to": 1.0},
                ),
                Motion(
                    type="scale",
                    target="text",
                    start_time=1.5,
                    duration=0.5,
                    easing="ease_out",
                    parameters={"from": 0.85, "to": 1.0},
                ),
            ],
        )

        result = render_stickman_job(job_spec, config)
        assert result["status"] == "completed", result.get("error")
        video_path = Path(result["output_reference"])
        assert video_path.exists()
        assert video_path.stat().st_size > 1000

        duration = float(
            subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                shell=False,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        assert abs(duration - 2.0) < 0.25

        first_frame = Path(tmpdir) / "first.png"
        mid_frame = Path(tmpdir) / "mid.png"
        last_frame = Path(tmpdir) / "last.png"
        _render_frame(video_path, "0.0", first_frame)
        _render_frame(video_path, "1.0", mid_frame)
        _render_frame(video_path, "1.9", last_frame)

        assert _frame_difference(first_frame, mid_frame) > 0
        assert _frame_difference(mid_frame, last_frame) > 0
        assert _frame_difference(first_frame, last_frame) > 0
