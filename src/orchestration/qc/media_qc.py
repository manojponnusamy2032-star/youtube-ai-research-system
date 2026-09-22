"""Media file QC validator.

Inspects the actual generated MP4 using ffprobe.  Checks file existence,
container validity, video/audio streams, codecs, resolution, FPS, duration,
and corruption.

A file is NOT considered valid merely because it exists.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.orchestration.qc.models import QCCheck, QCStatus, QCSeverity


def _run_ffprobe(path: str) -> dict[str, Any] | None:
    """Run ffprobe on a file and return parsed JSON output.

    Returns None if ffprobe is unavailable or the file cannot be probed.
    """
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
        return {"error": result.stderr.strip() or "ffprobe failed", "raw": result.stdout}

    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {"error": "ffprobe output not valid JSON", "raw": result.stdout[:500]}


def _check_file_exists(path: str | None) -> QCCheck:
    """Validate the MP4 file exists and is non-empty."""
    if not path:
        return QCCheck(
            check_name="media_file_exists",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No output path provided",
        )

    p = Path(path)
    if not p.exists():
        return QCCheck(
            check_name="media_file_exists",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"MP4 file does not exist: {path}",
        )

    if not p.is_file():
        return QCCheck(
            check_name="media_file_exists",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Output path is not a regular file: {path}",
        )

    size = p.stat().st_size
    if size == 0:
        return QCCheck(
            check_name="media_file_exists",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="MP4 file exists but is zero bytes",
        )

    return QCCheck(
        check_name="media_file_exists",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"MP4 file exists ({size:,} bytes)",
        details={"file_size_bytes": size},
    )


def _check_container_valid(path: str | None) -> QCCheck:
    """Validate the MP4 container is readable by ffprobe."""
    if not path:
        return QCCheck(
            check_name="media_container_valid",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No output path provided",
        )

    probe = _run_ffprobe(path)
    if probe is None:
        return QCCheck(
            check_name="media_container_valid",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="ffprobe unavailable; cannot validate container",
        )

    if "error" in probe:
        return QCCheck(
            check_name="media_container_valid",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"ffprobe could not read file: {probe['error'][:200]}",
            details={"probe_error": probe["error"][:500]},
        )

    streams = probe.get("streams", [])
    if not streams:
        return QCCheck(
            check_name="media_container_valid",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="ffprobe found no streams in file",
        )

    return QCCheck(
        check_name="media_container_valid",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Container valid with {len(streams)} stream(s)",
    )
def _check_video_stream(path: str | None) -> QCCheck:
    """Validate the video stream exists with valid codec/resolution/fps."""
    if not path:
        return QCCheck(
            check_name="media_video_stream",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No output path provided",
        )

    probe = _run_ffprobe(path)
    if probe is None:
        return QCCheck(
            check_name="media_video_stream",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="ffprobe unavailable; cannot validate video stream",
        )

    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]

    if not video_streams:
        return QCCheck(
            check_name="media_video_stream",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No video stream found in MP4",
        )

    vs = video_streams[0]
    codec = vs.get("codec_name", "")
    width = vs.get("width", 0)
    height = vs.get("height", 0)

    problems: list[str] = []
    if not codec:
        problems.append("missing video codec")
    if not width or width <= 0:
        problems.append(f"invalid width: {width}")
    if not height or height <= 0:
        problems.append(f"invalid height: {height}")

    # Parse FPS from r_frame_rate (e.g. "30/1" or "30000/1001").
    fps_raw = vs.get("r_frame_rate", "")
    fps: float | None = None
    if fps_raw and "/" in str(fps_raw):
        num, den = str(fps_raw).split("/", 1)
        try:
            fps = float(num) / float(den) if float(den) != 0 else None
        except (ValueError, ZeroDivisionError):
            fps = None
    elif fps_raw:
        try:
            fps = float(fps_raw)
        except ValueError:
            fps = None

    if fps is None or fps <= 0:
        problems.append(f"invalid FPS: {fps_raw}")

    if problems:
        return QCCheck(
            check_name="media_video_stream",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Video stream issues: {'; '.join(problems)}",
            details={
                "codec": codec,
                "width": width,
                "height": height,
                "fps_raw": fps_raw,
                "fps": fps,
                "problems": problems,
            },
        )

    return QCCheck(
        check_name="media_video_stream",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Video stream valid: {codec} {width}x{height} @ {fps:.2f}fps",
        details={"codec": codec, "width": width, "height": height, "fps": fps},
    )

def _check_audio_stream(path: str | None) -> QCCheck:
    """Validate the audio stream exists when expected."""
    if not path:
        return QCCheck(
            check_name="media_audio_stream",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No output path provided",
        )

    probe = _run_ffprobe(path)
    if probe is None:
        return QCCheck(
            check_name="media_audio_stream",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="ffprobe unavailable; cannot validate audio stream",
        )

    streams = probe.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if not audio_streams:
        return QCCheck(
            check_name="media_audio_stream",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No audio stream found (audio expected)",
        )

    audio = audio_streams[0]
    codec = audio.get("codec_name", "")
    sample_rate = audio.get("sample_rate", 0)

    problems: list[str] = []
    if not codec:
        problems.append("missing audio codec")
    if not sample_rate or int(sample_rate) <= 0:
        problems.append(f"invalid sample_rate: {sample_rate}")

    if problems:
        return QCCheck(
            check_name="media_audio_stream",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Audio stream issues: {'; '.join(problems)}",
            details={"codec": codec, "sample_rate": sample_rate, "problems": problems},
        )

    return QCCheck(
        check_name="media_audio_stream",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Audio stream valid: {codec} @ {sample_rate}Hz",
        details={"codec": codec, "sample_rate": int(sample_rate)},
    )


def _check_duration(path: str | None, planned_duration: float | None = None) -> QCCheck:
    """Validate container/video/audio duration and compare to planned."""
    if not path:
        return QCCheck(
            check_name="media_duration",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No output path provided",
        )

    probe = _run_ffprobe(path)
    if probe is None:
        return QCCheck(
            check_name="media_duration",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="ffprobe unavailable; cannot validate duration",
        )

    if "error" in probe:
        return QCCheck(
            check_name="media_duration",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"ffprobe error: {probe['error'][:200]}",
        )

    format_info = probe.get("format", {})
    container_duration_str = format_info.get("duration", "")
    container_duration: float | None = None
    if container_duration_str:
        try:
            container_duration = float(container_duration_str)
        except ValueError:
            pass

    if container_duration is None or container_duration <= 0:
        return QCCheck(
            check_name="media_duration",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Invalid container duration: {container_duration}",
        )

    # Compare to planned duration if available.
    if planned_duration is not None and planned_duration > 0:
        mismatch = abs(container_duration - planned_duration)
        if mismatch > max(10, planned_duration * 0.5):
            return QCCheck(
                check_name="media_duration",
                status=QCStatus.FAIL,
                severity=QCSeverity.FAIL,
                message=(
                    f"Major duration mismatch: actual={container_duration:.2f}s, "
                    f"planned={planned_duration:.2f}s (delta={mismatch:.2f}s)"
                ),
                details={
                    "container_duration": container_duration,
                    "planned_duration": planned_duration,
                    "delta": mismatch,
                },
            )
        if mismatch > max(2, planned_duration * 0.1):
            return QCCheck(
                check_name="media_duration",
                status=QCStatus.WARN,
                severity=QCSeverity.WARN,
                message=(
                    f"Minor duration mismatch: actual={container_duration:.2f}s, "
                    f"planned={planned_duration:.2f}s (delta={mismatch:.2f}s)"
                ),
                details={
                    "container_duration": container_duration,
                    "planned_duration": planned_duration,
                    "delta": mismatch,
                },
            )

    return QCCheck(
        check_name="media_duration",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Duration valid: {container_duration:.2f}s",
        details={"container_duration": container_duration, "planned_duration": planned_duration},
    )


def run_media_qc(
    output_path: str | None,
    planned_duration: float | None = None,
) -> list[QCCheck]:
    """Run all media QC checks.

    Args:
        output_path: Path to the MP4 file (or None).
        planned_duration: Expected duration in seconds (or None).

    Returns:
        A list of ``QCCheck`` results.
    """
    return [
        _check_file_exists(output_path),
        _check_container_valid(output_path),
        _check_video_stream(output_path),
        _check_audio_stream(output_path),
        _check_duration(output_path, planned_duration),
    ]

