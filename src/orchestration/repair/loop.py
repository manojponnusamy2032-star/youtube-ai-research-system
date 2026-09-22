"""Correction executor + retry-limited correction loop (Day 5).

    CorrectionExecutor.apply(job, plan)
        Regenerates ONLY the targeted artifact (plus mandatory downstream
        invalidations) using the orchestrator's targeted ``run_stages``.

    CorrectionLoop.run(job, initial_report)
        QC failure -> diagnose -> targeted correction -> rerender -> QC,
        bounded by ``max_correction_attempts`` (guaranteed termination).
        Every attempt is recorded and persisted to ``corrections.json``
        and ``correction_report.json`` (append-only lineage).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.orchestration.orchestrator import VideoPipelineOrchestrator
from src.orchestration.pipeline import STAGE_RENDER, STAGE_SCRIPT, STAGE_VISUAL_PLAN
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.repair.dependency_map import CorrectionTarget
from src.orchestration.repair.diagnoser import CorrectionDiagnoser
from src.orchestration.repair.executor import CorrectiveScriptAgent, CorrectiveVisualPlanner
from src.orchestration.repair.models import (
    CorrectionAction,
    CorrectionAttempt,
    CorrectionPlan,
    CorrectionReport,
)
from src.orchestration.state import write_json_artifact

# Default safe retry limit (requirement 7).
DEFAULT_MAX_CORRECTION_ATTEMPTS = 2

# Stage chain order used to expand invalidations into orchestrator stages.
_STAGE_ORDER = ["research", "strategy", "script", "visual_plan", "render"]

# QC-driven retry escalation (Day-5 extension): when the SAME failed checks
# persist after a correction at a target, escalate one step upstream so a
# deeper regeneration is attempted.  Bounded: SCRIPT cannot escalate further,
# so persistent script-level failure terminates via the no-progress rule
# instead of looping forever.
_ESCALATION_UPSTREAM: dict[CorrectionTarget, CorrectionTarget | None] = {
    CorrectionTarget.RENDER: CorrectionTarget.VISUAL_BEATS,
    CorrectionTarget.VISUAL_BEATS: CorrectionTarget.SCRIPT,
    CorrectionTarget.STORY_BEATS: CorrectionTarget.SCRIPT,
    CorrectionTarget.SCRIPT: None,
    CorrectionTarget.STRATEGY: CorrectionTarget.RESEARCH,
    CorrectionTarget.RESEARCH: None,
}


def _escalate_plan(plan: CorrectionPlan, upstream: CorrectionTarget) -> CorrectionPlan:
    """Re-target a plan one step upstream, carrying the correction context."""
    from src.orchestration.repair.dependency_map import (
        artifact_field_for,
        pipeline_stage_for,
    )

    context = dict(plan.correction_context)
    context["escalated_from"] = plan.target.value
    context["escalation_note"] = (
        f"Previous correction at '{plan.target.value}' did not resolve the "
        f"failed checks; regenerating the upstream '{upstream.value}' artifact "
        "and cascading downstream."
    )
    action = (
        CorrectionAction.RERENDER
        if upstream == CorrectionTarget.RENDER
        else CorrectionAction.REGENERATE
    )
    return plan.model_copy(
        update={
            "target": upstream,
            "target_stage": pipeline_stage_for(upstream),
            "target_artifact": artifact_field_for(upstream),
            "action": action,
            "affected_scene_ids": [],
            "correction_context": context,
        }
    )


def _stages_from(stage: str) -> list[str]:
    """All orchestrator stages from ``stage`` onward (inclusive)."""
    index = _STAGE_ORDER.index(stage)
    return _STAGE_ORDER[index:]


class CorrectionExecutor:
    """Applies a CorrectionPlan to a job using the smallest possible re-run."""

    def __init__(self, orchestrator: VideoPipelineOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._visual_planner = CorrectiveVisualPlanner()

    def apply(self, job: Any, plan: CorrectionPlan) -> list[str]:
        """Execute the plan; return the list of pipeline stages re-run."""
        job_dir = self._orchestrator.output_dir / job.job_id

        if plan.target == CorrectionTarget.RENDER:
            # Render-only failure: preserve ALL planning artifacts, rerender.
            self._orchestrator.run_stages(job, [STAGE_RENDER])
            return [STAGE_RENDER]

        if plan.target == CorrectionTarget.SCRIPT:
            # Script regeneration: wrap the registered script agent so the
            # correction context flows into generation, then cascade the
            # downstream artifacts (visual plan + render).
            base_agent = self._orchestrator.registry.get(STAGE_SCRIPT)
            self._orchestrator.registry.register(
                CorrectiveScriptAgent(base_agent), stage=STAGE_SCRIPT
            )
            self._orchestrator.run_stages(
                job, [STAGE_SCRIPT, STAGE_VISUAL_PLAN, STAGE_RENDER]
            )
            return [STAGE_SCRIPT, STAGE_VISUAL_PLAN, STAGE_RENDER]

        if plan.target in (CorrectionTarget.STORY_BEATS, CorrectionTarget.VISUAL_BEATS):
            # Visual correction: preserve research/strategy/script, rewrite
            # the visual plan (scene-targeted when scene ids are known),
            # then rerender.
            current = job.visual_plan
            if current is None:
                self._orchestrator.run_stages(job, [STAGE_VISUAL_PLAN, STAGE_RENDER])
                return [STAGE_VISUAL_PLAN, STAGE_RENDER]
            corrected = self._visual_planner.replan(current, plan)
            job.visual_plan = corrected
            write_json_artifact(job_dir / "visual_plan.json", corrected)
            self._orchestrator.run_stages(job, [STAGE_RENDER])
            return [STAGE_VISUAL_PLAN, STAGE_RENDER]

        # RESEARCH / STRATEGY targets: full upstream regeneration + cascade.
        from src.orchestration.repair.dependency_map import pipeline_stage_for

        stages = _stages_from(pipeline_stage_for(plan.target))
        self._orchestrator.run_stages(job, stages)
        return stages


class CorrectionLoop:
    """Retry-limited correction loop with full attempt lineage."""

    def __init__(
        self,
        orchestrator: VideoPipelineOrchestrator,
        max_correction_attempts: int = DEFAULT_MAX_CORRECTION_ATTEMPTS,
        diagnoser: CorrectionDiagnoser | None = None,
        executor: CorrectionExecutor | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._max_attempts = max(0, int(max_correction_attempts))
        self._diagnoser = diagnoser or CorrectionDiagnoser()
        self._executor = executor or CorrectionExecutor(orchestrator)

    @property
    def max_correction_attempts(self) -> int:
        return self._max_attempts

    def run(self, job: Any, initial_report: QCReport) -> tuple[Any, CorrectionReport]:
        """Run the correction loop for ``job`` starting from ``initial_report``.

        Returns ``(job, CorrectionReport)``.  Guaranteed to terminate: at
        most ``max_correction_attempts`` correction iterations, each a
        bounded targeted regeneration (no unbounded loops).
        """
        job_dir = self._orchestrator.output_dir / job.job_id
        report = CorrectionReport(
            job_id=job.job_id,
            initial_qc_status=initial_report.overall_status.value,
            attempt_count=0,
        )
        current_qc: QCReport = initial_report
        correction_failed = False
        terminal_reason = ""
        # QC-driven retry intelligence state.
        previous_failed_before: set[str] | None = None
        previous_target: CorrectionTarget | None = None

        # Policy (requirement 11): PASS -> stop; WARN-only -> stop (never an
        # endless warning-driven cycle); FAIL -> diagnose and correct.
        while (
            current_qc.overall_status == QCStatus.FAIL
            and report.attempt_count < self._max_attempts
        ):
            attempt_number = report.attempt_count + 1
            plan = self._diagnoser.diagnose(current_qc, attempt_number=attempt_number)
            if plan is None:
                terminal_reason = "nothing_actionable"
                break  # nothing actionable -> stop rather than loop

            # Escalation rule: if the SAME failed checks persisted after the
            # previous correction at the same target, escalate one step
            # upstream.  When no upstream target exists, stop early rather
            # than burn retry attempts on a failure we cannot fix deeper.
            escalated_from = ""
            escalated = False
            if (
                previous_failed_before is not None
                and previous_target is not None
                and plan.target == previous_target
                and set(plan.failed_checks) == previous_failed_before
            ):
                upstream = _ESCALATION_UPSTREAM.get(plan.target)
                if upstream is None:
                    terminal_reason = "no_progress"
                    break
                escalated_from = plan.target.value
                plan = _escalate_plan(plan, upstream)
                escalated = True
                report.escalation_count += 1

            attempt = CorrectionAttempt(
                attempt_number=attempt_number,
                failed_checks=list(plan.failed_checks),
                diagnosis=plan.context_summary(),
                target_stage=plan.target_stage,
                target_artifact=plan.target_artifact,
                action=plan.action.value,
                reason=plan.reason.value,
                affected_scene_ids=list(plan.affected_scene_ids),
                result="pending",
                escalated=escalated,
                escalated_from=escalated_from,
            )
            report.attempts.append(attempt)
            report.attempt_count = attempt_number

            try:
                stages_re_run = self._executor.apply(job, plan)
                attempt.result = "applied: " + ",".join(stages_re_run)
            except Exception as exc:  # noqa: BLE001 - correction boundary
                attempt.result = f"correction_failed: {exc}"
                correction_failed = True
                terminal_reason = "correction_error"
                self._persist(job_dir, report)
                break

            current_qc = self._orchestrator.run_qc(job)
            attempt.qc_status_after = current_qc.overall_status.value
            failed_now = {
                c.check_name for c in current_qc.checks if c.status == QCStatus.FAIL
            }
            attempt.failed_checks_after = sorted(failed_now)
            if current_qc.overall_status != QCStatus.FAIL:
                attempt.result = "passed"
            else:
                attempt.result = "qc_failed"
                # No progress = the failed-check set did not shrink.
                attempt.no_progress = (
                    previous_failed_before is not None
                    and failed_now == previous_failed_before
                )
            previous_failed_before = failed_now
            previous_target = plan.target
            self._persist(job_dir, report)

        # Terminal reason bookkeeping (never hides failures).
        if current_qc.overall_status == QCStatus.FAIL:
            outcome = "FAILED_CORRECTION" if correction_failed else "FAILED_QC"
            if not terminal_reason:
                terminal_reason = (
                    "correction_error" if correction_failed else "max_attempts_reached"
                )
        elif not terminal_reason:
            outcome = "SUCCESS"
            terminal_reason = "qc_passed"
        else:
            outcome = "SUCCESS"

        from datetime import datetime, timezone

        report.final_qc_status = current_qc.overall_status.value
        report.final_publish_ready = current_qc.publish_ready
        report.final_outcome = outcome
        report.terminal_reason = terminal_reason
        report.finished_at = datetime.now(timezone.utc)
        self._persist(job_dir, report)
        return job, report

    # -- lineage -------------------------------------------------------------

    def _persist(self, job_dir: Path, report: CorrectionReport) -> None:
        """Append-only lineage: corrections.json + correction_report.json."""
        write_json_artifact(job_dir / "correction_report.json", report)
        corrections_path = job_dir / "corrections.json"
        history: list[dict] = []
        if corrections_path.exists():
            try:
                history = json.loads(corrections_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - corrupt history -> start fresh
                history = []
        history.append(report.model_dump(mode="json"))
        corrections_path.write_text(
            json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
        )
