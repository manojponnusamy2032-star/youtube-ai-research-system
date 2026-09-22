"""CorrectionDiagnoser (Day 5).

Deterministic mapping from QC failures to the smallest reasonable
correction target.  No LLM judge — pure rules over ``QCCheck`` names.

Mapping policy (requirement 4):

    script_qc failure                -> SCRIPT
    visual_qc failure                -> VISUAL_BEATS
    repetition/static visual failure -> VISUAL_BEATS
    render_config failure            -> RENDER
    media corruption                 -> RENDER
    cross-stage script/visual match  -> VISUAL_BEATS (downstream)
    missing visual scene             -> VISUAL_BEATS

The diagnoser never proposes regenerating everything: it picks the
EARLIEST target in the dependency chain implicated by the failed checks,
which is by construction the smallest set that can fix the problem.
"""

from __future__ import annotations

from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.repair.dependency_map import (
    CORRECTION_CHAIN,
    artifact_field_for,
    pipeline_stage_for,
)
from src.orchestration.repair.models import (
    CorrectionAction,
    CorrectionPlan,
    CorrectionReason,
    CorrectionSeverity,
    CorrectionTarget,
    CorrectionTargetDetail,
)

# Deterministic rules: (prefix-match on check_name) -> (target, reason).
# Ordered most-specific first; the first matching rule wins.
_DIAGNOSIS_RULES: list[tuple[str, CorrectionTarget, CorrectionReason]] = [
    # Render / media problems -> re-render only, planning untouched.
    ("render_config", CorrectionTarget.RENDER, CorrectionReason.RENDER_CONFIG),
    ("media_", CorrectionTarget.RENDER, CorrectionReason.RENDER_MEDIA),
    ("mp4_", CorrectionTarget.RENDER, CorrectionReason.RENDER_MEDIA),
    # Cross-stage mismatch: script/visual mismatch is fixed downstream in the
    # visual planning stage (regenerating script would discard good narration).
    ("cross_stage", CorrectionTarget.VISUAL_BEATS, CorrectionReason.VISUAL_MISMATCH),
    # Script-quality problems -> regenerate script (cascade downstream).
    ("script_", CorrectionTarget.SCRIPT, CorrectionReason.SCRIPT_QUALITY),
    # All remaining visual/repetition problems -> visual beats.
    ("visual_", CorrectionTarget.VISUAL_BEATS, CorrectionReason.VISUAL_STATIC),
    ("repetition", CorrectionTarget.VISUAL_BEATS, CorrectionReason.VISUAL_STATIC),
    # Research / strategy stage failures (rare; QC does not check these today).
    ("strategy_", CorrectionTarget.STRATEGY, CorrectionReason.UNKNOWN),
    ("research_", CorrectionTarget.RESEARCH, CorrectionReason.UNKNOWN),
]


def _classify_check(check_name: str) -> tuple[CorrectionTarget, CorrectionReason] | None:
    """Apply the deterministic rules to one check name."""
    name = check_name.lower()
    for prefix, target, reason in _DIAGNOSIS_RULES:
        if name.startswith(prefix) or prefix in name:
            return target, reason
    return None


def _extract_scene_ids(report: QCReport, target: CorrectionTarget) -> list[int]:
    """Collect affected scene numbers from failed-check details, if any."""
    scene_ids: set[int] = set()
    if target not in (CorrectionTarget.VISUAL_BEATS, CorrectionTarget.STORY_BEATS):
        return []
    for check in report.checks:
        if check.status == QCStatus.PASS:
            continue
        for key in ("bad_scenes", "no_motion_scenes", "missing_scenes",
                    "scene_numbers", "affected_scenes"):
            value = check.details.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, int):
                        scene_ids.add(item)
                    elif isinstance(item, str) and item.isdigit():
                        scene_ids.add(int(item))
    return sorted(scene_ids)


class CorrectionDiagnoser:
    """QCReport -> CorrectionPlan (deterministic, no LLM)."""

    def diagnose(self, report: QCReport, attempt_number: int = 0) -> CorrectionPlan | None:
        """Diagnose a QC report and produce the smallest correction plan.

        Returns ``None`` when nothing needs correcting (PASS, or WARN with
        no failing checks — warnings do not trigger regeneration).
        """
        if report.overall_status == QCStatus.PASS:
            return None

        failed_checks = [
            check for check in report.checks
            if check.status == QCStatus.FAIL or check.severity.value == "fail"
        ]
        if not failed_checks:
            # WARN-only report: no hard failures -> no correction required.
            return None

        # Pick the EARLIEST target implicated by any failed check: fixing an
        # upstream artifact also fixes everything downstream of it.
        candidates: list[tuple[int, CorrectionTarget, CorrectionReason]] = []
        for check in failed_checks:
            classified = _classify_check(check.check_name)
            if classified is None:
                continue
            target, reason = classified
            candidates.append((CORRECTION_CHAIN.index(target), target, reason))

        if not candidates:
            # Unrecognized failure — conservatively target the visual plan
            # (never "regenerate everything").
            candidates.append((
                CORRECTION_CHAIN.index(CorrectionTarget.VISUAL_BEATS),
                CorrectionTarget.VISUAL_BEATS,
                CorrectionReason.UNKNOWN,
            ))

        candidates.sort(key=lambda item: item[0])
        _, target, reason = candidates[0]

        all_failed_names = sorted({c.check_name for c in failed_checks})
        scene_ids = _extract_scene_ids(report, target)
        action = (
            CorrectionAction.RERENDER
            if target == CorrectionTarget.RENDER
            else CorrectionAction.REGENERATE
        )
        if target in (CorrectionTarget.VISUAL_BEATS, CorrectionTarget.STORY_BEATS) and scene_ids:
            action = CorrectionAction.PARTIAL_REGENERATE

        return CorrectionPlan(
            job_id=report.job_id,
            target=target,
            target_stage=pipeline_stage_for(target),
            target_artifact=artifact_field_for(target),
            reason=reason,
            failed_checks=all_failed_names,
            severity=CorrectionSeverity.FAIL,
            action=action,
            attempt_number=attempt_number,
            affected_scene_ids=scene_ids,
            correction_context=self._build_context(
                report, target, reason, all_failed_names, scene_ids,
            ),
        )

    def resolve_target(self, target: CorrectionTarget) -> CorrectionTargetDetail:
        """Resolve a correction target to stage/artifact coordinates."""
        return CorrectionTargetDetail(
            target=target,
            stage=pipeline_stage_for(target),
            artifact=artifact_field_for(target),
        )

    # -- internals ------------------------------------------------------------

    def _build_context(
        self,
        report: QCReport,
        target: CorrectionTarget,
        reason: CorrectionReason,
        failed_checks: list[str],
        scene_ids: list[int],
    ) -> dict:
        """Explicit correction context carried into the regenerating agent."""
        messages = [c.message for c in report.checks if c.status == QCStatus.FAIL]
        context: dict = {
            "failed_checks": failed_checks,
            "failure_messages": messages,
            "correction_reason": reason.value,
            "required_improvement": self._required_improvement(reason),
        }
        if target in (CorrectionTarget.VISUAL_BEATS, CorrectionTarget.STORY_BEATS):
            context["affected_scene_ids"] = scene_ids
            context["instruction"] = (
                "Produce a visually distinct plan: vary camera instructions, "
                "character actions and motion across consecutive scenes. "
                "Preserve narration and durations."
            )
        elif target == CorrectionTarget.SCRIPT:
            context["instruction"] = (
                "Regenerate the script avoiding the reported quality problems; "
                "keep section count and duration constraints."
            )
        return context

    @staticmethod
    def _required_improvement(reason: CorrectionReason) -> str:
        return {
            CorrectionReason.VISUAL_STATIC: (
                "Consecutive scenes must differ in character action, camera "
                "and motion."
            ),
            CorrectionReason.VISUAL_MISMATCH: (
                "Visual plan must align with the script sections."
            ),
            CorrectionReason.VISUAL_MISSING: (
                "Every script section requires a matching visual scene."
            ),
            CorrectionReason.SCRIPT_QUALITY: "Script must satisfy script QC checks.",
            CorrectionReason.RENDER_MEDIA: "Re-render to produce a valid MP4.",
            CorrectionReason.RENDER_CONFIG: "Re-render honoring the render config.",
            CorrectionReason.UNKNOWN: "Resolve the reported QC failures.",
        }[reason]
