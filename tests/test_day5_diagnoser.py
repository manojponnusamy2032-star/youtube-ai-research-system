"""Day-5 correction diagnoser tests.

Verifies deterministic QC-failure -> correction-target mappings:
    script failure          -> SCRIPT
    visual failure          -> VISUAL_BEATS
    static/repetition fail  -> VISUAL_BEATS
    cross-stage mismatch    -> VISUAL_BEATS (downstream)
    render/media failure    -> RENDER
Plus: PASS/WARN never trigger corrections, scene-id extraction,
correction-context inspection, and dependency-map invalidation.
"""

from __future__ import annotations

import pytest

from src.orchestration.qc.models import QCCheck, QCReport, QCSeverity, QCStatus
from src.orchestration.repair.dependency_map import (
    CORRECTION_CHAIN,
    artifact_field_for,
    downstream_of,
    invalidation_set,
    is_downstream,
    pipeline_stage_for,
)
from src.orchestration.repair.diagnoser import CorrectionDiagnoser
from src.orchestration.repair.models import (
    CorrectionAction,
    CorrectionReason,
    CorrectionTarget,
)

JOB_ID = "job_001"


def _report(checks: list[QCCheck], overall: QCStatus | None = None) -> QCReport:
    """Build a QCReport; overall status computed like the QC pipeline does."""
    if overall is None:
        has_fail = any(
            c.status == QCStatus.FAIL or c.severity == QCSeverity.FAIL for c in checks
        )
        has_warn = any(
            c.status == QCStatus.WARN or c.severity == QCSeverity.WARN for c in checks
        )
        overall = (
            QCStatus.FAIL if has_fail else (QCStatus.WARN if has_warn else QCStatus.PASS)
        )
    errors = [
        f"{c.check_name}: {c.message}"
        for c in checks
        if c.status == QCStatus.FAIL or c.severity == QCSeverity.FAIL
    ]
    return QCReport(
        job_id=JOB_ID,
        overall_status=overall,
        checks=checks,
        errors=errors,
        publish_ready=overall == QCStatus.PASS,
    )


def _fail(check_name: str, message: str = "", details: dict | None = None) -> QCCheck:
    return QCCheck(
        check_name=check_name,
        status=QCStatus.FAIL,
        severity=QCSeverity.FAIL,
        message=message or f"{check_name} failed",
        details=details or {},
    )


class TestDiagnoserMappings:
    """QC failure -> smallest reasonable correction target."""

    def setup_method(self) -> None:
        self.diagnoser = CorrectionDiagnoser()

    def test_script_failure_targets_script(self):
        plan = self.diagnoser.diagnose(_report([_fail("script_narration_coverage")]))
        assert plan is not None
        assert plan.target == CorrectionTarget.SCRIPT
        assert plan.target_stage == "script"
        assert plan.target_artifact == "script"
        assert plan.reason == CorrectionReason.SCRIPT_QUALITY
        assert plan.action == CorrectionAction.REGENERATE

    def test_visual_failure_targets_visual_beats(self):
        plan = self.diagnoser.diagnose(_report([_fail("visual_scene_numbering")]))
        assert plan is not None
        assert plan.target == CorrectionTarget.VISUAL_BEATS
        assert plan.target_stage == "visual_plan"
        assert plan.target_artifact == "visual_plan"

    def test_static_repetition_failure_targets_visual_beats(self):
        plan = self.diagnoser.diagnose(
            _report([_fail("visual_camera_diversity", "All cameras identical")])
        )
        assert plan is not None
        assert plan.target == CorrectionTarget.VISUAL_BEATS
        assert plan.reason == CorrectionReason.VISUAL_STATIC

    def test_cross_stage_mismatch_targets_downstream_visual_beats(self):
        """Script/visual mismatch is fixed downstream, never by regenerating script."""
        plan = self.diagnoser.diagnose(
            _report([_fail("cross_stage_scene_alignment", "Scenes != sections")])
        )
        assert plan is not None
        assert plan.target == CorrectionTarget.VISUAL_BEATS
        assert plan.reason == CorrectionReason.VISUAL_MISMATCH
        assert plan.target != CorrectionTarget.SCRIPT

    def test_missing_visual_scene_targets_visual_beats(self):
        plan = self.diagnoser.diagnose(_report([_fail("visual_scene_count")]))
        assert plan is not None
        assert plan.target == CorrectionTarget.VISUAL_BEATS

    def test_media_corruption_targets_render(self):
        plan = self.diagnoser.diagnose(
            _report([_fail("media_mux_corrupt", "MP4 not decodable")])
        )
        assert plan is not None
        assert plan.target == CorrectionTarget.RENDER
        assert plan.target_stage == "render"
        assert plan.target_artifact == "artifact"
        assert plan.action == CorrectionAction.RERENDER

    def test_render_config_failure_targets_render(self):
        plan = self.diagnoser.diagnose(
            _report([_fail("render_config_resolution", "Resolution mismatch")])
        )
        assert plan is not None
        assert plan.target == CorrectionTarget.RENDER
        assert plan.reason == CorrectionReason.RENDER_CONFIG

    def test_mixed_failures_pick_earliest_target(self):
        """A script failure plus a render failure must correct the UPSTREAM one."""
        plan = self.diagnoser.diagnose(
            _report([_fail("media_mux_corrupt"), _fail("script_narration_coverage")])
        )
        assert plan is not None
        assert plan.target == CorrectionTarget.SCRIPT

    def test_failed_checks_list_is_complete_and_sorted(self):
        checks = [_fail("visual_camera_diversity"), _fail("visual_scene_durations")]
        plan = self.diagnoser.diagnose(_report(checks))
        assert plan is not None
        assert plan.failed_checks == sorted(
            ["visual_camera_diversity", "visual_scene_durations"]
        )

    def test_unknown_failure_never_regenerates_everything(self):
        """Unrecognized failures fall back to the visual plan, not 'all stages'."""
        plan = self.diagnoser.diagnose(_report([_fail("totally_unknown_check")]))
        assert plan is not None
        assert plan.target == CorrectionTarget.VISUAL_BEATS


class TestDiagnoserPolicy:
    """PASS / WARN never triggers corrections; FAIL always diagnoses."""

    def setup_method(self) -> None:
        self.diagnoser = CorrectionDiagnoser()

    def test_pass_report_never_corrects(self):
        check = QCCheck(
            check_name="script_present",
            status=QCStatus.PASS,
            severity=QCSeverity.INFO,
            message="ok",
        )
        assert self.diagnoser.diagnose(_report([check])) is None

    def test_warn_only_report_never_corrects(self):
        """Policy: warnings do not start an endless regeneration cycle."""
        check = QCCheck(
            check_name="visual_camera_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="Cameras show low diversity",
        )
        assert self.diagnoser.diagnose(_report([check])) is None

    def test_fail_report_always_diagnoses(self):
        plan = self.diagnoser.diagnose(_report([_fail("visual_scene_count")]))
        assert plan is not None


class TestSceneExtraction:
    """Affected scene ids flow from QC details into the correction plan."""

    def setup_method(self) -> None:
        self.diagnoser = CorrectionDiagnoser()

    def test_bad_scenes_extracted(self):
        plan = self.diagnoser.diagnose(
            _report([_fail("visual_scene_durations", details={"bad_scenes": [3, 4]})])
        )
        assert plan is not None
        assert plan.affected_scene_ids == [3, 4]
        assert plan.action == CorrectionAction.PARTIAL_REGENERATE

    def test_no_motion_scenes_extracted(self):
        plan = self.diagnoser.diagnose(
            _report([_fail("visual_motion_activity", details={"no_motion_scenes": [2]})])
        )
        assert plan is not None
        assert plan.affected_scene_ids == [2]

    def test_render_target_has_no_scene_ids(self):
        plan = self.diagnoser.diagnose(
            _report([_fail("media_mux_corrupt", details={"bad_scenes": [3]})])
        )
        assert plan is not None
        assert plan.affected_scene_ids == []


class TestCorrectionContext:
    """The correction context must be explicit and inspectable (requirement 9)."""

    def setup_method(self) -> None:
        self.diagnoser = CorrectionDiagnoser()

    def test_visual_context_carries_failed_checks_and_improvement(self):
        plan = self.diagnoser.diagnose(
            _report([_fail("visual_camera_diversity", "Consecutive scenes share camera")])
        )
        ctx = plan.correction_context
        assert "visual_camera_diversity" in ctx["failed_checks"]
        assert "Consecutive scenes share camera" in ctx["failure_messages"]
        assert ctx["correction_reason"] == CorrectionReason.VISUAL_STATIC.value
        assert "camera" in ctx["required_improvement"].lower()
        assert ctx["instruction"]

    def test_script_context_carries_instruction(self):
        plan = self.diagnoser.diagnose(_report([_fail("script_narration_coverage")]))
        ctx = plan.correction_context
        assert "instruction" in ctx
        assert "script" in ctx["instruction"].lower()


class TestDependencyMap:
    """Changing one stage invalidates ONLY downstream artifacts."""

    def test_visual_change_does_not_invalidate_script(self):
        targets = invalidation_set(CorrectionTarget.VISUAL_BEATS)
        assert CorrectionTarget.RENDER in targets
        assert CorrectionTarget.SCRIPT not in targets
        assert CorrectionTarget.STRATEGY not in targets

    def test_script_change_invalidates_downstream_visual_artifacts(self):
        targets = invalidation_set(CorrectionTarget.SCRIPT)
        assert targets == [
            CorrectionTarget.SCRIPT,
            CorrectionTarget.STORY_BEATS,
            CorrectionTarget.VISUAL_BEATS,
            CorrectionTarget.RENDER,
        ]

    def test_render_change_only_rerenders(self):
        assert invalidation_set(CorrectionTarget.RENDER) == [CorrectionTarget.RENDER]

    def test_downstream_of_is_ordered(self):
        chain = downstream_of(CorrectionTarget.STRATEGY)
        assert chain == [
            CorrectionTarget.STRATEGY,
            CorrectionTarget.SCRIPT,
            CorrectionTarget.STORY_BEATS,
            CorrectionTarget.VISUAL_BEATS,
            CorrectionTarget.RENDER,
        ]

    def test_is_downstream(self):
        assert is_downstream(CorrectionTarget.RENDER, CorrectionTarget.SCRIPT)
        assert not is_downstream(CorrectionTarget.SCRIPT, CorrectionTarget.RENDER)

    def test_stage_and_artifact_mapping(self):
        assert pipeline_stage_for(CorrectionTarget.RENDER) == "render"
        assert pipeline_stage_for(CorrectionTarget.VISUAL_BEATS) == "visual_plan"
        assert artifact_field_for(CorrectionTarget.RENDER) == "artifact"
        assert artifact_field_for(CorrectionTarget.SCRIPT) == "script"

    def test_chain_is_complete_and_ordered(self):
        assert CORRECTION_CHAIN == [
            CorrectionTarget.RESEARCH,
            CorrectionTarget.STRATEGY,
            CorrectionTarget.SCRIPT,
            CorrectionTarget.STORY_BEATS,
            CorrectionTarget.VISUAL_BEATS,
            CorrectionTarget.RENDER,
        ]
