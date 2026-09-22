"""Day-3 Cross-stage QC tests."""
from __future__ import annotations

import pytest
from src.orchestration.qc.cross_stage_qc import run_cross_stage_qc
from src.orchestration.qc.models import QCStatus, QCSeverity
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan
from src.orchestration.schemas.production import VideoArtifact


def _valid_script() -> ScriptPackage:
    sections = [
        ScriptSection(
            heading=f"Section {i}",
            narration=f"Narration text for section {i}.",
            duration_seconds=10,
        )
        for i in range(1, 4)
    ]
    return ScriptPackage(
        topic="Test Topic",
        title="Test Title",
        hook="Hook.",
        sections=sections,
        call_to_action="CTA.",
        total_duration_seconds=30,
    )


def _valid_plan() -> VisualPlan:
    scenes = [
        VisualScenePlan(
            scene_number=i,
            duration_seconds=10,
            narration=f"Narration {i}.",
            visual_prompt=f"Prompt {i}.",
        )
        for i in range(1, 4)
    ]
    return VisualPlan(
        topic="Test Topic",
        title="Test Title",
        scenes=scenes,
        render_job_plan={"total_jobs": 3, "jobs": [], "total_duration_seconds": 30},
        total_duration_seconds=30,
    )


def _valid_artifact() -> VideoArtifact:
    return VideoArtifact(
        job_id="job_001",
        status="completed",
        output_path="/tmp/video.mp4",
        mp4_exists=True,
        file_size_bytes=1000,
        scene_count=3,
        total_duration_seconds=30,
    )


class TestCrossStageQCValid:
    def test_matching_data(self):
        script = _valid_script()
        plan = _valid_plan()
        artifact = _valid_artifact()
        checks = run_cross_stage_qc(script, plan, artifact)
        for check in checks:
            assert check.status == QCStatus.PASS, f"{check.check_name}: {check.message}"


class TestCrossStageQCSceneCountMismatch:
    def test_scene_count_mismatch(self):
        script = _valid_script()
        plan = _valid_plan()
        plan.scenes = plan.scenes[:1]  # Fewer scenes than sections -> FAIL
        artifact = _valid_artifact()
        checks = run_cross_stage_qc(script, plan, artifact)
        scene_count = next(c for c in checks if c.check_name == "cross_stage_scene_count")
        assert scene_count.status == QCStatus.FAIL

    def test_day4_beat_expansion_passes(self):
        from src.orchestration.schemas.visual import VisualScenePlan
        script = _valid_script()
        plan = _valid_plan()
        extra = VisualScenePlan(
            scene_number=4, duration_seconds=5, narration="Extra.",
            visual_prompt="Extra prompt.",
        )
        plan.scenes = plan.scenes + [extra]
        artifact = _valid_artifact()
        checks = run_cross_stage_qc(script, plan, artifact)
        scene_count = next(c for c in checks if c.check_name == "cross_stage_scene_count")
        assert scene_count.status == QCStatus.PASS


class TestCrossStageQCDurationMismatch:
    def test_duration_mismatch(self):
        script = _valid_script()
        plan = _valid_plan()
        plan.total_duration_seconds = 100
        artifact = _valid_artifact()
        checks = run_cross_stage_qc(script, plan, artifact)
        duration = next(c for c in checks if c.check_name == "cross_stage_duration")
        assert duration.status == QCStatus.FAIL


class TestCrossStageQCMissingOutput:
    def test_missing_output(self):
        script = _valid_script()
        plan = _valid_plan()
        artifact = _valid_artifact()
        artifact.output_path = ""
        artifact.mp4_exists = False
        checks = run_cross_stage_qc(script, plan, artifact)
        output = next(c for c in checks if c.check_name == "cross_stage_render_output")
        assert output.status == QCStatus.FAIL

    def test_none_script(self):
        plan = _valid_plan()
        artifact = _valid_artifact()
        checks = run_cross_stage_qc(None, plan, artifact)
        for check in checks:
            if check.check_name != "cross_stage_render_output":
                assert check.status == QCStatus.FAIL

    def test_none_visual_plan(self):
        script = _valid_script()
        artifact = _valid_artifact()
        checks = run_cross_stage_qc(script, None, artifact)
        for check in checks:
            assert check.status == QCStatus.FAIL, f"{check.check_name}: {check.message}"

    def test_none_artifact(self):
        script = _valid_script()
        plan = _valid_plan()
        checks = run_cross_stage_qc(script, plan, None)
        output = next(c for c in checks if c.check_name == "cross_stage_render_output")
        assert output.status == QCStatus.FAIL
