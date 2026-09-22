"""Deterministic mock visual planner agent.

Converts a ScriptPackage into a render-ready ``VisualPlan`` whose
``render_job_plan`` matches the exact dictionary contract consumed by the
existing ``RenderJobManager`` / ``RenderPipelineOrchestrator``.  Every scene
carries a structured ``visual_description`` (environment, character, text,
camera), valid ``Motion`` primitives, transitions and an ``AudioRequest`` so
the real StickmanRenderer + TTS pipeline can produce a real MP4.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.agents.visual.base import VisualPlannerAgent
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan

# Deterministic per-scene visual palette (indexed by scene number).
_ENVIRONMENTS = [
    ("study_desk", (20, 26, 34), (45, 52, 62), (255, 200, 90)),
    ("abstract_info_space", (16, 24, 48), (32, 40, 64), (120, 200, 255)),
    ("workspace", (30, 34, 42), (52, 58, 68), (255, 170, 60)),
    ("classroom", (24, 30, 40), (50, 58, 46), (130, 220, 130)),
    ("office", (28, 32, 40), (70, 74, 82), (255, 220, 120)),
    ("study_desk", (18, 22, 30), (40, 46, 56), (255, 180, 80)),
]

# (pose, emotion, camera_pattern, object) per section index.
_SCENE_SPECS = [
    ("talk", "focused", "slow_zoom_in", "clock"),
    ("surprised", "frustrated", "static", "graph"),
    ("point", "focused", "pan_left", "thought_bubble"),
    ("talk", "focused", "static", "book"),
    ("wave", "happy", "slow_zoom_out", "calendar"),
    ("point", "excited", "focus_on_character", "check_mark"),
]
class MockVisualPlannerAgent(VisualPlannerAgent):
    """Mock implementation — deterministic scenes derived from the script."""

    def run(self, request: ScriptPackage) -> VisualPlan:
        scenes: list[VisualScenePlan] = []
        total_scenes = len(request.sections)
        for index, section in enumerate(request.sections):
            scene_number = index + 1
            scenes.append(
                self._build_scene(
                    heading=section.heading,
                    narration=section.narration,
                    duration_seconds=section.duration_seconds,
                    scene_number=scene_number,
                    total_scenes=total_scenes,
                )
            )

        total = sum(scene.duration_seconds for scene in scenes)
        render_job_plan = self._build_render_job_plan(scenes, title=request.title)
        return VisualPlan(
            topic=request.topic,
            title=request.title,
            scenes=scenes,
            render_job_plan=render_job_plan,
            total_duration_seconds=total,
        )

    # -- internals -----------------------------------------------------------

    def _build_scene(
        self,
        heading: str,
        narration: str,
        duration_seconds: int,
        scene_number: int,
        total_scenes: int,
    ) -> VisualScenePlan:
        env_type, bg, ground, accent = _ENVIRONMENTS[(scene_number - 1) % len(_ENVIRONMENTS)]
        pose, emotion, camera_pattern, object_type = _SCENE_SPECS[(scene_number - 1) % len(_SCENE_SPECS)]

        visual_description: dict[str, Any] = {
            "environment": {
                "type": env_type,
                "background_color": list(bg),
                "ground_color": list(ground),
                "ground_y": 0.8,
                "accent_color": list(accent),
            },
            "characters": [
                {
                    "name": "learner",
                    "pose": pose,
                    "emotion": emotion,
                    "x": 0.5,
                    "y": 0.78,
                    "scale": 1.0,
                    "color": [255, 255, 255],
                    "visible": True,
                }
            ],
            "objects": [
                {
                    "name": f"prop_{object_type}",
                    "type": object_type,
                    "x": 0.82,
                    "y": 0.55,
                    "scale": 1.0,
                    "rotation": 0.0,
                    "opacity": 1.0,
                    "visible": True,
                    "color": list(accent),
                }
            ],
            "text_elements": [
                {
                    "text": heading,
                    "x": 0.5,
                    "y": 0.2,
                    "size": "large",
                    "color": [255, 255, 255],
                    "opacity": 1.0,
                    "style": "bold",
                    "anchor": "center",
                    "max_width": 0.8,
                    "fade_in": 0.4,
                    "fade_out": 0.0,
                    "appear_at": 0.0,
                    "duration": 0.0,
                }
            ],
            "effects": [],
            "camera": {
                "pattern": camera_pattern,
                "focus_target": None,
                "start_state": {},
                "end_state": {},
                "duration": 0.0,
                "easing": "ease_in_out",
            },
        }

        motions = [
            {
                "type": "enter",
                "target": "character",
                "start_time": 0.0,
                "duration": min(0.8, duration_seconds * 0.3),
                "easing": "ease_out",
                "parameters": {"from": {"x": -0.2, "y": 0.0}, "to": {"x": 0.0, "y": 0.0}},
            },
            {
                "type": "fade",
                "target": "text",
                "start_time": min(1.2, max(0.0, duration_seconds - 1.0)),
                "duration": 0.6,
                "easing": "ease_in_out",
                "parameters": {"from": 1.0, "to": 0.0},
            },
        ]

        is_last = scene_number >= total_scenes
        transition = (
            {"type": "fade_to_black", "duration": 0.4, "parameters": {}}
            if is_last
            else {"type": "cut", "duration": 0.0, "parameters": {}}
        )

        audio_request = {
            "scene_number": scene_number,
            "duration_seconds": duration_seconds,
            "narration_text": narration,
            "voice_reference": "default",
            "background_music_reference": "",
            "sound_effect_references": [],
            "audio_format": "aac",
        }

        return VisualScenePlan(
            scene_number=scene_number,
            duration_seconds=duration_seconds,
            narration=narration,
            render_type="stickman_animation",
            visual_prompt=f"A stickman scene about: {heading}",
            animation_instructions=f"{pose}; text overlay: {heading}",
            camera_instructions=camera_pattern.replace("_", " "),
            audio_requirements="narration",
            character_action=pose,
            motions=motions,
            transition_to_next=transition,
            audio_request=audio_request,
            visual_description=visual_description,
        )

    def _build_render_job_plan(self, scenes: list[VisualScenePlan], title: str) -> dict[str, Any]:
        """Build the exact RenderJobPlan dict consumed by the existing pipeline."""
        jobs: list[dict[str, Any]] = []
        for scene in scenes:
            job_id = f"{title.lower().replace(' ', '-')[:24]}-scene-{scene.scene_number:02d}"
            jobs.append(
                {
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
                }
            )
        total = sum(scene.duration_seconds for scene in scenes)
        return {
            "total_jobs": len(jobs),
            "jobs": jobs,
            "total_duration_seconds": total,
        }
