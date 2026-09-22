"""Day 4: Intelligent Visual Planner Agent.

Composes StoryBeatPlanner + VisualBeatPlanner to convert ScriptPackage
into a VisualPlan with render-ready ScenePlan dictionaries compatible
with the existing RenderPipelineOrchestrator / StickmanRenderer contract.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.agents.visual.base import VisualPlannerAgent
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan
from src.services.scene_composition import (
    CameraSpec,
    CharacterSpec,
    EffectSpec,
    EnvironmentSpec,
    ObjectSpec,
    SceneComposition,
    TextSpec,
)
from src.services.story_beat_planner import StoryBeatPlanner
from src.services.visual_beat_planner import VisualBeatPlanner


class IntelligentVisualPlannerAgent(VisualPlannerAgent):
    """Intelligent visual planner using story beats and visual state progression."""

    def __init__(self) -> None:
        self._story_planner = StoryBeatPlanner()
        self._visual_planner = VisualBeatPlanner()

    def run(self, request: ScriptPackage) -> VisualPlan:
        """Produce a VisualPlan with intelligent beat-based scene composition."""
        story_plan = self._story_planner.plan(request)
        visual_plan = self._visual_planner.plan(story_plan)

        scenes: list[VisualScenePlan] = []
        for vb in visual_plan.beats:
            scenes.append(self._build_scene(vb))

        total = sum(scene.duration_seconds for scene in scenes)
        render_job_plan = self._build_render_job_plan(scenes, request.title)

        return VisualPlan(
            topic=request.topic,
            title=request.title,
            scenes=scenes,
            render_job_plan=render_job_plan,
            total_duration_seconds=total,
        )


    # ------------------------------------------------------------------
    # Scene construction
    # ------------------------------------------------------------------

    def _build_scene(self, vb: Any) -> VisualScenePlan:
        """Convert a VisualBeat into a render-ready VisualScenePlan."""
        env_spec = EnvironmentSpec(type=vb.environment, ground_y=0.8)
        character = CharacterSpec(
            name="learner", pose=vb.character_pose, emotion=vb.character_emotion,
            x=0.5, y=0.75, scale=1.0, visible=True,
        )
        objects = [
            ObjectSpec(name=o, type=o, x=0.75, y=0.7, scale=0.8)
            for o in vb.objects
        ]
        text_el = (
            TextSpec(
                text=vb.text_overlay, x=0.5, y=0.08, size="normal",
                color=(255, 255, 255), style="bold", anchor="center",
                fade_in=0.5, fade_out=0.5, duration=vb.duration_seconds,
            )
            if vb.text_overlay else None
        )
        effects = (
            [EffectSpec(
                type="highlight", target="character", start=0.0,
                duration=min(1.5, vb.duration_seconds * 0.4),
                parameters={"intensity": 0.8},
            )]
            if vb.emphasis_label == "high" else []
        )
        cam = CameraSpec(
            pattern=vb.camera_pattern,
            focus_target="learner" if vb.emphasis_label == "high" else None,
            duration=vb.transition_duration, easing="ease_in_out",
        )
        comp = SceneComposition(
            environment=env_spec, characters=[character], objects=objects,
            text_elements=[text_el] if text_el else [], effects=effects,
            camera=cam,
        )
        motions = _make_motions(vb.duration_seconds)
        transition = {
            "type": vb.transition_type,
            "duration": vb.transition_duration,
            "parameters": {},
        }
        audio_request = {
            "scene_number": vb.scene_number,
            "duration_seconds": vb.duration_seconds,
            "narration_text": vb.narration_text,
            "voice_reference": "default",
            "background_music_reference": "",
            "sound_effect_references": [],
            "audio_format": "aac",
        }
        return VisualScenePlan(
            scene_number=vb.scene_number,
            duration_seconds=vb.duration_seconds,
            narration=vb.narration_text,
            render_type="stickman_animation",
            visual_prompt=f"Stickman scene: {vb.scene_purpose}",
            animation_instructions=(
                f"{vb.character_action}; {vb.character_emotion}; "
                f"{vb.text_overlay}"
            ),
            camera_instructions=vb.camera_pattern.replace("_", " "),
            audio_requirements="narration",
            character_action=vb.character_action,
            motions=motions,
            transition_to_next=transition,
            audio_request=audio_request,
            visual_description=comp.to_dict(),
        )

    # ------------------------------------------------------------------
    # Render job plan
    # ------------------------------------------------------------------

    def _build_render_job_plan(
        self, scenes: list[VisualScenePlan], title: str,
    ) -> dict:
        """Build the RenderJobPlan dict consumed by the existing pipeline."""
        jobs: list[dict] = []
        for scene in scenes:
            slug = title.lower().replace(" ", "-")[:24]
            jobs.append({
                "job_id": f"{slug}-scene-{scene.scene_number:02d}",
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
        return {
            "total_jobs": len(jobs),
            "jobs": jobs,
            "total_duration_seconds": total,
        }


# ---------------------------------------------------------------------------
# Module-level motion builder (reused by _build_scene)
# ---------------------------------------------------------------------------

def _make_motions(duration: int) -> list[dict]:
    """Standard enter + text fade motions."""
    enter_dur = min(0.8, duration * 0.3)
    fade_start = max(1.2, duration - 1.0)
    return [
        {"type": "enter", "target": "character", "start_time": 0.0,
         "duration": enter_dur, "easing": "ease_out",
         "parameters": {"from": {"x": -0.2, "y": 0.0}, "to": {"x": 0.0, "y": 0.0}}},
        {"type": "fade", "target": "text", "start_time": fade_start,
         "duration": 0.6, "easing": "ease_in_out",
         "parameters": {"from": 1.0, "to": 0.0}},
    ]
