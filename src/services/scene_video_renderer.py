"""Scene video renderer.

Renders a single narrated scene into an MP4 clip using FFmpeg only: a solid
background (or a supplied background image) with centered, wrapped caption
text held for the scene duration. No paid asset or rendering service is used.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


@dataclass(frozen=True)
class VideoFormat:
    """Output geometry for a rendered video."""

    name: str
    width: int
    height: int
    fps: int = 30

    @property
    def is_vertical(self) -> bool:
        """Return True for portrait (Shorts-style) output."""
        return self.height > self.width


SHORTS_FORMAT = VideoFormat(name="shorts", width=1080, height=1920, fps=30)
LONG_FORM_FORMAT = VideoFormat(name="long", width=1920, height=1080, fps=30)
FORMATS = {SHORTS_FORMAT.name: SHORTS_FORMAT, LONG_FORM_FORMAT.name: LONG_FORM_FORMAT}


class SceneVideoRenderer:
    """Renders caption scenes to MP4 clips with FFmpeg."""

    def __init__(
        self,
        output_directory: str = "output/scenes",
        font_path: str | None = None,
        background_color: str = "0x101820",
        text_color: str = "white",
        execute_enabled: bool = True,
    ) -> None:
        """Initialize the scene renderer.

        Args:
            output_directory: Directory for rendered scene clips.
            font_path: TTF font used for captions. Auto-detected when omitted.
            background_color: FFmpeg color for the generated background.
            text_color: Caption color.
            execute_enabled: When False, ``render_scene`` only builds commands.
        """
        self.output_directory = output_directory
        self.font_path = font_path or self._detect_font()
        self.background_color = background_color
        self.text_color = text_color
        self.execute_enabled = execute_enabled

    def is_available(self) -> bool:
        """Return True when FFmpeg is on PATH."""
        return shutil.which("ffmpeg") is not None

    def render_scene(
        self,
        scene_number: int,
        text: str,
        duration_seconds: float,
        video_format: VideoFormat = SHORTS_FORMAT,
        background_image: str | None = None,
    ) -> dict[str, Any]:
        """Render one scene clip.

        Args:
            scene_number: 1-based scene index, used for ordering and naming.
            text: Caption text drawn on the scene.
            duration_seconds: Clip duration; must be positive.
            video_format: Output geometry.
            background_image: Optional image used instead of a solid color.

        Returns:
            A render output record compatible with ``VideoAssembler``.
        """
        if scene_number < 1:
            raise ValueError("scene_number must be >= 1")
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")

        os.makedirs(self.output_directory, exist_ok=True)
        output_path = os.path.join(
            self.output_directory, f"scene_{scene_number:03d}_{video_format.name}.mp4"
        )
        text_path = f"{output_path}.txt"
        with open(text_path, "w", encoding="utf-8") as handle:
            handle.write(self.wrap_text(text, video_format))

        command = self.build_command(
            text_path=text_path,
            output_path=output_path,
            duration_seconds=duration_seconds,
            video_format=video_format,
            background_image=background_image,
        )

        record: dict[str, Any] = {
            "job_id": f"scene-{scene_number}",
            "scene_number": scene_number,
            "output_reference": output_path,
            "duration_seconds": duration_seconds,
            "command": command,
        }

        if not self.execute_enabled:
            record["status"] = "command_built"
            return record

        if not self.is_available():
            record["status"] = "failed"
            record["error"] = "FFmpeg is not available on PATH"
            return record

        result = subprocess.run(
            command, shell=False, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0 or not os.path.exists(output_path):
            record["status"] = "failed"
            record["error"] = f"FFmpeg failed with return code {result.returncode}"
            record["stderr"] = (result.stderr or "")[:500]
            return record

        record["status"] = "completed"
        logger.info(f"Rendered scene {scene_number} to {output_path}")
        return record

    def build_command(
        self,
        text_path: str,
        output_path: str,
        duration_seconds: float,
        video_format: VideoFormat,
        background_image: str | None = None,
    ) -> list[str]:
        """Build the FFmpeg command for one scene clip."""
        font_size = self.font_size(video_format)
        drawtext = "drawtext=" + ":".join(
            [
                f"textfile={self._escape_filter_path(text_path)}",
                f"fontfile={self._escape_filter_path(self.font_path)}",
                f"fontcolor={self.text_color}",
                f"fontsize={font_size}",
                f"line_spacing={font_size // 3}",
                "x=(w-text_w)/2",
                "y=(h-text_h)/2",
                "box=1",
                "boxcolor=black@0.45",
                f"boxborderw={font_size // 3}",
            ]
        )

        if background_image:
            scale = (
                f"scale={video_format.width}:{video_format.height}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={video_format.width}:{video_format.height}"
            )
            inputs = ["-loop", "1", "-i", background_image]
            filters = f"{scale},{drawtext},format=yuv420p"
        else:
            source = (
                f"color=c={self.background_color}:"
                f"s={video_format.width}x{video_format.height}:r={video_format.fps}"
            )
            inputs = ["-f", "lavfi", "-i", source]
            filters = f"{drawtext},format=yuv420p"

        return [
            "ffmpeg",
            "-y",
            *inputs,
            "-t",
            f"{duration_seconds:.3f}",
            "-vf",
            filters,
            "-r",
            str(video_format.fps),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]

    @staticmethod
    def font_size(video_format: VideoFormat) -> int:
        """Return a caption font size proportional to the output width."""
        return max(28, video_format.width // (18 if video_format.is_vertical else 28))

    @staticmethod
    def wrap_text(text: str, video_format: VideoFormat) -> str:
        """Wrap caption text to a readable line length for the format."""
        cleaned = " ".join(str(text).split())
        if not cleaned:
            raise ValueError("text cannot be empty")
        width = 22 if video_format.is_vertical else 42
        return "\n".join(textwrap.wrap(cleaned, width=width)) or cleaned

    @staticmethod
    def _escape_filter_path(path: str) -> str:
        """Escape a path for use inside an FFmpeg filter argument."""
        return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    @staticmethod
    def _detect_font() -> str:
        """Return the first available caption font."""
        for candidate in FONT_CANDIDATES:
            if os.path.exists(candidate):
                return candidate
        raise RuntimeError(
            "No caption font found. Install DejaVu fonts or pass font_path."
        )
