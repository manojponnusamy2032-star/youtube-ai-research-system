"""Day-3 QC Pipeline tests."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from src.orchestration.qc.qc_pipeline import _compute_overall_status, run_qc
from src.orchestration.qc.models import (
    QCStatus,
    QCCheck,
    QCReport,
    QCRequest,
)
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan
from src.orchestration.schemas.production import VideoArtifact


def _valid_script(duration_per_section: int = 1, num_sections: int = 2) -> ScriptPackage:
    sections = [
        ScriptSection(
            heading=f"Section {i}",
            narration=f"Narration text for section {i} here.",
            duration_seconds=duration_per_section,
        )
        for i in range(1, num_sections + 1)
    ]
    total = duration_per_section * num_sections
    return ScriptPackage(
        topic="Test Topic",
        title="Test Title",
        hook="Hook.",
        sections=sections,
        call_to_action="CTA.",
        total_duration_seconds=total,
    )


def _valid_plan(duration_per_scene: int = 1, num_scenes: int = 2) -> VisualPlan:
    scenes = [
        VisualScenePlan(
            scene_number=i,
            duration_seconds=duration_per_scene,
            narration=f"Narration {i}.",
            visual_prompt=f"Prompt {i}.",
            camera_instructions="static" if i % 2 == 0 else "zoom",
            character_action="talk" if i % 2 == 0 else "point",
            motions=[{"type": "enter"}],
            visual_description={"environment": {"type": "desk"}},
        )
        for i in range(1, num_scenes + 1)
    ]
    total = duration_per_scene * num_scenes
    return VisualPlan(
        topic="Test Topic",
        title="Test Title",
        scenes=scenes,
        render_job_plan={"total_jobs": num_scenes, "jobs": [], "total_duration_seconds": total},
        total_duration_seconds=total,
    )
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


def _artifact_with_mp4(tmp_path: Path, scene_count: int = 2, duration: int = 2) -> VideoArtifact:
    """Create a VideoArtifact backed by a real MP4.

    The MP4 is created with matching duration to keep tests fast.
    """
    mp4 = _make_valid_mp4(tmp_path / "video.mp4", duration=duration)
    return VideoArtifact(
        job_id="job_001",
        status="completed",
        output_path=str(mp4),
        mp4_exists=True,
        file_size_bytes=mp4.stat().st_size,
        scene_count=scene_count,
        total_duration_seconds=duration,
    )


class TestOverallStatusComputation:
    def test_all_pass(self):
        checks = [QCCheck(check_name="a", status=QCStatus.PASS, message="")]
        assert _compute_overall_status(checks) == QCStatus.PASS

    def test_any_fail(self):
        checks = [
            QCCheck(check_name="a", status=QCStatus.PASS, message=""),
            QCCheck(check_name="b", status=QCStatus.FAIL, message=""),
        ]
        assert _compute_overall_status(checks) == QCStatus.FAIL

    def test_warn_no_fail(self):
        checks = [
            QCCheck(check_name="a", status=QCStatus.PASS, message=""),
            QCCheck(check_name="b", status=QCStatus.WARN, message=""),
        ]
        assert _compute_overall_status(checks) == QCStatus.WARN


class TestQCPipeline:
    def test_valid_job_with_mp4(self, tmp_path: Path):
        """Full QC on a valid job with a real MP4 should PASS."""
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        artifact = _artifact_with_mp4(tmp_path)
        request = QCRequest(
            job_id="job_001",
            script=_valid_script(),
            visual_plan=_valid_plan(),
            artifact=artifact,
            render_config={"width": 320, "height": 240, "fps": 24},
        )
        report = run_qc(request)
        assert isinstance(report, QCReport)
        assert report.job_id == "job_001"
        assert report.overall_status == QCStatus.PASS
        assert report.publish_ready is True
        assert len(report.checks) > 0
        assert report.metrics["failed"] == 0

    def test_failed_job_missing_script(self):
        request = QCRequest(
            job_id="job_002",
            script=None,
            visual_plan=_valid_plan(),
            artifact=None,
        )
        report = run_qc(request)
        assert report.overall_status == QCStatus.FAIL
        assert report.publish_ready is False

    def test_failed_job_missing_artifact(self):
        request = QCRequest(
            job_id="job_003",
            script=_valid_script(),
            visual_plan=_valid_plan(),
            artifact=None,
        )
        report = run_qc(request)
        assert report.overall_status == QCStatus.FAIL
        assert report.publish_ready is False

    def test_warn_job_repetitive_visuals(self, tmp_path: Path):
        """WARN status when visuals are repetitive (but media is valid)."""
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        artifact = _artifact_with_mp4(tmp_path)
        plan = _valid_plan()
        for s in plan.scenes:
            s.visual_prompt = "identical prompt"
        request = QCRequest(
            job_id="job_004",
            script=_valid_script(),
            visual_plan=plan,
            artifact=artifact,
        )
        report = run_qc(request)
        assert report.overall_status == QCStatus.WARN
        assert report.publish_ready is False

    def test_metrics_populated(self, tmp_path: Path):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        artifact = _artifact_with_mp4(tmp_path)
        request = QCRequest(
            job_id="job_005",
            script=_valid_script(),
            visual_plan=_valid_plan(),
            artifact=artifact,
        )
        report = run_qc(request)
        assert "total_checks" in report.metrics
        assert "passed" in report.metrics
        assert "warned" in report.metrics
        assert "failed" in report.metrics
        assert report.metrics["total_checks"] == len(report.checks)

    def test_errors_warnings_populated(self):
        request = QCRequest(
            job_id="job_006",
            script=None,
            visual_plan=None,
            artifact=None,
        )
        report = run_qc(request)
        assert len(report.errors) > 0
        assert report.publish_ready is False

    def test_fail_overrides_warn(self):
        """A FAIL check should always make overall_status FAIL regardless of WARNs."""
        request = QCRequest(
            job_id="job_007",
            script=None,
            visual_plan=None,
            artifact=None,
        )
        report = run_qc(request)
        assert report.overall_status == QCStatus.FAIL
        assert report.publish_ready is False
