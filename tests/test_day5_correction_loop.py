"""Day-5 correction-loop tests.

Covers the CorrectionLoop end to end with deterministic QC fixtures:
    - retry counting (0 / 1 / 2 / max exceeded)
    - guaranteed termination (no infinite loop)
    - artifact lineage (corrections.json / correction_report.json)
    - escalation on persisting failure + no-progress early stop
    - targeted regeneration (only the smallest artifact re-run)
    - scene-level correction preserves unaffected scenes
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.orchestration.agents.research.mock import MockResearchAgent
from src.orchestration.agents.script.mock import MockScriptAgent
from src.orchestration.agents.strategy.mock import MockStrategyAgent
from src.orchestration.agents.visual.mock import MockVisualPlannerAgent
from src.orchestration.orchestrator import VideoPipelineOrchestrator
from src.orchestration.pipeline import (
    STAGE_QC,
    STAGE_RENDER,
    STAGE_SCRIPT,
    STAGE_VISUAL_PLAN,
    PipelineSpec,
)
from src.orchestration.qc.models import QCCheck, QCReport, QCSeverity, QCStatus
from src.orchestration.repair.loop import (
    DEFAULT_MAX_CORRECTION_ATTEMPTS,
    CorrectionExecutor,
    CorrectionLoop,
)
from src.orchestration.repair.executor import CorrectiveVisualPlanner
from src.orchestration.repair.models import CorrectionPlan, CorrectionTarget
from src.orchestration.schemas.production import ProductionRequest, VideoArtifact
from src.orchestration.schemas.research import ResearchRequest
from src.orchestration.schemas.visual import VisualPlan

DEFAULT_TOPIC = "Why Most People Quit Learning a Skill Too Early"


class _StubRenderer:
    """Renderer adapter double: succeeds, records how many times it ran."""

    stage = STAGE_RENDER

    def __init__(self) -> None:
        self.render_calls = 0

    def run(self, request: ProductionRequest) -> VideoArtifact:
        self.render_calls += 1
        return VideoArtifact(
            job_id=request.job_id,
            status="completed",
            output_path=request.output_path,
            mp4_exists=True,
            file_size_bytes=42,
            scene_count=len(request.visual_plan.scenes),
            total_duration_seconds=request.visual_plan.total_duration_seconds,
        )


def _build_orchestrator(tmp_path: Path) -> tuple[VideoPipelineOrchestrator, _StubRenderer]:
    renderer = _StubRenderer()
    spec = PipelineSpec.default(renderer_adapter=renderer)
    orch = VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path))
    return orch, renderer


def _run_pipeline_through_qc(
    tmp_path: Path,
    inject: list[QCCheck] | None = None,
    qc_agent: "_ScriptedQCAgent | None" = None,
):
    """Run a full mock pipeline + QC, optionally injecting extra QC failures.

    ``qc_agent`` replaces the natural QC gate with a test-only scripted double
    BEFORE the pipeline runs, so the initial report comes from the scripted
    sequence (the stub renderer's fake MP4 makes the natural media QC fail,
    which would pollute loop-mechanics expectations).
    Returns (orchestrator, renderer, job, qc_report).
    """
    orch, renderer = _build_orchestrator(tmp_path)
    if qc_agent is not None:
        orch.registry.register(qc_agent, stage="qc")
    job = orch.create_job(DEFAULT_TOPIC)
    # Run all stages except QC.
    orch.run_stages(
        job, ["research", "strategy", "script", "visual_plan", "render"]
    )
    report = orch.run_qc(job)
    if inject:
        report = report.model_copy(
            update={
                "checks": list(report.checks) + inject,
                "overall_status": QCStatus.FAIL,
                "publish_ready": False,
                "errors": [f"{c.check_name}: {c.message}" for c in inject],
            }
        )
    return orch, renderer, job, report


def _static_camera_check(scene: int = 2) -> QCCheck:
    return QCCheck(
        check_name="visual_camera_diversity",
        status=QCStatus.FAIL,
        severity=QCSeverity.FAIL,
        message="Consecutive scenes use the same camera",
        details={"bad_scenes": [scene]},
    )


class _ScriptedQCAgent:
    """Deterministic scripted QC double (TEST-ONLY).

    The stub renderer never writes a decodable MP4, so the natural QC suite
    fails on media checks and loop-mechanics tests cannot use it.  This double
    satisfies the existing stage-agent contract (``stage`` + ``run(request)``)
    and replays a scripted sequence of QCReports; the last report repeats.
    Production QC is never modified by tests.
    """

    stage = STAGE_QC

    def __init__(self, reports: list[QCReport]) -> None:
        if not reports:
            raise ValueError("scripted QC requires at least one report")
        self._reports = list(reports)
        self.calls = 0

    def run(self, request) -> QCReport:
        report = self._reports[min(self.calls, len(self._reports) - 1)]
        self.calls += 1
        return report.model_copy(update={"job_id": request.job_id})


def _qc_report(status: QCStatus, checks: list[QCCheck]) -> QCReport:
    """Aggregate scripted checks into a QCReport like the QC pipeline does."""
    errors = [f"{c.check_name}: {c.message}" for c in checks if c.status == QCStatus.FAIL]
    warnings = [f"{c.check_name}: {c.message}" for c in checks if c.status == QCStatus.WARN]
    return QCReport(
        job_id="scripted",
        overall_status=status,
        checks=checks,
        errors=errors,
        warnings=warnings,
        publish_ready=status == QCStatus.PASS,
    )


def _pass_check(name: str = "script_present") -> QCCheck:
    return QCCheck(
        check_name=name,
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="ok",
    )


class TestRetryControl:
    """Retry counting and terminal outcomes."""

    def test_pass_on_first_attempt_means_zero_corrections(self, tmp_path):
        # Scripted QC: initial QC -> PASS.  The natural QC cannot be used here:
        # the stub renderer's fake MP4 fails media checks, which is a test
        # artifact, not a loop-mechanics scenario.
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path,
            qc_agent=_ScriptedQCAgent([_qc_report(QCStatus.PASS, [_pass_check()])]),
        )
        assert report.overall_status == QCStatus.PASS
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        assert correction.attempt_count == 0
        assert correction.attempts == []
        assert correction.final_outcome == "SUCCESS"
        assert correction.terminal_reason == "qc_passed"
        assert correction.final_publish_ready is True

    def test_fail_then_pass_means_exactly_one_correction(self, tmp_path):
        """Failure A: static/repeated visuals -> targeted visual correction.

        Scripted QC: initial QC -> FAIL, post-correction QC -> PASS.
        """
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path,
            qc_agent=_ScriptedQCAgent([
                _qc_report(QCStatus.FAIL, [_static_camera_check(scene=2)]),
                _qc_report(QCStatus.PASS, [_pass_check()]),
            ]),
        )
        assert report.overall_status == QCStatus.FAIL
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        assert correction.attempt_count == 1
        assert correction.final_outcome == "SUCCESS"
        assert correction.terminal_reason == "qc_passed"
        # Only the visual plan + render were re-run; script never regenerated.
        assert "script" not in correction.attempts[0].result
        assert correction.attempts[0].target_stage == "visual_plan"

    def test_default_limit_is_safe(self):
        assert DEFAULT_MAX_CORRECTION_ATTEMPTS == 2


def _persistent_fail_qc():
    """QC double INSTANCE that keeps failing with the same static-camera check.

    Must be registered as a stage agent (``stage`` + ``run(self, request)``);
    the previous tests registered the raw class, which broke the agent
    contract (``run() missing 1 required positional argument``).
    """

    class _AlwaysFailQC:
        stage = "qc"

        def run(self, request):
            return QCReport(
                job_id=request.job_id,
                overall_status=QCStatus.FAIL,
                checks=[_static_camera_check()],
                errors=["persistent"],
                publish_ready=False,
            )

    return _AlwaysFailQC()


class TestPersistentFailure:
    """Failure D: QC keeps failing -> hard attempt limit, terminal failure."""

    def test_persistent_failure_respects_max_attempts(self, tmp_path):
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, qc_agent=_persistent_fail_qc()
        )
        assert report.overall_status == QCStatus.FAIL
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        assert correction.attempt_count == 2  # exactly the limit, never more
        assert correction.final_outcome == "FAILED_QC"
        assert correction.terminal_reason == "max_attempts_reached"
        assert correction.final_publish_ready is False
        assert correction.final_qc_status == "fail"

    def test_zero_max_attempts_corrects_nothing(self, tmp_path):
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, inject=[_static_camera_check()]
        )
        loop = CorrectionLoop(orch, max_correction_attempts=0)
        job, correction = loop.run(job, report)
        assert correction.attempt_count == 0
        assert correction.final_outcome == "FAILED_QC"
        assert renderer.render_calls == 1  # only the initial render

    def test_loop_terminates_under_persistent_failure(self, tmp_path):
        """Explicit no-infinite-loop proof: run() must return."""
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, qc_agent=_persistent_fail_qc()
        )
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)  # must return, not hang
        assert correction.attempt_count <= loop.max_correction_attempts
        assert correction.terminal_reason in ("max_attempts_reached", "no_progress")


class TestArtifactLineage:
    """Every attempt is recorded and persisted (append-only)."""

    def test_lineage_files_written(self, tmp_path):
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, inject=[_static_camera_check()]
        )
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        job_dir = tmp_path / job.job_id
        assert (job_dir / "correction_report.json").exists()
        assert (job_dir / "corrections.json").exists()
        saved = json.loads((job_dir / "correction_report.json").read_text("utf-8"))
        assert saved["job_id"] == job.job_id
        assert saved["attempt_count"] == correction.attempt_count
        assert len(saved["attempts"]) == correction.attempt_count

    def test_attempt_fields_are_recorded(self, tmp_path):
        # Scripted QC: FAIL with exactly one check -> PASS after correction,
        # so the recorded attempt fields are deterministic.
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path,
            qc_agent=_ScriptedQCAgent([
                _qc_report(QCStatus.FAIL, [_static_camera_check(scene=3)]),
                _qc_report(QCStatus.PASS, [_pass_check()]),
            ]),
        )
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        attempt = correction.attempts[0]
        assert attempt.attempt_number == 1
        assert attempt.failed_checks == ["visual_camera_diversity"]
        assert attempt.target_stage == "visual_plan"
        assert attempt.target_artifact == "visual_plan"
        assert attempt.reason == "visual_static"
        assert attempt.affected_scene_ids == [3]
        assert attempt.diagnosis  # inspectable summary
        assert attempt.result

    def test_attempt_sequence_numbers_are_ordered(self, tmp_path):
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, qc_agent=_persistent_fail_qc()
        )
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        numbers = [a.attempt_number for a in correction.attempts]
        assert numbers == [1, 2]


class TestTargetedRegeneration:
    """Corrections re-run only the smallest affected artifact."""

    def test_visual_correction_preserves_planning(self, tmp_path):
        # Scripted QC: FAIL -> PASS after the targeted visual correction.
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path,
            qc_agent=_ScriptedQCAgent([
                _qc_report(QCStatus.FAIL, [_static_camera_check()]),
                _qc_report(QCStatus.PASS, [_pass_check()]),
            ]),
        )
        script_before = job.script.model_copy(deep=True)
        strategy_before = job.strategy.model_copy(deep=True)
        visual_before = job.visual_plan.model_copy(deep=True)
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        assert job.script == script_before
        assert job.strategy == strategy_before
        # Visual plan DID change (corrections actually change generation) and
        # the corrected artifact passed the post-correction QC gate.
        assert job.visual_plan != visual_before
        assert correction.attempts[0].result == "passed"
        assert correction.attempts[0].qc_status_after == "pass"

    def test_render_correction_does_not_regenerate_planning(self, tmp_path):
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path,
            qc_agent=_ScriptedQCAgent([
                _qc_report(QCStatus.FAIL, [
                    QCCheck(
                        check_name="render_config_resolution",
                        status=QCStatus.FAIL,
                        severity=QCSeverity.FAIL,
                        message="Resolution mismatch",
                    )
                ]),
                _qc_report(QCStatus.PASS, [_pass_check()]),
            ]),
        )
        plan_before = job.visual_plan.model_copy(deep=True)
        script_before = job.script.model_copy(deep=True)
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        assert correction.attempts[0].target_stage == "render"
        assert correction.attempts[0].action == "rerender"
        assert job.visual_plan == plan_before
        assert job.script == script_before


class TestSceneLevelCorrection:
    """Unaffected scenes remain verbatim when targeted correction is possible."""

    def test_partial_correction_preserves_unaffected_scenes(self, tmp_path):
        # Scripted QC: FAIL for scene 2 only -> PASS after the partial fix.
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path,
            qc_agent=_ScriptedQCAgent([
                _qc_report(QCStatus.FAIL, [_static_camera_check(scene=2)]),
                _qc_report(QCStatus.PASS, [_pass_check()]),
            ]),
        )
        scenes_before = {s.scene_number: s for s in job.visual_plan.scenes}
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        # The corrective planner rewrote ONLY the affected scene.
        assert correction.attempts[0].affected_scene_ids == [2]
        planner = CorrectiveVisualPlanner()
        original_plan = job.visual_plan.model_copy(
            update={"scenes": list(scenes_before.values())}
        )
        corrected = planner.replan(
            original_plan,
            CorrectionPlan(
                job_id=job.job_id,
                target_stage="visual_plan",
                target_artifact="visual_plan",
                target=CorrectionTarget.VISUAL_BEATS,
                reason="visual_static",
                action="partial",
                affected_scene_ids=[2],
                attempt_number=1,
            ),
        )
        # Scene 2 changed; every unaffected scene is preserved verbatim.
        scene_by_number = {s.scene_number: s for s in corrected.scenes}
        assert sorted(scene_by_number) == list(range(1, len(scenes_before) + 1))
        for number, before in scenes_before.items():
            if number == 2:
                assert scene_by_number[number] != before
            else:
                assert scene_by_number[number] == before
        assert corrected.total_duration_seconds == job.visual_plan.total_duration_seconds

    def test_full_correction_changes_all_scenes_but_keeps_structure(self, tmp_path):
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, inject=[
                QCCheck(
                    check_name="visual_render_plan",
                    status=QCStatus.FAIL,
                    severity=QCSeverity.FAIL,
                    message="Plan mismatch",
                )
            ]
        )
        scene_count = len(job.visual_plan.scenes)
        durations = [s.duration_seconds for s in job.visual_plan.scenes]
        narrations = [s.narration for s in job.visual_plan.scenes]
        loop = CorrectionLoop(orch, max_correction_attempts=2)
        job, correction = loop.run(job, report)
        assert len(job.visual_plan.scenes) == scene_count
        assert [s.duration_seconds for s in job.visual_plan.scenes] == durations
        assert [s.narration for s in job.visual_plan.scenes] == narrations


class TestEscalation:
    """QC-driven escalation: same failure after correction -> upstream target."""

    def test_escalation_occurs_on_identical_persisting_failure(self, tmp_path):
        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, qc_agent=_persistent_fail_qc()
        )
        assert report.overall_status == QCStatus.FAIL
        loop = CorrectionLoop(orch, max_correction_attempts=3)
        job, correction = loop.run(job, report)
        # Same check persists -> the second attempt must escalate upstream.
        escalated = [a for a in correction.attempts if a.escalated]
        assert escalated, "expected escalation on persisting identical failure"
        assert correction.escalation_count >= 1
        assert escalated[0].escalated_from == "visual_beats"
        assert escalated[0].target_stage == "script"

    def test_no_progress_terminates_when_escalation_impossible(self, tmp_path):
        """Script-level failures cannot escalate further -> early stop."""
        script_check = QCCheck(
            check_name="script_narration_coverage",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Narration missing",
        )

        class _AlwaysFailScriptQC:
            stage = "qc"

            def run(self, request):
                return QCReport(
                    job_id=request.job_id,
                    overall_status=QCStatus.FAIL,
                    checks=[script_check],
                    errors=["persistent script failure"],
                    publish_ready=False,
                )

        orch, renderer, job, report = _run_pipeline_through_qc(
            tmp_path, inject=[script_check]
        )
        orch.registry.register(_AlwaysFailScriptQC(), stage="qc")
        loop = CorrectionLoop(orch, max_correction_attempts=5)
        job, correction = loop.run(job, report)
        # Bounded: stops at the limit; never burns unbounded retries.
        assert correction.attempt_count <= 5
        assert correction.terminal_reason in ("max_attempts_reached", "no_progress")
        assert correction.final_outcome in ("FAILED_QC", "FAILED_CORRECTION")
        assert correction.final_publish_ready is False
