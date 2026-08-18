"""Multi-scene renderer service.

Renders a RenderJobPlan containing multiple RenderJobSpec objects into
individual scene MP4s using StickmanRenderer, then assembles them into
a single final MP4 using VideoAssembler.

Each scene is rendered independently with its own duration and audio
request. The final output preserves scene order and combines all scenes
into one playable video.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.models.content_package import AudioRequest, RenderConfig, RenderJobPlan, RenderJobSpec
from src.services.stickman_renderer import render_stickman_job
from src.services.video_assembler import VideoAssembler


class MultiSceneRenderer:
    """Renders multiple scenes and assembles them into a final MP4.

    Uses the existing StickmanRenderer for per-scene rendering and the
    existing VideoAssembler for final concatenation. Does not duplicate
    any FFmpeg logic.
    """

    def __init__(
        self,
        config: RenderConfig | None = None,
        video_assembler: VideoAssembler | None = None,
    ) -> None:
        """Initialize the multi-scene renderer.

        Args:
            config: Optional RenderConfig. A default is used if omitted.
            video_assembler: Optional VideoAssembler. A new one with
                execute_enabled=True is created if omitted.
        """
        self.config = config if config is not None else RenderConfig()
        self.video_assembler = video_assembler or VideoAssembler(
            config=self.config,
            execute_enabled=True,
        )

    def render_plan(
        self,
        plan: RenderJobPlan | dict[str, Any],
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Render a full RenderJobPlan into a single final MP4.

        Args:
            plan: RenderJobPlan or dict with jobs list. Each job must
                contain job_id, scene_number, duration_seconds, and
                optionally audio_request.
            output_path: Optional explicit output path for the final MP4.
                If not provided, uses the VideoAssembler's default path.

        Returns:
            Dictionary with:
            - status: "completed" or "failed"
            - scene_results: List of per-scene render results
            - final_output: Path to the final assembled MP4
            - total_scenes: Number of scenes rendered
            - total_duration_seconds: Sum of scene durations
            - error: Error message if failed
        """
        # Normalize plan to dict
        if isinstance(plan, RenderJobPlan):
            plan_dict = plan.to_dict()
        elif isinstance(plan, dict):
            plan_dict = plan
        else:
            return {
                "status": "failed",
                "error": "plan must be a RenderJobPlan or dict",
            }

        jobs_data = plan_dict.get("jobs", [])
        if not isinstance(jobs_data, list) or len(jobs_data) == 0:
            return {
                "status": "failed",
                "error": "plan.jobs must be a non-empty list",
            }

        # Render each scene
        scene_results: list[dict[str, Any]] = []
        render_outputs: list[dict[str, Any]] = []
        total_duration = 0

        for job_data in jobs_data:
            if not isinstance(job_data, dict):
                scene_results.append({
                    "status": "failed",
                    "error": "job must be a dictionary",
                })
                continue

            job_id = str(job_data.get("job_id", f"scene-{len(scene_results) + 1}"))
            scene_number = int(job_data.get("scene_number", len(scene_results) + 1))
            duration = int(job_data.get("duration_seconds", 0))
            total_duration += duration

            # Convert audio_request dict to AudioRequest if needed. If no
            # audio_request is provided, inject a silent one so every scene
            # has the same stream layout (video + audio) for concat assembly.
            audio_request = job_data.get("audio_request")
            if isinstance(audio_request, dict):
                audio_request = AudioRequest(
                    scene_number=int(audio_request.get("scene_number", scene_number)),
                    duration_seconds=int(audio_request.get("duration_seconds", duration)),
                    narration_text=str(audio_request.get("narration_text", "")),
                    voice_reference=str(audio_request.get("voice_reference", "")),
                    background_music_reference=str(audio_request.get("background_music_reference", "")),
                    sound_effect_references=list(audio_request.get("sound_effect_references", [])),
                    audio_format=str(audio_request.get("audio_format", "aac")),
                )
            elif audio_request is None:
                audio_request = AudioRequest(
                    scene_number=scene_number,
                    duration_seconds=duration,
                    narration_text="",
                    voice_reference="",
                    background_music_reference="",
                    sound_effect_references=[],
                    audio_format="aac",
                )

            # Build RenderJobSpec
            job_spec = RenderJobSpec(
                job_id=job_id,
                scene_number=scene_number,
                duration_seconds=duration,
                render_type=str(job_data.get("render_type", "stickman_animation")),
                character_ids=list(job_data.get("character_ids", [])),
                asset_ids=list(job_data.get("asset_ids", [])),
                visual_prompt=str(job_data.get("visual_prompt", "")),
                animation_instructions=str(job_data.get("animation_instructions", "")),
                camera_instructions=str(job_data.get("camera_instructions", "")),
                audio_requirements=str(job_data.get("audio_requirements", "")),
                audio_request=audio_request,
            )

            # Render the scene
            result = render_stickman_job(job_spec, self.config)
            scene_results.append(result)

            if result.get("status") == "completed":
                render_outputs.append({
                    "job_id": job_id,
                    "scene_number": scene_number,
                    "output_reference": result["output_reference"],
                    "status": "completed",
                    "duration_seconds": duration,
                })
            else:
                render_outputs.append({
                    "job_id": job_id,
                    "scene_number": scene_number,
                    "output_reference": None,
                    "status": "failed",
                    "duration_seconds": duration,
                })

        # Check if all scenes rendered successfully
        failed_scenes = [r for r in scene_results if r.get("status") != "completed"]
        if failed_scenes:
            return {
                "status": "failed",
                "scene_results": scene_results,
                "total_scenes": len(jobs_data),
                "total_duration_seconds": total_duration,
                "error": f"{len(failed_scenes)} scene(s) failed to render",
            }

        # Assemble the final video
        assembly_result = self.video_assembler.assemble(render_outputs)

        if assembly_result.get("status") != "completed":
            return {
                "status": "failed",
                "scene_results": scene_results,
                "total_scenes": len(jobs_data),
                "total_duration_seconds": total_duration,
                "error": f"Video assembly failed: {assembly_result.get('error', 'unknown')}",
                "assembly_result": assembly_result,
            }

        final_output = assembly_result.get("output_reference")
        if output_path and final_output and final_output != output_path:
            # Copy/move to the requested output path
            import shutil
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            shutil.copy2(final_output, output_path)
            final_output = output_path

        return {
            "status": "completed",
            "scene_results": scene_results,
            "final_output": final_output,
            "total_scenes": len(jobs_data),
            "total_duration_seconds": total_duration,
            "assembly_result": assembly_result,
        }