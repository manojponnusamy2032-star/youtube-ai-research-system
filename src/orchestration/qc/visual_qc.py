"""Visual Plan QC validator.

Validates a ``VisualPlan`` for structural integrity, scene numbering,
durations, narration/visual coverage, and render plan consistency.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.qc.models import QCCheck, QCStatus, QCSeverity


def _check_scene_count(plan: Any) -> QCCheck:
    """Validate that the plan has at least one scene."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_scene_count",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Visual plan has zero scenes",
        )

    return QCCheck(
        check_name="visual_scene_count",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Visual plan has {len(scenes)} scene(s)",
        details={"scene_count": len(scenes)},
    )


def _check_scene_numbering(plan: Any) -> QCCheck:
    """Validate scene numbering is ordered and consistent."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_scene_numbering",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Cannot validate numbering: no scenes",
        )

    numbers = [getattr(s, "scene_number", None) for s in scenes]
    if any(n is None for n in numbers):
        return QCCheck(
            check_name="visual_scene_numbering",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Some scenes have no scene_number",
        )

    expected = list(range(1, len(scenes) + 1))
    if numbers != expected:
        return QCCheck(
            check_name="visual_scene_numbering",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Scene numbering is not 1..N: got {numbers}",
            details={"expected": expected, "actual": numbers},
        )

    return QCCheck(
        check_name="visual_scene_numbering",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="Scene numbering is ordered and consistent",
    )


def _check_scene_durations(plan: Any) -> QCCheck:
    """Validate every scene has positive duration."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_scene_durations",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No scenes to validate durations",
        )

    bad_scenes: list[int] = []
    for idx, scene in enumerate(scenes):
        duration = getattr(scene, "duration_seconds", 0)
        if duration is None or duration <= 0:
            bad_scenes.append(idx + 1)

    if bad_scenes:
        return QCCheck(
            check_name="visual_scene_durations",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Scenes with non-positive duration: {bad_scenes}",
            details={"bad_scenes": bad_scenes},
        )

    return QCCheck(
        check_name="visual_scene_durations",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="All scenes have positive duration",
    )
def _check_narration_coverage(plan: Any) -> QCCheck:
    """Validate every scene has narration."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_narration_coverage",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No scenes to validate narration coverage",
        )

    missing: list[int] = []
    for idx, scene in enumerate(scenes):
        narration = getattr(scene, "narration", None)
        if not narration or not str(narration).strip():
            missing.append(idx + 1)

    if missing:
        return QCCheck(
            check_name="visual_narration_coverage",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Scenes missing narration: {missing}",
            details={"missing_narration_scenes": missing},
        )

    return QCCheck(
        check_name="visual_narration_coverage",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="All scenes have narration",
    )


def _check_visual_coverage(plan: Any) -> QCCheck:
    """Validate each scene contains meaningful visual information."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_coverage",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No scenes to validate visual coverage",
        )

    weak_scenes: list[int] = []
    for idx, scene in enumerate(scenes):
        prompt = str(getattr(scene, "visual_prompt", "") or "").strip()
        description = getattr(scene, "visual_description", None) or {}
        has_description = bool(description) if isinstance(description, dict) else bool(str(description).strip())
        animation = str(getattr(scene, "animation_instructions", "") or "").strip()

        if not prompt and not has_description and not animation:
            weak_scenes.append(idx + 1)

    if weak_scenes:
        return QCCheck(
            check_name="visual_coverage",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message=f"Scenes with minimal visual information: {weak_scenes}",
            details={"weak_scenes": weak_scenes},
        )

    return QCCheck(
        check_name="visual_coverage",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="All scenes contain meaningful visual information",
    )

def _check_render_plan(plan: Any) -> QCCheck:
    """Validate render_job_plan exists and matches scene count."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []
    render_job_plan = getattr(plan, "render_job_plan", None)

    if not render_job_plan or not isinstance(render_job_plan, dict):
        return QCCheck(
            check_name="visual_render_plan",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="render_job_plan is missing or not a dict",
        )

    jobs = render_job_plan.get("jobs", [])
    total_jobs = render_job_plan.get("total_jobs", len(jobs))

    if not jobs and not total_jobs:
        return QCCheck(
            check_name="visual_render_plan",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="render_job_plan has no jobs and no total_jobs count",
        )

    if total_jobs != len(scenes):
        return QCCheck(
            check_name="visual_render_plan",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=(
                f"render_job_plan total_jobs ({total_jobs}) != "
                f"scene count ({len(scenes)})"
            ),
            details={"total_jobs": total_jobs, "scene_count": len(scenes)},
        )

    return QCCheck(
        check_name="visual_render_plan",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"render_job_plan matches scene count ({len(scenes)})",
        details={"total_jobs": total_jobs},
    )


def _check_duration_consistency(plan: Any) -> QCCheck:
    """Validate sum(scene durations) ≈ total_duration_seconds."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []
    declared = getattr(plan, "total_duration_seconds", 0) or 0

    if not scenes:
        return QCCheck(
            check_name="visual_duration_consistency",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="No scenes to validate duration consistency",
        )

    scene_sum = sum(getattr(s, "duration_seconds", 0) or 0 for s in scenes)

    if declared > 0:
        mismatch = abs(declared - scene_sum)
        if mismatch > max(5, declared * 0.25):
            return QCCheck(
                check_name="visual_duration_consistency",
                status=QCStatus.FAIL,
                severity=QCSeverity.FAIL,
                message=(
                    f"Major duration mismatch: declared={declared}s, "
                    f"scene_sum={scene_sum}s (delta={mismatch}s)"
                ),
                details={"declared": declared, "scene_sum": scene_sum, "delta": mismatch},
            )
        if mismatch > 0:
            return QCCheck(
                check_name="visual_duration_consistency",
                status=QCStatus.WARN,
                severity=QCSeverity.WARN,
                message=(
                    f"Minor duration mismatch: declared={declared}s, "
                    f"scene_sum={scene_sum}s (delta={mismatch}s)"
                ),
                details={"declared": declared, "scene_sum": scene_sum, "delta": mismatch},
            )

    return QCCheck(
        check_name="visual_duration_consistency",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Duration consistent: {scene_sum}s",
        details={"declared": declared, "scene_sum": scene_sum},
    )


def run_visual_qc(plan: Any) -> list[QCCheck]:
    """Run all visual plan QC checks.

    Args:
        plan: A ``VisualPlan`` (or None).

    Returns:
        A list of ``QCCheck`` results.
    """
    if plan is None:
        return [
            QCCheck(
                check_name="visual_present",
                status=QCStatus.FAIL,
                severity=QCSeverity.FAIL,
                message="VisualPlan is missing (None)",
            )
        ]

    return [
        _check_scene_count(plan),
        _check_scene_numbering(plan),
        _check_scene_durations(plan),
        _check_narration_coverage(plan),
        _check_visual_coverage(plan),
        _check_render_plan(plan),
        _check_duration_consistency(plan),
    ]

