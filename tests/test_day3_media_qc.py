"""Day-3 Media QC tests."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from src.orchestration.qc.media_qc import run_media_qc
from src.orchestration.qc.render_config_qc import run_render_config_qc
from src.orchestration.qc.models import QCStatus


def _make_valid_mp4(path: Path, width: int = 320, height: int = 240, fps: int = 24, duration: int = 2) -> Path:
    """Create a small valid MP4 using FFmpeg."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:d={duration}:r={fps}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        timeout=30,
        shell=False,
    )
    return path


class TestMediaQCValid:
    def test_valid_mp4(self, tmp_path: Path):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        mp4 = _make_valid_mp4(tmp_path / "valid.mp4")
        assert mp4.exists(), "FFmpeg did not create the MP4"
        checks = run_media_qc(str(mp4), planned_duration=2.0)
        for check in checks:
            assert check.status == QCStatus.PASS, f"{check.check_name}: {check.message}"


class TestMediaQCMissingFile:
    def test_missing_file(self):
        checks = run_media_qc("/nonexistent/path/video.mp4")
        exists = next(c for c in checks if c.check_name == "media_file_exists")
        assert exists.status == QCStatus.FAIL

    def test_none_path(self):
        checks = run_media_qc(None)
        exists = next(c for c in checks if c.check_name == "media_file_exists")
        assert exists.status == QCStatus.FAIL

    def test_zero_byte_file(self, tmp_path: Path):
        mp4 = tmp_path / "empty.mp4"
        mp4.write_bytes(b"")
        checks = run_media_qc(str(mp4))
        exists = next(c for c in checks if c.check_name == "media_file_exists")
        assert exists.status == QCStatus.FAIL
        assert "zero bytes" in exists.message


class TestMediaQCCorruptFile:
    def test_invalid_mp4(self, tmp_path: Path):
        mp4 = tmp_path / "corrupt.mp4"
        mp4.write_bytes(b"not a valid mp4 file content")
        checks = run_media_qc(str(mp4))
        container = next(c for c in checks if c.check_name == "media_container_valid")
        assert container.status == QCStatus.FAIL


class TestRenderConfigQC:
    def test_matching_config(self, tmp_path: Path):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        mp4 = _make_valid_mp4(tmp_path / "config_match.mp4", width=320, height=240, fps=24)
        assert mp4.exists(), "FFmpeg did not create the MP4"
        checks = run_render_config_qc(str(mp4), {
            "width": 320,
            "height": 240,
            "fps": 24,
            "video_codec": "libx264",
            "audio_format": "aac",
        })
        config = next(c for c in checks if c.check_name == "render_config_match")
        assert config.status == QCStatus.PASS, config.message

    def test_mismatched_config(self, tmp_path: Path):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        mp4 = _make_valid_mp4(tmp_path / "config_mismatch.mp4", width=320, height=240, fps=24)
        assert mp4.exists(), "FFmpeg did not create the MP4"
        checks = run_render_config_qc(str(mp4), {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "libx264",
            "audio_format": "aac",
        })
        config = next(c for c in checks if c.check_name == "render_config_match")
        assert config.status == QCStatus.FAIL
        assert "width mismatch" in config.message or "height mismatch" in config.message
