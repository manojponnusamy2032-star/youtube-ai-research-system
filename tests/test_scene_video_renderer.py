"""Tests for the FFmpeg scene video renderer."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.services.scene_video_renderer import (
    FORMATS,
    LONG_FORM_FORMAT,
    SHORTS_FORMAT,
    SceneVideoRenderer,
)


def _renderer(tmp_path, execute_enabled: bool = False) -> SceneVideoRenderer:
    """Build a renderer writing into a temporary directory."""
    return SceneVideoRenderer(
        output_directory=str(tmp_path / "scenes"),
        font_path=str(tmp_path / "font.ttf"),
        execute_enabled=execute_enabled,
    )


def test_formats_cover_shorts_and_long_form() -> None:
    """Both target geometries are registered."""
    assert FORMATS["shorts"] == SHORTS_FORMAT
    assert FORMATS["long"] == LONG_FORM_FORMAT
    assert SHORTS_FORMAT.is_vertical
    assert not LONG_FORM_FORMAT.is_vertical


def test_command_encodes_format_geometry(tmp_path) -> None:
    """The generated command carries the requested size and fps."""
    renderer = _renderer(tmp_path)

    command = renderer.build_command(
        text_path=str(tmp_path / "caption.txt"),
        output_path=str(tmp_path / "scene.mp4"),
        duration_seconds=3.5,
        video_format=LONG_FORM_FORMAT,
    )

    joined = " ".join(command)
    assert "s=1920x1080" in joined
    assert "drawtext=" in joined
    assert "libx264" in command
    assert command[command.index("-t") + 1] == "3.500"


def test_command_uses_background_image_when_supplied(tmp_path) -> None:
    """A background image replaces the solid color source."""
    image = tmp_path / "bg.jpg"
    image.write_bytes(b"jpg")
    renderer = _renderer(tmp_path)

    command = renderer.build_command(
        text_path=str(tmp_path / "caption.txt"),
        output_path=str(tmp_path / "scene.mp4"),
        duration_seconds=2.0,
        video_format=SHORTS_FORMAT,
        background_image=str(image),
    )

    joined = " ".join(command)
    assert "lavfi" not in joined
    assert "scale=1080:1920" in joined
    assert "crop=1080:1920" in joined


def test_wrap_text_is_narrower_for_vertical() -> None:
    """Portrait captions wrap to shorter lines than landscape ones."""
    text = "one two three four five six seven eight nine ten eleven twelve"

    vertical_lines = SceneVideoRenderer.wrap_text(text, SHORTS_FORMAT).split("\n")
    landscape_lines = SceneVideoRenderer.wrap_text(text, LONG_FORM_FORMAT).split("\n")

    assert len(vertical_lines) > len(landscape_lines)


def test_wrap_text_rejects_blank_text() -> None:
    """Blank captions are rejected."""
    with pytest.raises(ValueError):
        SceneVideoRenderer.wrap_text("   ", SHORTS_FORMAT)


@pytest.mark.parametrize("scene_number,duration", [(0, 1.0), (1, 0.0), (1, -2.0)])
def test_render_scene_validates_inputs(tmp_path, scene_number, duration) -> None:
    """Invalid scene numbers and durations are rejected."""
    renderer = _renderer(tmp_path)

    with pytest.raises(ValueError):
        renderer.render_scene(scene_number, "hello", duration)


def test_render_scene_builds_command_without_executing(tmp_path) -> None:
    """With execution disabled the caption file is written but FFmpeg is not run."""
    renderer = _renderer(tmp_path)

    with patch("subprocess.run") as run:
        record = renderer.render_scene(2, "Hello there", 4.0, SHORTS_FORMAT)

    run.assert_not_called()
    assert record["status"] == "command_built"
    assert record["scene_number"] == 2
    assert os.path.exists(f"{record['output_reference']}.txt")


def test_render_scene_reports_ffmpeg_failure(tmp_path) -> None:
    """A non-zero FFmpeg exit is reported as a failed record."""
    renderer = _renderer(tmp_path, execute_enabled=True)

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "subprocess.run", return_value=MagicMock(returncode=1, stderr="bad filter")
    ):
        record = renderer.render_scene(1, "Hello", 2.0)

    assert record["status"] == "failed"
    assert "return code 1" in record["error"]


def test_render_scene_completes_when_output_exists(tmp_path) -> None:
    """A successful run returns an assembler-compatible record."""
    renderer = _renderer(tmp_path, execute_enabled=True)

    def fake_run(command, **kwargs):
        with open(command[-1], "wb") as handle:
            handle.write(b"mp4")
        return MagicMock(returncode=0, stderr="")

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "subprocess.run", side_effect=fake_run
    ):
        record = renderer.render_scene(1, "Hello", 2.0)

    assert record["status"] == "completed"
    assert record["duration_seconds"] == 2.0
    assert os.path.exists(record["output_reference"])
