"""Tests for RenderConfig model."""

from __future__ import annotations

import pytest

from src.models.content_package import RenderConfig, RenderJobPlan, RenderJobSpec


def test_default_render_config() -> None:
    """Test that default RenderConfig has sensible YouTube defaults."""
    config = RenderConfig()
    
    assert config.width == 1920
    assert config.height == 1080
    assert config.fps == 30
    assert config.aspect_ratio == "16:9"
    assert config.video_format == "mp4"
    assert config.video_codec == "h264"
    assert config.audio_format == "aac"
    assert config.output_directory == "output"
    assert config.filename_template == "{job_id}.mp4"


def test_custom_render_config() -> None:
    """Test that custom RenderConfig values are accepted."""
    config = RenderConfig(
        width=1280,
        height=720,
        fps=60,
        aspect_ratio="16:9",
        video_format="mov",
        video_codec="prores",
        audio_format="wav",
        output_directory="renders",
        filename_template="scene_{scene_number}_{job_id}.mp4",
    )
    
    assert config.width == 1280
    assert config.height == 720
    assert config.fps == 60
    assert config.aspect_ratio == "16:9"
    assert config.video_format == "mov"
    assert config.video_codec == "prores"
    assert config.audio_format == "wav"
    assert config.output_directory == "renders"
    assert config.filename_template == "scene_{scene_number}_{job_id}.mp4"


def test_invalid_width_raises_error() -> None:
    """Test that invalid width raises ValueError."""
    with pytest.raises(ValueError, match="width must be positive"):
        RenderConfig(width=0)
    
    with pytest.raises(ValueError, match="width must be positive"):
        RenderConfig(width=-1920)


def test_invalid_height_raises_error() -> None:
    """Test that invalid height raises ValueError."""
    with pytest.raises(ValueError, match="height must be positive"):
        RenderConfig(height=0)
    
    with pytest.raises(ValueError, match="height must be positive"):
        RenderConfig(height=-1080)


def test_invalid_fps_raises_error() -> None:
    """Test that invalid FPS raises ValueError."""
    with pytest.raises(ValueError, match="fps must be positive"):
        RenderConfig(fps=0)
    
    with pytest.raises(ValueError, match="fps must be positive"):
        RenderConfig(fps=-30)


def test_empty_aspect_ratio_raises_error() -> None:
    """Test that empty aspect_ratio raises ValueError."""
    with pytest.raises(ValueError, match="aspect_ratio cannot be empty"):
        RenderConfig(aspect_ratio="")


def test_empty_video_format_raises_error() -> None:
    """Test that empty video_format raises ValueError."""
    with pytest.raises(ValueError, match="video_format cannot be empty"):
        RenderConfig(video_format="")


def test_empty_video_codec_raises_error() -> None:
    """Test that empty video_codec raises ValueError."""
    with pytest.raises(ValueError, match="video_codec cannot be empty"):
        RenderConfig(video_codec="")


def test_empty_audio_format_raises_error() -> None:
    """Test that empty audio_format raises ValueError."""
    with pytest.raises(ValueError, match="audio_format cannot be empty"):
        RenderConfig(audio_format="")


def test_empty_output_directory_raises_error() -> None:
    """Test that empty output_directory raises ValueError."""
    with pytest.raises(ValueError, match="output_directory cannot be empty"):
        RenderConfig(output_directory="")


def test_empty_filename_template_raises_error() -> None:
    """Test that empty filename_template raises ValueError."""
    with pytest.raises(ValueError, match="filename_template cannot be empty"):
        RenderConfig(filename_template="")


def test_render_job_plan_without_render_config() -> None:
    """Test that RenderJobPlan works without render_config (backward compatibility)."""
    job_spec = RenderJobSpec(
        job_id="job-1",
        scene_number=1,
        duration_seconds=45,
        render_type="host_footage",
        character_ids=["char-1"],
        asset_ids=["asset-1"],
        visual_prompt="Test scene",
        animation_instructions="Fade in",
        camera_instructions="Wide shot",
        audio_requirements="Narration",
    )
    
    plan = RenderJobPlan(
        total_jobs=1,
        jobs=[job_spec],
        total_duration_seconds=45,
    )
    
    assert plan.render_config is None
    assert plan.total_jobs == 1
    assert len(plan.jobs) == 1
    
    # Verify to_dict works without render_config
    result = plan.to_dict()
    assert "render_config" not in result
    assert result["total_jobs"] == 1


def test_render_job_plan_with_render_config() -> None:
    """Test that RenderJobPlan works with render_config."""
    job_spec = RenderJobSpec(
        job_id="job-1",
        scene_number=1,
        duration_seconds=45,
        render_type="host_footage",
        character_ids=["char-1"],
        asset_ids=["asset-1"],
        visual_prompt="Test scene",
        animation_instructions="Fade in",
        camera_instructions="Wide shot",
        audio_requirements="Narration",
    )
    
    render_config = RenderConfig(
        width=1280,
        height=720,
        fps=60,
        output_directory="custom_output",
    )
    
    plan = RenderJobPlan(
        total_jobs=1,
        jobs=[job_spec],
        total_duration_seconds=45,
        render_config=render_config,
    )
    
    assert plan.render_config is not None
    assert plan.render_config.width == 1280
    assert plan.render_config.height == 720
    assert plan.render_config.fps == 60
    assert plan.render_config.output_directory == "custom_output"
    
    # Verify to_dict includes render_config
    result = plan.to_dict()
    assert "render_config" in result
    assert result["render_config"]["width"] == 1280
    assert result["render_config"]["height"] == 720
    assert result["render_config"]["fps"] == 60
    assert result["render_config"]["output_directory"] == "custom_output"


def test_render_config_whitespace_only_values_raise_error() -> None:
    """Test that whitespace-only values raise ValueError."""
    with pytest.raises(ValueError, match="aspect_ratio cannot be empty"):
        RenderConfig(aspect_ratio="   ")
    
    with pytest.raises(ValueError, match="video_format cannot be empty"):
        RenderConfig(video_format="  ")
    
    with pytest.raises(ValueError, match="output_directory cannot be empty"):
        RenderConfig(output_directory="\t")