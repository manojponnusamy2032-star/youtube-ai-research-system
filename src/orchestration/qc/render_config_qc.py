"""Render configuration QC validator.

Validates the final media against the requested ``RenderConfig``.
Detects mismatches in width, height, fps, format, video codec, audio codec.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from src.orchestration.qc.models import QCCheck, QCStatus, QCSeverity


def _run_ffprobe(path: str) -> dict[str, Any] | None:
    """Run ffprobe on a file and return parsed JSON output."""
    if shutil.which("ffprobe") is None:
        return None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return {"error": result.stderr.strip() or "ffprobe failed"}

    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {"error": "ffprobe output not valid JSON"}


def _parse_fps(fps_raw: str) -> float | None:
    """Parse FPS from r_frame_rate string like '30/1' or '30000/1001'."""
    if not fps_raw:
        return None
    if "/" in str(fps_raw):
        num, den = str(fps_raw).split("/", 1)
        try:
            return float(num) / float(den) if float(den) != 0 else None
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(fps_raw)
    except ValueError:
        return None
def _check_render_config(path: str | None, render_config: dict[str, Any]) -> QCCheck:
    """Validate the actual output matches the requested render configuration."""
    if not path:
        return QCCheck(
            check_name="render_config_match",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No output path provided",
        )

    if not render_config:
        return QCCheck(
            check_name="render_config_match",
            status=QCStatus.PASS,
            severity=QCSeverity.INFO,
            message="No render config provided; skipping config match",
        )

    probe = _run_ffprobe(path)
    if probe is None:
        return QCCheck(
            check_name="render_config_match",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="ffprobe unavailable; cannot validate render config",
        )

    if "error" in probe:
        return QCCheck(
            check_name="render_config_match",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message=f"ffprobe error: {probe['error'][:200]}",
        )

    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if not video_streams:
        return QCCheck(
            check_name="render_config_match",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No video stream found for config validation",
        )

    vs = video_streams[0]
    actual_width = vs.get("width", 0)
    actual_height = vs.get("height", 0)
    actual_video_codec = vs.get("codec_name", "")
    actual_fps = _parse_fps(vs.get("r_frame_rate", ""))

    actual_audio_codec = ""
    if audio_streams:
        actual_audio_codec = audio_streams[0].get("codec_name", "")

    format_info = probe.get("format", {})
    actual_format = format_info.get("format_name", "")

    problems: list[str] = []

    requested_width = render_config.get("width")
    requested_height = render_config.get("height")
    requested_fps = render_config.get("fps")
    requested_video_codec = render_config.get("video_codec", "")
    requested_audio_codec = render_config.get("audio_codec") or render_config.get("audio_format", "")

    if requested_width and actual_width and int(requested_width) != int(actual_width):
        problems.append(f"width mismatch: requested={requested_width}, actual={actual_width}")
    if requested_height and actual_height and int(requested_height) != int(actual_height):
        problems.append(f"height mismatch: requested={requested_height}, actual={actual_height}")

    if requested_fps and actual_fps is not None:
        if abs(float(requested_fps) - actual_fps) > 1.0:
            problems.append(f"fps mismatch: requested={requested_fps}, actual={actual_fps:.2f}")

    if requested_video_codec and actual_video_codec:
        # Normalize codec names for comparison.
        # FFmpeg encoder name "libx264" → ffprobe reports "h264"
        # Both mean H.264, so we need an alias map.
        _CODEC_ALIASES: dict[str, str] = {
            "x264": "h264",
            "libx264": "h264",
            "x265": "h265",
            "libx265": "h265",
            "mpeg4": "mpeg4",
        }
        req_low = requested_video_codec.lower().strip()
        act_low = actual_video_codec.lower().strip()
        req_canonical = _CODEC_ALIASES.get(req_low, req_low)
        act_canonical = _CODEC_ALIASES.get(act_low, act_low)
        if req_canonical != act_canonical:
            problems.append(
                f"video codec mismatch: requested={requested_video_codec}, "
                f"actual={actual_video_codec}"
            )

    if requested_audio_codec and actual_audio_codec:
        req = requested_audio_codec.lower()
        act = actual_audio_codec.lower()
        if req != act and not req.startswith(act) and not act.startswith(req):
            problems.append(
                f"audio codec mismatch: requested={requested_audio_codec}, "
                f"actual={actual_audio_codec}"
            )

    if problems:
        return QCCheck(
            check_name="render_config_match",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Render config mismatch: {'; '.join(problems)}",
            details={
                "requested": render_config,
                "actual": {
                    "width": actual_width,
                    "height": actual_height,
                    "fps": actual_fps,
                    "video_codec": actual_video_codec,
                    "audio_codec": actual_audio_codec,
                    "format": actual_format,
                },
                "problems": problems,
            },
        )

    return QCCheck(
        check_name="render_config_match",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="Render configuration matches output",
        details={
            "requested": render_config,
            "actual": {
                "width": actual_width,
                "height": actual_height,
                "fps": actual_fps,
                "video_codec": actual_video_codec,
                "audio_codec": actual_audio_codec,
                "format": actual_format,
            },
        },
    )


def run_render_config_qc(
    output_path: str | None,
    render_config: dict[str, Any] | None = None,
) -> list[QCCheck]:
    """Run render configuration QC checks.

    Args:
        output_path: Path to the MP4 file (or None).
        render_config: Requested render configuration.

    Returns:
        A list of ``QCCheck`` results.
    """
    return [
        _check_render_config(output_path, render_config or {}),
    ]

