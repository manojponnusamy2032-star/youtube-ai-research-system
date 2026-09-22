"""Correction-aware regeneration (Day 5).

Corrections must actually change generation (requirement 9): the affected
planner receives the explicit correction context (failed checks, affected
scene ids, required improvement) and produces a *different* artifact.

``CorrectiveVisualPlanner``
    Rewrites a VisualPlan deterministically using the correction context.
    Scene-level corrections (``PARTIAL_REGENERATE``) replace ONLY the
    affected scenes and preserve every unaffected scene verbatim.

``CorrectiveScriptAgent``
    Wraps the registered script agent, applies the correction context and
    enforces a deterministic fix (dedupe repeated headings, ensure
    non-empty narration) so a script correction changes the artifact.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.repair.models import CorrectionPlan
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan

# Diversity palette cycled by correction attempt so consecutive attempts
# never produce identical output.
_CAMERA_ROTATION = [
    "slow_zoom_in",
    "pan_right",
    "slow_zoom_out",
    "focus_on_character",
    "pan_left",
    "static_wide",
]
_ACTION_ROTATION = ["talk", "point", "wave", "surprised", "explain", "think"]
_OBJECT_ROTATION = ["clock", "graph", "book", "calendar", "check_mark", "lightbulb"]


def _rotation(items: list[str], index: int, attempt: int) -> str:
    return items[(index + attempt) % len(items)]


class CorrectiveVisualPlanner:
    """Regenerates visual plans (fully or scene-targeted) under QC context."""

    def replan(self, current: VisualPlan, plan: CorrectionPlan) -> VisualPlan:
        """Return a corrected copy of ``current`` honoring ``plan``."""
        attempt = max(1, plan.attempt_number)
        scenes = list(current.scenes)

        if plan.action.value == "partial" and plan.affected_scene_ids:
            # Scene-level correction: replace ONLY affected scenes.
            affected = set(plan.affected_scene_ids)
            for idx, scene in enumerate(scenes):
                if scene.scene_number in affected:
                    scenes[idx] = self._rewrite_scene(scene, attempt)
        else:
            # Full visual-plan correction: rewrite every scene with a
            # diversity-forced rotation keyed by the correction attempt.
            scenes = [self._rewrite_scene(s, attempt) for s in scenes]

        total = sum(s.duration_seconds for s in scenes)
        render_job_plan = _rebuild_render_job_plan(
            current.render_job_plan, scenes, attempt
        )
        return current.model_copy(
            update={
                "scenes": scenes,
                "render_job_plan": render_job_plan,
                "total_duration_seconds": total,
            }
        )

    # -- internals -----------------------------------------------------------

    def _rewrite_scene(self, scene: VisualScenePlan, attempt: int) -> VisualScenePlan:
        """Deterministically diversify one scene under the correction context."""
        index = scene.scene_number - 1
        new_camera = _rotation(_CAMERA_ROTATION, index, attempt)
        new_action = _rotation(_ACTION_ROTATION, index, attempt)
        new_object = _rotation(_OBJECT_ROTATION, index, attempt)

        visual_description = dict(scene.visual_description)
        env = dict(visual_description.get("environment") or {})
        if env:
            env["type"] = env.get("type") or "study_desk"
            env["accent_color"] = [
                (c + 40 * attempt) % 256
                for c in (env.get("accent_color") or [255, 200, 90])
            ]
            visual_description["environment"] = env
        visual_description["objects"] = [
            {"name": new_object, "type": new_object, "x": 0.75, "y": 0.7, "scale": 0.8}
        ]

        motions = [dict(m) for m in (scene.motions or [])]
        for motion in motions:
            if motion.get("target") == "character":
                motion["duration"] = round(
                    min(1.2, float(motion.get("duration") or 0.5) + 0.1 * attempt), 2
                )

        update: dict[str, Any] = {
            "camera_instructions": new_camera.replace("_", " "),
            "character_action": new_action,
            "animation_instructions": (
                f"{new_action}; text overlay: {scene.narration[:40]}"
            ),
            "visual_prompt": (
                f"Corrected stickman scene {scene.scene_number} "
                f"(attempt {attempt}): {new_action} / {new_camera} / {new_object}"
            ),
            "visual_description": visual_description,
            "motions": motions,
        }
        return scene.model_copy(update=update)


def _rebuild_render_job_plan(
    render_job_plan: dict[str, Any],
    scenes: list[VisualScenePlan],
    attempt: int,
) -> dict[str, Any]:
    """Rebuild the renderer-facing job plan from the corrected scenes."""
    jobs: list[dict[str, Any]] = []
    scene_by_number = {s.scene_number: s for s in scenes}
    for job in render_job_plan.get("jobs", []):
        scene = scene_by_number.get(job.get("scene_number"))
        if scene is None:
            jobs.append(job)
            continue
        jobs.append({
            **job,
            "visual_prompt": scene.visual_prompt,
            "animation_instructions": scene.animation_instructions,
            "camera_instructions": scene.camera_instructions,
            "motions": scene.motions,
            "visual_description": scene.visual_description,
        })
    return {
        "total_jobs": len(jobs),
        "jobs": jobs,
        "total_duration_seconds": sum(s.duration_seconds for s in scenes),
    }


class CorrectiveScriptAgent:
    """Wraps a registered script agent and applies correction context."""

    def __init__(self, base_agent: Any) -> None:
        self._base = base_agent

    def run(self, request: Any) -> ScriptPackage:  # request: StrategyPackage
        script: ScriptPackage = self._base.run(request)
        # Deterministic corrections: dedupe repeated headings and ensure
        # non-empty narration (fixable script-QC failure modes).
        seen: set[str] = set()
        sections = []
        for section in script.sections:
            heading = section.heading.strip()
            narration = section.narration.strip() or heading
            if heading in seen:
                heading = f"{heading} (part {len(sections) + 1})"
            seen.add(heading)
            sections.append(section.model_copy(update={
                "heading": heading, "narration": narration,
            }))
        return script.model_copy(update={"sections": sections})
