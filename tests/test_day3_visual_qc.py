"""Day-3 Visual QC tests."""
from __future__ import annotations

import pytest
from src.orchestration.qc.visual_qc import run_visual_qc
from src.orchestration.qc.repetition_qc import run_repetition_qc
from src.orchestration.qc.models import QCStatus, QCSeverity
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan


def _valid_plan() -> VisualPlan:
    scenes = [
        VisualScenePlan(
            scene_number=i,
            duration_seconds=10,
            narration=f"Narration for scene {i}.",
            visual_prompt=f"Visual prompt for scene {i}.",
            camera_instructions="static" if i % 2 == 0 else "zoom",
            character_action="talk" if i % 2 == 0 else "point",
            motions=[{"type": "enter", "target": "character"}],
            visual_description={"environment": {"type": "desk"}},
        )
        for i in range(1, 4)
    ]
    return VisualPlan(
        topic="Test Topic",
        title="Test Title",
        scenes=scenes,
        render_job_plan={
            "total_jobs": 3,
            "jobs": [{"job_id": f"scene-{i}"} for i in range(1, 4)],
            "total_duration_seconds": 30,
        },
        total_duration_seconds=30,
    )


class TestVisualQCValid:
    def test_valid_plan_passes(self):
        plan = _valid_plan()
        checks = run_visual_qc(plan)
        for check in checks:
            assert check.status == QCStatus.PASS, f"{check.check_name}: {check.message}"

    def test_none_plan(self):
        checks = run_visual_qc(None)
        assert len(checks) == 1
        assert checks[0].status == QCStatus.FAIL


class TestVisualQCSceneCount:
    def test_zero_scenes(self):
        plan = _valid_plan()
        plan.scenes = []
        checks = run_visual_qc(plan)
        count = next(c for c in checks if c.check_name == "visual_scene_count")
        assert count.status == QCStatus.FAIL


class TestVisualQCSceneNumbering:
    def test_invalid_numbering(self):
        plan = _valid_plan()
        plan.scenes[0].scene_number = 5
        checks = run_visual_qc(plan)
        numbering = next(c for c in checks if c.check_name == "visual_scene_numbering")
        assert numbering.status == QCStatus.FAIL


class TestVisualQCDuration:
    def test_zero_duration(self):
        plan = _valid_plan()
        plan.scenes[0].duration_seconds = 0
        checks = run_visual_qc(plan)
        duration = next(c for c in checks if c.check_name == "visual_scene_durations")
        assert duration.status == QCStatus.FAIL

    def test_duration_mismatch(self):
        plan = _valid_plan()
        plan.total_duration_seconds = 100  # scenes sum to 30
        checks = run_visual_qc(plan)
        consistency = next(c for c in checks if c.check_name == "visual_duration_consistency")
        assert consistency.status == QCStatus.FAIL


class TestVisualQCNarration:
    def test_missing_narration(self):
        plan = _valid_plan()
        plan.scenes[0].narration = ""
        checks = run_visual_qc(plan)
        coverage = next(c for c in checks if c.check_name == "visual_narration_coverage")
        assert coverage.status == QCStatus.FAIL


class TestVisualQCVisualCoverage:
    def test_missing_visual_data(self):
        plan = _valid_plan()
        plan.scenes[0].visual_prompt = ""
        plan.scenes[0].visual_description = {}
        plan.scenes[0].animation_instructions = ""
        checks = run_visual_qc(plan)
        coverage = next(c for c in checks if c.check_name == "visual_coverage")
        assert coverage.status == QCStatus.WARN


class TestVisualQCRenderPlan:
    def test_missing_render_jobs(self):
        plan = _valid_plan()
        plan.render_job_plan = {"total_jobs": 0, "jobs": []}
        checks = run_visual_qc(plan)
        render = next(c for c in checks if c.check_name == "visual_render_plan")
        assert render.status == QCStatus.FAIL

    def test_scene_count_mismatch(self):
        plan = _valid_plan()
        plan.render_job_plan["total_jobs"] = 10
        checks = run_visual_qc(plan)
        render = next(c for c in checks if c.check_name == "visual_render_plan")
        assert render.status == QCStatus.FAIL


class TestRepetitionQC:
    def test_repeated_visual_prompts(self):
        plan = _valid_plan()
        for s in plan.scenes:
            s.visual_prompt = "identical prompt"
        checks = run_repetition_qc(plan)
        diversity = next(c for c in checks if c.check_name == "visual_prompt_diversity")
        assert diversity.status == QCStatus.WARN

    def test_repeated_camera_instructions(self):
        plan = _valid_plan()
        for s in plan.scenes:
            s.camera_instructions = "identical camera"
        checks = run_repetition_qc(plan)
        diversity = next(c for c in checks if c.check_name == "visual_camera_diversity")
        assert diversity.status == QCStatus.WARN

    def test_missing_activity_information(self):
        plan = _valid_plan()
        for s in plan.scenes:
            s.motions = []
        checks = run_repetition_qc(plan)
        activity = next(c for c in checks if c.check_name == "visual_motion_activity")
        assert activity.status == QCStatus.WARN

    def test_diverse_plan_passes(self):
        plan = _valid_plan()
        checks = run_repetition_qc(plan)
        for check in checks:
            assert check.status == QCStatus.PASS, f"{check.check_name}: {check.message}"
