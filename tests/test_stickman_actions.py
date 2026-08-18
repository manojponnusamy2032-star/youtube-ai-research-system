"""Tests for the StickmanRenderer character-action system.

Verifies action detection from job instructions, deterministic pose
computation, and that different actions produce visibly different
output files.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.models.content_package import RenderConfig, RenderJobSpec
from src.services.stickman_renderer import StickmanRenderer, render_stickman_job


def _ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    return FFmpegRenderer().is_available()


def _config(tmpdir: str) -> RenderConfig:
    """Create a small render config."""
    return RenderConfig(
        width=160,
        height=120,
        fps=5,
        video_format="mp4",
        video_codec="libx264",
        audio_format="aac",
        output_directory=tmpdir,
        filename_template="action_{job_id}.mp4",
    )


def _job(action_instructions: str, job_id: str = "job", duration: int = 1) -> RenderJobSpec:
    """Create a RenderJobSpec with specific animation instructions."""
    return RenderJobSpec(
        job_id=job_id,
        scene_number=1,
        duration_seconds=duration,
        render_type="stickman_animation",
        character_ids=[],
        asset_ids=[],
        visual_prompt="A stickman character",
        animation_instructions=action_instructions,
        camera_instructions="Static",
        audio_requirements="None",
        audio_request=None,
    )


def _renderer(tmpdir: str) -> StickmanRenderer:
    """Create a StickmanRenderer instance."""
    return StickmanRenderer(execute_enabled=True)


def test_action_detection_walk() -> None:
    """Test that 'walk' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Walk cycle with arm oscillation", "visual_prompt": ""}
    assert renderer._detect_action(job) == "walk"


def test_action_detection_run() -> None:
    """Test that 'run' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Running with high knees", "visual_prompt": ""}
    assert renderer._detect_action(job) == "run"


def test_action_detection_point() -> None:
    """Test that 'point' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Pointing at the target", "visual_prompt": ""}
    assert renderer._detect_action(job) == "point"


def test_action_detection_wave() -> None:
    """Test that 'wave' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Waving hello to the audience", "visual_prompt": ""}
    assert renderer._detect_action(job) == "wave"


def test_action_detection_jump() -> None:
    """Test that 'jump' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Jumping up and down excitedly", "visual_prompt": ""}
    assert renderer._detect_action(job) == "jump"


def test_action_detection_talk() -> None:
    """Test that 'talk' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Talking to the camera", "visual_prompt": ""}
    assert renderer._detect_action(job) == "talk"


def test_action_detection_surprised() -> None:
    """Test that 'surprised' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Looking surprised", "visual_prompt": ""}
    assert renderer._detect_action(job) == "surprised"


def test_action_detection_idle() -> None:
    """Test that 'idle' action is detected from instructions."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Standing idle", "visual_prompt": ""}
    assert renderer._detect_action(job) == "idle"


def test_action_detection_defaults_to_walk() -> None:
    """Test that unknown instructions default to 'walk'."""
    renderer = StickmanRenderer(execute_enabled=False)
    job = {"animation_instructions": "Some unknown instruction", "visual_prompt": ""}
    assert renderer._detect_action(job) == "walk"


def test_pose_is_deterministic() -> None:
    """Test that the same action at the same time produces the same pose."""
    renderer = StickmanRenderer(execute_enabled=False)
    pose1 = renderer._compute_pose("walk", 0.5, 2.0, 320, 240)
    pose2 = renderer._compute_pose("walk", 0.5, 2.0, 320, 240)
    assert pose1 == pose2


def test_pose_stickman_x_differs_walk_vs_idle() -> None:
    """Test that walk moves the character while idle keeps it centered."""
    renderer = StickmanRenderer(execute_enabled=False)
    walk_pose = renderer._compute_pose("walk", 1.0, 2.0, 320, 240)
    idle_pose = renderer._compute_pose("idle", 1.0, 2.0, 320, 240)
    # Walk starts at 15% width = 48, idle stays at 50% = 160
    assert walk_pose.stickman_x != idle_pose.stickman_x


def test_pose_arm_positions_differ_between_actions() -> None:
    """Test that different actions produce different arm positions."""
    renderer = StickmanRenderer(execute_enabled=False)
    walk_pose = renderer._compute_pose("walk", 0.5, 2.0, 320, 240)
    point_pose = renderer._compute_pose("point", 0.5, 2.0, 320, 240)
    surprised_pose = renderer._compute_pose("surprised", 0.5, 2.0, 320, 240)
    # All three actions should have visibly different right-arm X positions
    assert point_pose.right_arm_x != walk_pose.right_arm_x
    assert surprised_pose.right_arm_x != walk_pose.right_arm_x
    assert point_pose.right_arm_x != surprised_pose.right_arm_x


def test_supported_actions_are_complete() -> None:
    """Test that all 8 supported actions are recognized."""
    renderer = StickmanRenderer(execute_enabled=False)
    supported = {"idle", "walk", "run", "point", "wave", "jump", "talk", "surprised"}
    for action in supported:
        pose = renderer._compute_pose(action, 0.5, 2.0, 320, 240)
        assert pose is not None
        assert pose.head_radius > 0


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_each_action_renders_valid_mp4() -> None:
    """Test that each supported action produces a valid MP4 file."""
    actions = ["idle", "walk", "run", "point", "wave", "jump", "talk", "surprised"]
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _config(tmpdir)
        for action in actions:
            job_spec = _job(action, job_id=f"test-{action}", duration=1)
            result = render_stickman_job(job_spec, config)
            assert result["status"] == "completed", \
                f"Action '{action}' failed: {result.get('error', 'unknown')}"
            output_path = Path(result["output_reference"])
            assert output_path.exists()
            assert output_path.stat().st_size > 1000


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
def test_actions_produce_distinct_outputs() -> None:
    """Test that different actions produce differently-sized output files (visibly different)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = _config(tmpdir)
        sizes = {}
        for action in ["idle", "walk", "run", "point", "wave", "jump", "talk", "surprised"]:
            job_spec = _job(action, job_id=f"distinct-{action}", duration=1)
            result = render_stickman_job(job_spec, config)
            assert result["status"] == "completed"
            output_path = Path(result["output_reference"])
            sizes[action] = output_path.stat().st_size

        # At least some actions should produce meaningfully different sizes
        # due to different animation patterns.
        unique_sizes = set(sizes.values())
        assert len(unique_sizes) >= 4, \
            f"Expected at least 4 distinct output sizes, got {len(unique_sizes)}: {sizes}"