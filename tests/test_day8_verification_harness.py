#!/usr/bin/env python3
"""Day-8 verification harness tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from run_day8_verification import (
    RENDER_STATUS_COMPLETED, RENDER_STATUS_FAILED,
    discover_mp4, validate_mp4_with_ffprobe,
    validate_render_progress, validate_visual_plan,
    verify_job_directory,
)


@pytest.fixture
def tmp_job_dir(tmp_path: Path) -> Path:
    d = tmp_path / "job_001"
    d.mkdir()
    return d


@pytest.fixture
def valid_visual_plan() -> dict[str, Any]:
    return {"topic": "Test", "title": "Test Title", "scenes": [
        {"scene_number": 1, "duration_seconds": 10.0},
        {"scene_number": 2, "duration_seconds": 15.0},
    ]}


@pytest.fixture
def valid_render_progress() -> dict[str, Any]:
    return {
        "job_id": "test-job", "status": RENDER_STATUS_COMPLETED,
        "tasks_total": 6, "tasks_done": 6,
        "current_stage": "render", "failures": [],
        "started_at": "2024-01-01T00:00:00Z",
        "completed_at": "2024-01-01T00:01:00Z",
        "total_ms": 60000, "work_ms": 55000,
        "total_frames": 150, "rendered_frames": 150,
        "frames_per_second": 25.0, "frame_ms": 40,
        "remaining": 0, "eta_seconds": 0,
        "scenes": [
            {"scene_number": 1, "status": "completed", "duration_seconds": 25.0},
            {"scene_number": 2, "status": "completed", "duration_seconds": 25.0},
        ],
    }


@pytest.fixture
def failed_render_progress() -> dict[str, Any]:
    return {
        "job_id": "test-job", "status": RENDER_STATUS_FAILED,
        "tasks_total": 6, "tasks_done": 4,
        "current_stage": "render", "failures": ["scene_003"],
        "started_at": "2024-01-01T00:00:00Z",
        "completed_at": "2024-01-01T00:01:00Z",
        "total_ms": 60000, "work_ms": 40000,
        "total_frames": 150, "rendered_frames": 100,
        "frames_per_second": 25.0, "frame_ms": 40,
        "remaining": 50, "eta_seconds": 50,
        "scenes": [
            {"scene_number": 1, "status": "completed", "duration_seconds": 25.0},
            {"scene_number": 2, "status": "completed", "duration_seconds": 25.0},
            {"scene_number": 3, "status": "failed", "duration_seconds": 0.0},
        ],
    }


@pytest.fixture
def valid_mp4_file(tmp_path: Path) -> Path:
    mp4 = tmp_path / "test.mp4"
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=1",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
             "-pix_fmt", "yuv420p", str(mp4)],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0 and mp4.exists() and mp4.stat().st_size > 0:
            return mp4
    except Exception:
        pass
    mp4.write_bytes(b"\x00" * 100)
    return mp4


class TestVisualPlan:
    def test_valid(self, valid_visual_plan: dict[str, Any]) -> None:
        r = validate_visual_plan(valid_visual_plan)
        assert r["valid"] is True

    def test_missing_topic(self, tmp_path: Path) -> None:
        assert validate_visual_plan({"title": "T", "scenes": []})["valid"] is False

    def test_missing_scenes(self, tmp_path: Path) -> None:
        assert validate_visual_plan({"topic": "T", "title": "T"})["valid"] is False

    def test_empty_scenes(self, tmp_path: Path) -> None:
        assert validate_visual_plan({"topic": "T", "title": "T", "scenes": []})["valid"] is False


class TestRenderProgress:
    def test_valid(self, valid_render_progress: dict[str, Any]) -> None:
        r = validate_render_progress(valid_render_progress)
        assert r["valid"] is True

    def test_failed(self, failed_render_progress: dict[str, Any]) -> None:
        r = validate_render_progress(failed_render_progress)
        assert r["valid"] is False


class TestMP4Discovery:
    def test_prefers_final(self, tmp_path: Path) -> None:
        (tmp_path / "video.mp4").write_bytes(b"\x00" * 100)
        (tmp_path / "final_video.mp4").write_bytes(b"\x00" * 100)
        r = discover_mp4(tmp_path)
        assert r is not None and r.name == "final_video.mp4"

    def test_none_when_missing(self, tmp_path: Path) -> None:
        assert discover_mp4(tmp_path) is None

    def test_in_subdir(self, tmp_path: Path) -> None:
        (tmp_path / "render").mkdir()
        (tmp_path / "render" / "out.mp4").write_bytes(b"\x00" * 100)
        assert discover_mp4(tmp_path) is not None


class TestMP4Validation:
    def test_nonexistent(self, tmp_path: Path) -> None:
        r = validate_mp4_with_ffprobe(tmp_path / "nope.mp4")
        assert r["valid"] is False

    def test_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.mp4"
        p.write_bytes(b"")
        r = validate_mp4_with_ffprobe(p)
        assert r["valid"] is False

    def test_invalid(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.mp4"
        p.write_bytes(b"not mp4")
        r = validate_mp4_with_ffprobe(p)
        assert r["valid"] is False


class TestFullVerification:
    def test_valid_job_passes(
        self,
        tmp_job_dir: Path,
        valid_visual_plan: dict[str, Any],
        valid_render_progress: dict[str, Any],
        valid_mp4_file: Path,
    ) -> None:
        """A complete, contract-satisfying job directory passes verification."""
        (tmp_job_dir / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        (tmp_job_dir / "render_progress.json").write_text(json.dumps(valid_render_progress))
        import shutil
        shutil.copy2(valid_mp4_file, tmp_job_dir / "final_video.mp4")
        r = verify_job_directory(tmp_job_dir)
        assert r["passed"] is True
        assert r["overall_pass"] is True
        assert r["visual_plan"]["valid"] is True
        assert r["render_progress"]["valid"] is True
        assert r["mp4"]["valid"] is True
        assert r["render_status"] == RENDER_STATUS_COMPLETED
        assert r["errors"] == []

    def test_missing_visual_plan(self, tmp_job_dir: Path, valid_render_progress: dict[str, Any], valid_mp4_file: Path) -> None:
        (tmp_job_dir / "render_progress.json").write_text(json.dumps(valid_render_progress))
        import shutil; shutil.copy2(valid_mp4_file, tmp_job_dir / "final_video.mp4")
        assert verify_job_directory(tmp_job_dir)["overall_pass"] is False

    def test_missing_render_progress(self, tmp_job_dir: Path, valid_visual_plan: dict[str, Any], valid_mp4_file: Path) -> None:
        (tmp_job_dir / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        import shutil; shutil.copy2(valid_mp4_file, tmp_job_dir / "final_video.mp4")
        assert verify_job_directory(tmp_job_dir)["overall_pass"] is False

    def test_failed_status(self, tmp_job_dir: Path, valid_visual_plan: dict[str, Any], failed_render_progress: dict[str, Any], valid_mp4_file: Path) -> None:
        (tmp_job_dir / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        (tmp_job_dir / "render_progress.json").write_text(json.dumps(failed_render_progress))
        import shutil; shutil.copy2(valid_mp4_file, tmp_job_dir / "final_video.mp4")
        assert verify_job_directory(tmp_job_dir)["overall_pass"] is False

    def test_missing_mp4(self, tmp_job_dir: Path, valid_visual_plan: dict[str, Any], valid_render_progress: dict[str, Any]) -> None:
        (tmp_job_dir / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        (tmp_job_dir / "render_progress.json").write_text(json.dumps(valid_render_progress))
        assert verify_job_directory(tmp_job_dir)["overall_pass"] is False

    def test_invalid_mp4(self, tmp_job_dir: Path, valid_visual_plan: dict[str, Any], valid_render_progress: dict[str, Any]) -> None:
        (tmp_job_dir / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        (tmp_job_dir / "render_progress.json").write_text(json.dumps(valid_render_progress))
        (tmp_job_dir / "final_video.mp4").write_bytes(b"bad")
        assert verify_job_directory(tmp_job_dir)["overall_pass"] is False

    def test_optional_absent_ok(self, tmp_job_dir: Path, valid_visual_plan: dict[str, Any], valid_render_progress: dict[str, Any], valid_mp4_file: Path) -> None:
        (tmp_job_dir / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        (tmp_job_dir / "render_progress.json").write_text(json.dumps(valid_render_progress))
        import shutil; shutil.copy2(valid_mp4_file, tmp_job_dir / "final_video.mp4")
        r = verify_job_directory(tmp_job_dir)
        assert r["overall_pass"] is True
        assert r["optional_artifacts"]["research.json"] == "missing"

    def test_job_json_does_not_substitute_for_render_progress(
        self, tmp_job_dir: Path, valid_visual_plan: dict[str, Any], valid_mp4_file: Path
    ) -> None:
        """render_progress.json is a required artifact: job.json cannot replace it."""
        (tmp_job_dir / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        (tmp_job_dir / "job.json").write_text(json.dumps({
            "job_id": "t", "current_stage": "render",
            "render_outputs": [{"job_id": "s1", "status": RENDER_STATUS_COMPLETED,
                "output_reference": "s1.mp4", "scene_number": 1, "duration_seconds": 10}],
            "final_media": {"status": RENDER_STATUS_COMPLETED, "output_reference": "final_video.mp4"},
        }))
        import shutil; shutil.copy2(valid_mp4_file, tmp_job_dir / "final_video.mp4")
        r = verify_job_directory(tmp_job_dir)
        assert r["overall_pass"] is False
        assert r["render_progress"]["valid"] is False
        assert r["visual_plan"]["valid"] is True
        assert r["mp4"]["valid"] is True
        assert any("render_progress.json" in e for e in r["errors"])


class TestCLI:
    def test_missing_dir(self, tmp_path: Path) -> None:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "scripts" / "run_day8_verification.py"),
             "--job-dir", str(tmp_path / "nope")],
            capture_output=True, text=True,
        )
        assert r.returncode != 0

    def test_cli_output(self, tmp_path: Path, valid_visual_plan: dict[str, Any], valid_render_progress: dict[str, Any], valid_mp4_file: Path) -> None:
        d = tmp_path / "job"; d.mkdir()
        (d / "visual_plan.json").write_text(json.dumps(valid_visual_plan))
        (d / "render_progress.json").write_text(json.dumps(valid_render_progress))
        import shutil; shutil.copy2(valid_mp4_file, d / "final_video.mp4")
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "scripts" / "run_day8_verification.py"),
             "--job-dir", str(d)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        out = d / "day8_verification.json"
        assert out.exists()

    def test_missing_fields(self, tmp_path: Path) -> None:
        assert validate_render_progress({"job_id": "test"})["valid"] is False

    def test_nonempty_failures(self, tmp_path: Path) -> None:
        r = validate_render_progress({
            "job_id": "t", "status": RENDER_STATUS_COMPLETED,
            "tasks_total": 5, "tasks_done": 5,
            "current_stage": "r", "failures": ["s1"],
        })
        assert r["valid"] is False

    def test_pending_not_accepted(self, tmp_path: Path) -> None:
        r = validate_render_progress({
            "job_id": "t", "status": "pending",
            "tasks_total": 5, "tasks_done": 0,
            "current_stage": "r", "failures": [],
        })
        assert r["valid"] is False

    def test_running_not_accepted(self, tmp_path: Path) -> None:
        r = validate_render_progress({
            "job_id": "t", "status": "running",
            "tasks_total": 5, "tasks_done": 2,
            "current_stage": "r", "failures": [],
        })
        assert r["valid"] is False
