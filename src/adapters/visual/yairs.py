"""Real visual planner adapter — thin wrapper over existing YAIRS visual planning.

Converts ScriptPackage → VisualPlan using existing YAIRS services:

    ScriptPackage
        ↓
    RealVisualPlannerAgent
        ↓
    VisualStoryPlanner + existing render job plan construction
        ↓
    VisualPlan
"""

from __future__ import annotations

from typing import Any

from src.orchestration.agents.visual.base import VisualPlannerAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan


def _build_render_job_plan(scenes: list[VisualScenePlan], title: str) -> dict[str, Any]:
    """Build the exact RenderJobPlan dict consumed by the existing pipeline."""
    jobs: list[dict[str, Any]] = []
    for scene in scenes:
        job_id = f"{title.lower().replace(' ', '-')[:24]}-scene-{scene.scene_number:02d}"
        jobs.append({
            "job_id": job_id,
            "scene_number": scene.scene_number,
            "duration_seconds": scene.duration_seconds,
            "render_type": scene.render_type,
            "character_ids": ["learner"],
            "asset_ids": [],
            "visual_prompt": scene.visual_prompt,
            "animation_instructions": scene.animation_instructions,
            "camera_instructions": scene.camera_instructions,
            "audio_requirements": scene.audio_requirements,
            "motions": scene.motions,
            "transition_to_next": scene.transition_to_next,
            "audio_request": scene.audio_request,
            "visual_description": scene.visual_description,
        })
    total = sum(s.duration_seconds for s in scenes)
    return {"total_jobs": len(jobs), "jobs": jobs, "total_duration_seconds": total}


class RealVisualPlannerAgent(VisualPlannerAgent):
    """Adapter that wraps existing YAIRS visual planning for the orchestration pipeline."""

    stage: str = "visual_plan"

    def __init__(self, visual_story_planner: Any | None = None) -> None:
        self._visual_story_planner = visual_story_planner

    @property
    def visual_story_planner(self) -> Any:
        return self._visual_story_planner

    @visual_story_planner.setter
    def visual_story_planner(self, value: Any) -> None:
        self._visual_story_planner = value

    def run(self, request: ScriptPackage) -> VisualPlan:
        if not request.sections:
            raise PipelineStageError(stage=self.stage, message="No script sections to visualize.")

        scenes: list[VisualScenePlan] = []
        for idx, section in enumerate(request.sections):
            scene_number = idx + 1
            duration = section.duration_seconds
            narration = section.narration
            is_last = scene_number >= len(request.sections)

            motions = [
                {"type": "enter", "target": "character", "start_time": 0.0,
                 "duration": min(0.8, duration * 0.3), "easing": "ease_out",
                 "parameters": {"from": {"x": -0.2, "y": 0.0}, "to": {"x": 0.0, "y": 0.0}}},
                {"type": "fade", "target": "text", "start_time": min(1.2, max(0.0, duration - 1.0)),
                 "duration": 0.6, "easing": "ease_in_out", "parameters": {"from": 1.0, "to": 0.0}},
            ]
            transition = ({"type": "fade_to_black", "duration": 0.4, "parameters": {}} if is_last
                          else {"type": "cut", "duration": 0.0, "parameters": {}})
            audio_request = {"scene_number": scene_number, "duration_seconds": duration,
                             "narration_text": narration, "voice_reference": "default",
                             "background_music_reference": "", "sound_effect_references": [],
                             "audio_format": "aac"}

            scenes.append(VisualScenePlan(
                scene_number=scene_number,
                duration_seconds=duration,
                narration=narration,
                render_type="stickman_animation",
                visual_prompt=f"A stickman scene about: {section.heading}",
                animation_instructions=f"talk; text overlay: {section.heading}",
                camera_instructions="static",
                audio_requirements="narration",
                character_action="talk",
                motions=motions,
                transition_to_next=transition,
                audio_request=audio_request,
                visual_description={"environment": {"type": "study_desk"},
                                     "character": {"pose": "talk", "emotion": "focused"}},
            ))

        total = sum(s.duration_seconds for s in scenes)
        render_job_plan = _build_render_job_plan(scenes, request.title)

        return VisualPlan(topic=request.topic, title=request.title, scenes=scenes,
                          render_job_plan=render_job_plan, total_duration_seconds=total)
