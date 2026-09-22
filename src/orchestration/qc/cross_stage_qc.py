"""Cross-stage consistency QC validator.

Compares ScriptPackage ↔ VisualPlan ↔ Render output to catch cases where
an earlier stage claims one thing but the final output contains another.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.qc.models import QCCheck, QCStatus, QCSeverity


def _check_script_visual_scene_count(script: Any, visual_plan: Any) -> QCCheck:
    """Validate scene count is consistent with section count.

    Day-4 beat planning may split long/important beats into multiple visual
    scenes, so exact 1:1 equality is no longer required.  Acceptance:
    ``sections <= scenes <= 3 * sections``; anything outside that range is
    a FAIL.  More scenes than sections is intentional visual expansion and
    reports PASS with an informational message.
    """
    if script is None or visual_plan is None:
        return QCCheck(
            check_name="cross_stage_scene_count",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Cannot compare: script or visual_plan is None",
        )

    sections = getattr(script, "sections", None) or []
    scenes = getattr(visual_plan, "scenes", None) or []

    if len(scenes) < len(sections) or len(scenes) > 3 * max(1, len(sections)):
        return QCCheck(
            check_name="cross_stage_scene_count",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=(
                f"Section count ({len(sections)}) incompatible with "
                f"scene count ({len(scenes)})"
            ),
            details={"section_count": len(sections), "scene_count": len(scenes)},
        )

    if len(sections) != len(scenes):
        return QCCheck(
            check_name="cross_stage_scene_count",
            status=QCStatus.PASS,
            severity=QCSeverity.INFO,
            message=(
                f"Day-4 beat expansion: {len(sections)} section(s) -> "
                f"{len(scenes)} scene(s)"
            ),
            details={"section_count": len(sections), "scene_count": len(scenes)},
        )

    return QCCheck(
        check_name="cross_stage_scene_count",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Scene count matches section count ({len(sections)})",
    )


def _check_script_visual_duration(script: Any, visual_plan: Any) -> QCCheck:
    """Validate script duration matches visual plan duration."""
    if script is None or visual_plan is None:
        return QCCheck(
            check_name="cross_stage_duration",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Cannot compare: script or visual_plan is None",
        )

    script_duration = getattr(script, "total_duration_seconds", 0) or 0
    visual_duration = getattr(visual_plan, "total_duration_seconds", 0) or 0

    if script_duration > 0 and visual_duration > 0:
        mismatch = abs(script_duration - visual_duration)
        if mismatch > max(5, script_duration * 0.25):
            return QCCheck(
                check_name="cross_stage_duration",
                status=QCStatus.FAIL,
                severity=QCSeverity.FAIL,
                message=(
                    f"Major duration mismatch: script={script_duration}s, "
                    f"visual={visual_duration}s (delta={mismatch}s)"
                ),
                details={"script_duration": script_duration, "visual_duration": visual_duration, "delta": mismatch},
            )
        if mismatch > 0:
            return QCCheck(
                check_name="cross_stage_duration",
                status=QCStatus.WARN,
                severity=QCSeverity.WARN,
                message=(
                    f"Minor duration mismatch: script={script_duration}s, "
                    f"visual={visual_duration}s (delta={mismatch}s)"
                ),
                details={"script_duration": script_duration, "visual_duration": visual_duration, "delta": mismatch},
            )

    return QCCheck(
        check_name="cross_stage_duration",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Duration consistent: {script_duration}s",
    )
def _check_script_visual_topic(script: Any, visual_plan: Any) -> QCCheck:
    """Validate topic/title consistency between script and visual plan."""
    if script is None or visual_plan is None:
        return QCCheck(
            check_name="cross_stage_topic",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Cannot compare: script or visual_plan is None",
        )

    script_topic = str(getattr(script, "topic", "") or "").strip()
    visual_topic = str(getattr(visual_plan, "topic", "") or "").strip()
    script_title = str(getattr(script, "title", "") or "").strip()
    visual_title = str(getattr(visual_plan, "title", "") or "").strip()

    problems: list[str] = []
    if script_topic and visual_topic and script_topic != visual_topic:
        problems.append(f"topic mismatch: script={script_topic!r}, visual={visual_topic!r}")
    if script_title and visual_title and script_title != visual_title:
        problems.append(f"title mismatch: script={script_title!r}, visual={visual_title!r}")

    if problems:
        return QCCheck(
            check_name="cross_stage_topic",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message=f"Topic/title inconsistency: {'; '.join(problems)}",
            details={"problems": problems},
        )

    return QCCheck(
        check_name="cross_stage_topic",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="Topic/title consistent across stages",
    )


def _check_visual_render_output(visual_plan: Any, artifact: Any) -> QCCheck:
    """Validate visual plan matches the render output artifact."""
    if visual_plan is None or artifact is None:
        return QCCheck(
            check_name="cross_stage_render_output",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message="Cannot compare: visual_plan or artifact is None",
        )

    scenes = getattr(visual_plan, "scenes", None) or []
    artifact_scene_count = getattr(artifact, "scene_count", 0) or 0
    output_path = getattr(artifact, "output_path", "") or ""
    mp4_exists = getattr(artifact, "mp4_exists", False)

    problems: list[str] = []

    if artifact_scene_count > 0 and len(scenes) > 0:
        if artifact_scene_count != len(scenes):
            problems.append(
                f"scene count mismatch: visual={len(scenes)}, "
                f"artifact={artifact_scene_count}"
            )

    if not output_path:
        problems.append("artifact has no output_path")
    if not mp4_exists:
        problems.append("artifact.mp4_exists is False")

    if problems:
        return QCCheck(
            check_name="cross_stage_render_output",
            status=QCStatus.FAIL,
            severity=QCSeverity.FAIL,
            message=f"Render output issues: {'; '.join(problems)}",
            details={"problems": problems},
        )

    return QCCheck(
        check_name="cross_stage_render_output",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="Visual plan matches render output",
    )


def run_cross_stage_qc(
    script: Any = None,
    visual_plan: Any = None,
    artifact: Any = None,
) -> list[QCCheck]:
    """Run all cross-stage consistency QC checks.

    Args:
        script: A ``ScriptPackage`` (or None).
        visual_plan: A ``VisualPlan`` (or None).
        artifact: A ``VideoArtifact`` (or None).

    Returns:
        A list of ``QCCheck`` results.
    """
    return [
        _check_script_visual_scene_count(script, visual_plan),
        _check_script_visual_duration(script, visual_plan),
        _check_script_visual_topic(script, visual_plan),
        _check_visual_render_output(visual_plan, artifact),
    ]

