"""Visual repetition / activity QC checks.

Lightweight deterministic checks that detect obvious problems such as:
- all scenes using exactly identical visual prompts
- all scenes using exactly identical camera instructions
- all scenes using exactly identical character actions
- scenes with no motion/activity information

These produce WARN rather than FAIL.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.qc.models import QCCheck, QCStatus, QCSeverity


def _check_visual_prompt_diversity(plan: Any) -> QCCheck:
    """Detect all scenes using exactly identical visual prompts."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_prompt_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="No scenes to check visual prompt diversity",
        )

    prompts = [
        str(getattr(s, "visual_prompt", "") or "").strip() for s in scenes
    ]
    non_empty = [p for p in prompts if p]
    if not non_empty:
        return QCCheck(
            check_name="visual_prompt_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="All scenes have empty visual prompts",
        )

    if len(set(non_empty)) == 1 and len(non_empty) > 1:
        return QCCheck(
            check_name="visual_prompt_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="All scenes use identical visual prompts",
            details={"identical_prompt": non_empty[0][:100]},
        )

    return QCCheck(
        check_name="visual_prompt_diversity",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Visual prompts show diversity ({len(set(non_empty))} unique)",
    )
def _check_camera_diversity(plan: Any) -> QCCheck:
    """Detect all scenes using exactly identical camera instructions."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_camera_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="No scenes to check camera diversity",
        )

    cameras = [
        str(getattr(s, "camera_instructions", "") or "").strip() for s in scenes
    ]
    non_empty = [c for c in cameras if c]
    if not non_empty:
        return QCCheck(
            check_name="visual_camera_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="All scenes have empty camera instructions",
        )

    if len(set(non_empty)) == 1 and len(non_empty) > 1:
        return QCCheck(
            check_name="visual_camera_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="All scenes use identical camera instructions",
            details={"identical_camera": non_empty[0][:100]},
        )

    return QCCheck(
        check_name="visual_camera_diversity",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Camera instructions show diversity ({len(set(non_empty))} unique)",
    )


def _check_character_action_diversity(plan: Any) -> QCCheck:
    """Detect all scenes using exactly identical character actions."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_character_action_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="No scenes to check character action diversity",
        )

    actions = [
        str(getattr(s, "character_action", "") or "").strip() for s in scenes
    ]
    non_empty = [a for a in actions if a]
    if not non_empty:
        return QCCheck(
            check_name="visual_character_action_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="All scenes have empty character actions",
        )

    if len(set(non_empty)) == 1 and len(non_empty) > 1:
        return QCCheck(
            check_name="visual_character_action_diversity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="All scenes use identical character actions",
            details={"identical_action": non_empty[0][:100]},
        )

    return QCCheck(
        check_name="visual_character_action_diversity",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message=f"Character actions show diversity ({len(set(non_empty))} unique)",
    )


def _check_motion_activity(plan: Any) -> QCCheck:
    """Detect scenes with no motion/activity information."""
    scenes: list[Any] = getattr(plan, "scenes", None) or []

    if not scenes:
        return QCCheck(
            check_name="visual_motion_activity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message="No scenes to check motion activity",
        )

    no_motion: list[int] = []
    for idx, scene in enumerate(scenes):
        motions = getattr(scene, "motions", None) or []
        if not motions:
            no_motion.append(idx + 1)

    if no_motion:
        if len(no_motion) == len(scenes):
            return QCCheck(
                check_name="visual_motion_activity",
                status=QCStatus.WARN,
                severity=QCSeverity.WARN,
                message="No scenes have motion/activity information",
                details={"no_motion_scenes": no_motion},
            )
        return QCCheck(
            check_name="visual_motion_activity",
            status=QCStatus.WARN,
            severity=QCSeverity.WARN,
            message=f"Some scenes missing motion info: {no_motion}",
            details={"no_motion_scenes": no_motion},
        )

    return QCCheck(
        check_name="visual_motion_activity",
        status=QCStatus.PASS,
        severity=QCSeverity.INFO,
        message="All scenes have motion/activity information",
    )


def run_repetition_qc(plan: Any) -> list[QCCheck]:
    """Run all repetition/activity QC checks.

    Args:
        plan: A ``VisualPlan`` (or None).

    Returns:
        A list of ``QCCheck`` results.
    """
    if plan is None:
        return [
            QCCheck(
                check_name="visual_repetition_present",
                status=QCStatus.WARN,
                severity=QCSeverity.WARN,
                message="VisualPlan is missing (None)",
            )
        ]

    return [
        _check_visual_prompt_diversity(plan),
        _check_camera_diversity(plan),
        _check_character_action_diversity(plan),
        _check_motion_activity(plan),
    ]

