"""Stickman Animation Renderer.

Generates animated 2D stickman scenes using procedural frame generation
piped to FFmpeg for encoding. Uses only Python standard library and FFmpeg.

Supports a deterministic character-action system. The action is derived
from the RenderJobSpec ``animation_instructions`` when possible, and
defaults to walking when no action can be determined.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.render_job_executor import RenderRequest
from src.models.content_package import Motion, RenderConfig, RenderJobSpec
from src.services.ffmpeg_renderer import FFmpegRenderer
from src.services.scene_composition import (
    PAN_RANGE_RATIO,
    SAFE_MARGIN_RATIO,
    ZOOM_THEN_PAN_RANGE_RATIO,
    SceneComposition,
    resolve_text_placement,
)
from src.utils.motion_utils import apply_easing, clamp, interpolate_value, motion_progress

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - Pillow should exist, but keep a fallback.
    Image = None
    ImageDraw = None
    ImageFont = None


@dataclass
class StickmanPose:
    """Reusable representation of a stickman pose at a moment in time.

    All coordinates are in pixels. Angles are in radians.
    This abstraction lets future actions be added by computing a pose
    without duplicating drawing code.
    """

    head_x: int
    head_y: int
    head_radius: int
    neck_y: int
    shoulder_y: int
    hip_y: int
    left_arm_x: int
    left_arm_y: int
    right_arm_x: int
    right_arm_y: int
    left_leg_x: int
    left_leg_y: int
    right_leg_x: int
    right_leg_y: int
    stickman_x: int
    stickman_y: int
    body_length: int
    arm_length: int
    leg_length: int
    line_thickness: int
    camera_zoom: float = 1.0
    camera_pan_x: int = 0
    camera_pan_y: int = 0
    color: tuple[int, int, int] = (255, 255, 255)


class StickmanRenderer:
    """Renders animated stickman scenes using procedural generation."""

    def __init__(self, execute_enabled: bool = True) -> None:
        """Initialize the stickman renderer.
        
        Args:
            execute_enabled: If True, executes FFmpeg to produce MP4. Default: True
        """
        self.execute_enabled = execute_enabled
        self.ffmpeg_renderer = FFmpegRenderer(execute_enabled=execute_enabled)

    def is_available(self) -> bool:
        """Check if FFmpeg is available."""
        return self.ffmpeg_renderer.is_available()

    def render(self, request: RenderRequest) -> dict[str, Any]:
        """Render a stickman animation job.
        
        Args:
            request: Render request containing job and configuration
            
        Returns:
            Dictionary with render result information
        """
        config = request.render_config
        job = request.job
        transition_to_next = job.get("transition_to_next")
        
        # Build output path
        output_path = self.ffmpeg_renderer._build_output_path(config, job.get("job_id", "unknown"))
        
        # Validate output path
        self.ffmpeg_renderer._validate_output_path(output_path)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if not self.execute_enabled:
            # Return command info only
            result = {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "command_built",
                "output_reference": output_path,
                "duration_seconds": int(job.get("duration_seconds", 0)),
                "command": "stickman procedural generation (not executed)",
                "ffmpeg_available": self.is_available(),
            }
            if transition_to_next is not None:
                result["transition_to_next"] = transition_to_next.to_dict() if hasattr(transition_to_next, "to_dict") else dict(transition_to_next)
            return result
        
        # Check FFmpeg availability
        if not self.is_available():
            result = {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": "FFmpeg is not available on PATH",
            }
            if transition_to_next is not None:
                result["transition_to_next"] = transition_to_next.to_dict() if hasattr(transition_to_next, "to_dict") else dict(transition_to_next)
            return result
        
        # Parse audio request if present
        audio_request = None
        audio_req_data = job.get("audio_request")
        if audio_req_data:
            from src.models.content_package import AudioRequest
            if isinstance(audio_req_data, dict):
                audio_request = AudioRequest(
                    scene_number=int(audio_req_data.get("scene_number", 1)),
                    duration_seconds=int(audio_req_data.get("duration_seconds", 0)),
                    narration_text=str(audio_req_data.get("narration_text", "")),
                    voice_reference=str(audio_req_data.get("voice_reference", "")),
                    background_music_reference=str(audio_req_data.get("background_music_reference", "")),
                    sound_effect_references=list(audio_req_data.get("sound_effect_references", [])),
                    audio_format=str(audio_req_data.get("audio_format", "aac")),
                )
            elif isinstance(audio_req_data, AudioRequest):
                audio_request = audio_req_data

        camera_instructions = str(job.get("camera_instructions", ""))
        motions = self._collect_motions(request)

        video_target_path = output_path
        temp_video_path = None
        if audio_request:
            temp_video_path = output_path + ".temp_video.mp4"
            video_target_path = temp_video_path

        try:
            # Generate and encode animation
            self._generate_animation(
                job,
                config,
                video_target_path,
                motions=motions,
                camera_instructions=camera_instructions,
            )
            
            # Verify video output
            if not os.path.exists(video_target_path):
                result = {
                    "job_id": str(job.get("job_id", "unknown")),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": int(job.get("duration_seconds", 0)),
                    "error": f"Video output file not created: {video_target_path}",
                }
                if transition_to_next is not None:
                    result["transition_to_next"] = transition_to_next.to_dict() if hasattr(transition_to_next, "to_dict") else dict(transition_to_next)
                return result

            if audio_request:
                # 1. Render the audio
                from src.services.ffmpeg_audio_renderer import FFmpegAudioRenderer
                from src.services.audio_renderer import AudioRenderRequest
                
                audio_renderer = FFmpegAudioRenderer(
                    output_directory=config.output_directory,
                    execute_enabled=True,
                )
                
                audio_render_request = AudioRenderRequest(
                    audio_request=audio_request,
                    job=job,
                )
                audio_result = audio_renderer.render(audio_render_request)
                
                if audio_result.get("status") == "failed":
                    if temp_video_path and os.path.exists(temp_video_path):
                        try:
                            os.remove(temp_video_path)
                        except Exception:
                            pass
                    return {
                        "job_id": str(job.get("job_id", "unknown")),
                        "status": "failed",
                        "output_reference": None,
                        "duration_seconds": int(job.get("duration_seconds", 0)),
                        "error": f"Audio rendering failed: {audio_result.get('error')}",
                    }
                
                audio_reference = audio_result.get("audio_reference")
                
                # 2. Mux video and audio
                from src.services.media_muxer import MediaMuxer
                media_muxer = MediaMuxer(execute_enabled=True)
                
                mux_result = media_muxer.mux(
                    video_reference=temp_video_path,
                    audio_reference=audio_reference,
                    output_path=output_path,
                )
                
                # Clean up temp video
                if temp_video_path and os.path.exists(temp_video_path):
                    try:
                        os.remove(temp_video_path)
                    except Exception:
                        pass
                
                if mux_result.get("status") == "failed":
                    if audio_reference and os.path.exists(audio_reference):
                        try:
                            os.remove(audio_reference)
                        except Exception:
                            pass
                    return {
                        "job_id": str(job.get("job_id", "unknown")),
                        "status": "failed",
                        "output_reference": None,
                        "duration_seconds": int(job.get("duration_seconds", 0)),
                        "error": f"Muxing failed: {mux_result.get('error')}",
                    }
                
                # Clean up generated audio
                if audio_reference and os.path.exists(audio_reference):
                    try:
                        os.remove(audio_reference)
                    except Exception:
                        pass

            # Verify output
            if not os.path.exists(output_path):
                return {
                    "job_id": str(job.get("job_id", "unknown")),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": int(job.get("duration_seconds", 0)),
                    "error": f"Output file not created: {output_path}",
                }
            
            file_size = os.path.getsize(output_path)
            if file_size < 1000:
                result = {
                    "job_id": str(job.get("job_id", "unknown")),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": int(job.get("duration_seconds", 0)),
                    "error": f"Output file too small: {file_size} bytes",
                }
                if transition_to_next is not None:
                    result["transition_to_next"] = transition_to_next.to_dict() if hasattr(transition_to_next, "to_dict") else dict(transition_to_next)
                return result
            
            result = {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "completed",
                "output_reference": output_path,
                "duration_seconds": int(job.get("duration_seconds", 0)),
                "file_size_bytes": file_size,
            }
            if transition_to_next is not None:
                result["transition_to_next"] = transition_to_next.to_dict() if hasattr(transition_to_next, "to_dict") else dict(transition_to_next)
            return result
            
        except Exception as e:
            return {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": f"Stickman rendering failed: {str(e)}",
            }

    def _collect_motions(self, request: RenderRequest) -> list[Motion]:
        """Collect structured motions and legacy fallback motions."""
        motions = self._normalize_motions(getattr(request, "motions", []))
        if not motions:
            motions = self._normalize_motions(request.job.get("motions", []))

        structured_keys = {(motion.target, motion.type) for motion in motions}
        legacy_motions = self._legacy_motion_fallbacks(request.job, structured_keys)
        return motions + legacy_motions

    def _normalize_motions(self, motions: Any) -> list[Motion]:
        """Convert motion payloads into Motion objects."""
        normalized: list[Motion] = []
        if not isinstance(motions, list):
            return normalized

        for motion in motions:
            try:
                if isinstance(motion, Motion):
                    normalized.append(motion)
                elif isinstance(motion, dict):
                    normalized.append(Motion(**motion))
            except Exception:
                continue
        return normalized

    def _legacy_motion_fallbacks(
        self,
        job: dict[str, Any],
        structured_keys: set[tuple[str, str]],
    ) -> list[Motion]:
        """Convert legacy text instructions into structured motions."""
        motions: list[Motion] = []
        camera_text = str(job.get("camera_instructions", "")).lower()
        animation_text = str(job.get("animation_instructions", "")).lower()
        visual_text = str(job.get("visual_prompt", "")).lower()
        duration = max(0.5, float(job.get("duration_seconds", 1)))
        combined = f"{camera_text} {animation_text} {visual_text}"

        def add_motion(motion: Motion) -> None:
            key = (motion.target, motion.type)
            if key not in structured_keys:
                motions.append(motion)

        if ("camera", "zoom") not in structured_keys and any(token in combined for token in ("zoom in", "close-up", "zoom out", "zoom")):
            add_motion(
                Motion(
                    type="zoom",
                    target="camera",
                    start_time=0.0,
                    duration=min(2.5, duration),
                    easing="ease_in_out",
                    parameters={"from": 1.0, "to": 1.1 if "zoom out" not in combined else 0.92},
                )
            )

        if ("camera", "pan") not in structured_keys and any(token in combined for token in ("pan", "tracking", "follow", "split-screen")):
            add_motion(
                Motion(
                    type="pan",
                    target="camera",
                    start_time=0.0,
                    duration=min(2.5, duration),
                    easing="ease_in_out",
                    parameters={"from": {"x": 0.0, "y": 0.0}, "to": {"x": 0.15, "y": 0.0}},
                )
            )

        if ("character", "move") not in structured_keys and any(token in combined for token in ("walk", "move", "stroll", "across the screen")):
            add_motion(
                Motion(
                    type="move",
                    target="character",
                    start_time=0.25,
                    duration=min(1.5, duration),
                    easing="ease_in_out",
                    parameters={"from": {"x": 0.15, "y": 0.75}, "to": {"x": 0.5, "y": 0.75}},
                )
            )

        if ("character", "enter") not in structured_keys and any(token in combined for token in ("enter", "fade in", "appear", "opening")):
            add_motion(
                Motion(
                    type="enter",
                    target="character",
                    start_time=0.0,
                    duration=min(0.75, duration),
                    easing="ease_out",
                    parameters={"direction": "left"},
                )
            )

        if ("character", "exit") not in structured_keys and any(token in combined for token in ("exit", "fade out", "disappear", "end screen")):
            add_motion(
                Motion(
                    type="exit",
                    target="character",
                    start_time=max(0.0, duration - min(0.75, duration)),
                    duration=min(0.75, duration),
                    easing="ease_in",
                    parameters={"direction": "right"},
                )
            )

        if ("text", "fade") not in structured_keys and any(token in combined for token in ("text overlay", "graphics", "caption", "title")):
            add_motion(
                Motion(
                    type="fade",
                    target="text",
                    start_time=min(1.5, max(0.0, duration - 1.0)),
                    duration=min(1.0, duration),
                    easing="ease_in_out",
                    parameters={"from": 0.0, "to": 1.0},
                )
            )
        if ("text", "scale") not in structured_keys and any(token in combined for token in ("text overlay", "graphics", "caption", "title")):
            add_motion(
                Motion(
                    type="scale",
                    target="text",
                    start_time=min(1.5, max(0.0, duration - 1.0)),
                    duration=min(1.0, duration),
                    easing="ease_out",
                    parameters={"from": 0.9, "to": 1.0},
                )
            )

        return motions

    def _evaluate_motion_state(
        self,
        motions: list[Motion],
        current_time: float,
        duration: float,
        width: int,
        height: int,
        base_action: str,
        composition: SceneComposition | None = None,
    ) -> dict[str, Any]:
        """Evaluate active motions into a lightweight render state."""
        state: dict[str, Any] = {
            "camera_zoom": 1.0,
            "camera_pan_x": 0,
            "camera_pan_y": 0,
            "character_x": None,
            "character_y": None,
            "character_scale": 1.0,
            "character_opacity": 1.0,
            "character_visible": True,
            "text_opacity": 0.0,
            "text_scale": 1.0,
            "text_visible": False,
            "object_layers": {},
            "environment": {},
            "named_characters": {},
            "typed_objects": {},
            "text_specs": [],
            "effect_specs": [],
            "_camera_spec": None,
            "_camera_motion_seen": False,
            "suppress_primary_character": False,
        }

        if composition is not None:
            if composition.environment is not None:
                state["environment"] = composition.environment.to_dict()
            for ch in composition.characters:
                state["named_characters"][ch.name] = {
                    "spec": ch,
                    "x": None,
                    "y": None,
                    "scale": ch.scale,
                    "opacity": 1.0,
                    "visible": ch.visible,
                }
            for ob in composition.objects:
                od = ob.to_dict()
                od["x"] = ob.x * width
                od["y"] = ob.y * height
                state["typed_objects"][ob.name] = od
            state["text_specs"] = [t.to_dict() for t in composition.text_elements]
            state["effect_specs"] = [e.to_dict() for e in composition.effects]
            if composition.camera is not None:
                state["_camera_spec"] = composition.camera.to_dict()
            state["suppress_primary_character"] = bool(composition.characters)

        has_text_motion = any(motion.target == "text" for motion in motions)
        state["text_visible"] = has_text_motion
        if has_text_motion:
            state["text_opacity"] = 0.0

        for motion in motions:
            if current_time <= motion.start_time:
                phase = 0.0
            elif current_time >= motion.start_time + motion.duration:
                phase = 1.0
            else:
                phase = (current_time - motion.start_time) / motion.duration
            eased = apply_easing(phase, motion.easing)
            params = motion.parameters or {}

            if motion.target == "camera":
                state["_camera_motion_seen"] = True
                if motion.type == "zoom":
                    start = float(params.get("from", 1.0))
                    end = float(params.get("to", 1.0))
                    state["camera_zoom"] = interpolate_value(start, end, eased)
                elif motion.type == "pan":
                    start = params.get("from", {"x": 0.0, "y": 0.0})
                    end = params.get("to", {"x": 0.0, "y": 0.0})
                    pan = interpolate_value(start, end, eased)
                    if isinstance(pan, dict):
                        state["camera_pan_x"] = int(float(pan.get("x", 0.0)) * width)
                        state["camera_pan_y"] = int(float(pan.get("y", 0.0)) * height)

            elif motion.target == "character":
                tid = str(getattr(motion, "target_id", "") or "")
                bucket: dict[str, Any] | None = None
                if tid and tid in state["named_characters"]:
                    bucket = state["named_characters"][tid]

                def _set_pos(px: float, py: float) -> None:
                    if bucket is not None:
                        bucket["x"] = px
                        bucket["y"] = py
                    else:
                        state["character_x"] = px
                        state["character_y"] = py

                def _get_scale() -> float:
                    return float(bucket["scale"]) if bucket is not None else float(state["character_scale"])

                def _set_scale(v: float) -> None:
                    if bucket is not None:
                        bucket["scale"] = v
                    else:
                        state["character_scale"] = v

                def _set_opacity(v: float) -> None:
                    if bucket is not None:
                        bucket["opacity"] = v
                    else:
                        state["character_opacity"] = v

                if motion.type in {"move", "enter", "exit"}:
                    start = params.get("from")
                    end = params.get("to")
                    if start is None or end is None:
                        direction = str(params.get("direction", "left")).lower()
                        if motion.type == "enter":
                            start, end = self._offscreen_to_center(direction)
                        elif motion.type == "exit":
                            start, end = self._center_to_offscreen(direction)
                        else:
                            start = {"x": 0.15, "y": 0.75}
                            end = {"x": 0.5, "y": 0.75}
                    position = interpolate_value(start, end, eased)
                    if isinstance(position, dict):
                        _set_pos(
                            float(position.get("x", 0.5)) * width,
                            float(position.get("y", 0.75)) * height,
                        )
                elif motion.type == "scale":
                    start = float(params.get("from", 1.0))
                    end = float(params.get("to", 1.0))
                    _set_scale(interpolate_value(start, end, eased))
                elif motion.type == "fade":
                    start = float(params.get("from", 1.0))
                    end = float(params.get("to", 1.0))
                    _set_opacity(interpolate_value(start, end, eased))
                elif motion.type == "emphasize":
                    strength = float(params.get("strength", 0.1))
                    _set_scale(_get_scale() + strength * math.sin(math.pi * eased))
                elif motion.type == "rotate":
                    # Rotation is a no-op for stick figures; consume gracefully.
                    pass

            elif motion.target == "text":
                if motion.type in {"enter", "fade", "scale"}:
                    if motion.type == "enter":
                        state["text_visible"] = True
                    if motion.type == "fade":
                        start = float(params.get("from", 0.0))
                        end = float(params.get("to", 1.0))
                        state["text_opacity"] = interpolate_value(start, end, eased)
                    elif motion.type == "scale":
                        start = float(params.get("from", 0.9))
                        end = float(params.get("to", 1.0))
                        state["text_scale"] = interpolate_value(start, end, eased)
                elif motion.type == "emphasize":
                    state["text_scale"] = float(state["text_scale"]) + 0.05 * math.sin(math.pi * eased)

            elif motion.target == "object":
                target_id = motion.target_id or "object"
                if target_id in state["typed_objects"]:
                    object_state = state["typed_objects"][target_id]
                    if motion.type in {"move", "enter", "exit"}:
                        start = params.get("from")
                        end = params.get("to")
                        if start is None or end is None:
                            direction = str(params.get("direction", "left")).lower()
                            if motion.type == "enter":
                                start, end = self._offscreen_to_center(direction)
                            elif motion.type == "exit":
                                start, end = self._center_to_offscreen(direction)
                            else:
                                start = {"x": 0.2, "y": 0.3}
                                end = {"x": 0.75, "y": 0.3}
                        position = interpolate_value(start, end, eased)
                        if isinstance(position, dict):
                            object_state["x"] = float(position.get("x", 0.5)) * width
                            object_state["y"] = float(position.get("y", 0.5)) * height
                    elif motion.type == "scale":
                        object_state["scale"] = float(interpolate_value(float(params.get("from", 1.0)), float(params.get("to", 1.0)), eased))
                    elif motion.type == "fade":
                        object_state["opacity"] = float(interpolate_value(float(params.get("from", 1.0)), float(params.get("to", 1.0)), eased))
                    elif motion.type == "rotate":
                        object_state["rotation"] = float(interpolate_value(float(params.get("from", 0.0)), float(params.get("to", 0.0)), eased))
                    continue
                object_state = state["object_layers"].setdefault(
                    target_id,
                    {
                        "x": width * 0.8,
                        "y": height * 0.3,
                        "scale": 1.0,
                        "opacity": 1.0,
                    },
                )
                if motion.type in {"move", "enter", "exit"}:
                    start = params.get("from")
                    end = params.get("to")
                    if start is None or end is None:
                        direction = str(params.get("direction", "left")).lower()
                        if motion.type == "enter":
                            start, end = self._offscreen_to_center(direction)
                        elif motion.type == "exit":
                            start, end = self._center_to_offscreen(direction)
                        else:
                            start = {"x": 0.2, "y": 0.3}
                            end = {"x": 0.75, "y": 0.3}
                    position = interpolate_value(start, end, eased)
                    if isinstance(position, dict):
                        object_state["x"] = float(position.get("x", 0.5)) * width
                        object_state["y"] = float(position.get("y", 0.5)) * height
                elif motion.type == "scale":
                    object_state["scale"] = float(interpolate_value(float(params.get("from", 1.0)), float(params.get("to", 1.0)), eased))
                elif motion.type == "fade":
                    object_state["opacity"] = float(interpolate_value(float(params.get("from", 1.0)), float(params.get("to", 1.0)), eased))

        _cam_spec = state.pop("_camera_spec", None)
        if _cam_spec and not state.pop("_camera_motion_seen", False):
            self._apply_camera_pattern(state, _cam_spec, current_time, duration, width, height)

        if state["character_x"] is None or state["character_y"] is None:
            if base_action in ("walk", "run"):
                progress = current_time / duration if duration > 0 else 0.0
                state["character_x"] = width * (0.15 + 0.5 * progress)
                state["character_y"] = height * 0.75
            else:
                state["character_x"] = width * 0.5
                state["character_y"] = height * 0.75

        return state

    @staticmethod
    def _offscreen_to_center(direction: str) -> tuple[dict[str, float], dict[str, float]]:
        """Return start/end normalized positions for an entering element."""
        direction_name = direction.lower()
        if direction_name == "right":
            return {"x": 1.15, "y": 0.75}, {"x": 0.5, "y": 0.75}
        if direction_name == "top":
            return {"x": 0.5, "y": -0.15}, {"x": 0.5, "y": 0.75}
        if direction_name == "bottom":
            return {"x": 0.5, "y": 1.15}, {"x": 0.5, "y": 0.75}
        return {"x": -0.15, "y": 0.75}, {"x": 0.5, "y": 0.75}

    @staticmethod
    def _center_to_offscreen(direction: str) -> tuple[dict[str, float], dict[str, float]]:
        """Return start/end normalized positions for an exiting element."""
        direction_name = direction.lower()
        if direction_name == "right":
            return {"x": 0.5, "y": 0.75}, {"x": 1.15, "y": 0.75}
        if direction_name == "top":
            return {"x": 0.5, "y": 0.75}, {"x": 0.5, "y": -0.15}
        if direction_name == "bottom":
            return {"x": 0.5, "y": 0.75}, {"x": 0.5, "y": 1.15}
        return {"x": 0.5, "y": 0.75}, {"x": -0.15, "y": 0.75}

    def _detect_action(self, job: dict[str, Any]) -> str:
        """Determine the character action from the job specification.

        The action is extracted from the ``animation_instructions`` field
        when it contains one of the supported action keywords. Falls back
        to a deterministic keyword scan of visual_prompt as well.
        Defaults to ``walk`` to preserve existing behavior.

        Returns:
            One of: idle, walk, run, point, wave, jump, talk, surprised
        """
        text = str(job.get("animation_instructions", "")).lower()
        text += " " + str(job.get("visual_prompt", "")).lower()

        action_keywords: dict[str, list[str]] = {
            "idle": ["idle", "standing", "stand still", "waiting"],
            "walk": ["walk", "walking", "stroll", "strolling"],
            "run": ["run", "running", "sprint", "sprinting"],
            "point": ["point", "pointing", "gesture at", "indicate"],
            "wave": ["wave", "waving", "hello", "greeting"],
            "jump": ["jump", "jumping", "hop", "hopping", "leap", "leaping"],
            "talk": ["talk", "talking", "speak", "speaking", "narrate", "narrating"],
            "surprised": ["surprised", "surprise", "shock", "shocked", "amazed"],
        }

        for action, keywords in action_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return action

        return "walk"

    def _compute_pose(
        self,
        action: str,
        t: float,
        duration: float,
        width: int,
        height: int,
        camera_instructions: str = "",
        motion_state: dict[str, Any] | None = None,
        emotion: str = "",
    ) -> StickmanPose:
        """Compute a deterministic stickman pose for the given action at time t.

        Args:
            action: One of the supported action names.
            t: Current time in seconds.
            duration: Total duration in seconds.
            width: Frame width.
            height: Frame height.

        Returns:
            StickmanPose with all joint coordinates.
        """
        # Ground line
        ground_y = int(height * 0.75)

        # Stickman dimensions (proportional to frame)
        scale = min(width, height) * 0.15
        camera_text = camera_instructions.lower()
        progress = t / duration if duration > 0 else 0.0

        camera_zoom = 1.0
        camera_pan_x = 0
        camera_pan_y = 0
        character_x = None
        character_y = None
        character_scale = 1.0
        character_opacity = 1.0
        character_visible = True

        if motion_state:
            camera_zoom = float(motion_state.get("camera_zoom", camera_zoom))
            camera_pan_x = int(motion_state.get("camera_pan_x", camera_pan_x))
            camera_pan_y = int(motion_state.get("camera_pan_y", camera_pan_y))
            character_x = motion_state.get("character_x")
            character_y = motion_state.get("character_y")
            character_scale = float(motion_state.get("character_scale", character_scale))
            character_opacity = float(motion_state.get("character_opacity", character_opacity))
            character_visible = bool(motion_state.get("character_visible", True))
        else:
            if "zoom in" in camera_text or "close-up" in camera_text:
                camera_zoom = 1.0 + (0.12 * progress)
            elif "zoom out" in camera_text:
                camera_zoom = 1.12 - (0.12 * progress)
            elif "zoom" in camera_text:
                camera_zoom = 1.0 + (0.06 * math.sin(progress * math.pi))

            if "pan left" in camera_text:
                camera_pan_x = int(width * (0.06 - 0.12 * progress))
            elif "pan right" in camera_text:
                camera_pan_x = int(width * (-0.06 + 0.12 * progress))
            elif "tracking" in camera_text or "follow" in camera_text or "pan" in camera_text:
                camera_pan_x = int(math.sin(progress * math.pi * 2.0) * width * 0.04)

            if "tilt up" in camera_text:
                camera_pan_y = int(height * (0.02 - 0.04 * progress))
            elif "tilt down" in camera_text:
                camera_pan_y = int(height * (-0.02 + 0.04 * progress))

        effective_scale = scale * camera_zoom * character_scale
        head_radius = int(effective_scale * 0.15)
        body_length = int(effective_scale * 0.5)
        leg_length = int(effective_scale * 0.45)
        arm_length = int(effective_scale * 0.4)
        line_thickness = max(2, int(effective_scale * 0.02))
        color = (255, 255, 255)

        # Character horizontal position
        if character_x is not None:
            stickman_x = int(character_x)
        elif action in ("walk", "run"):
            # Walk/run: move left-to-center as before
            stickman_x = int(width * 0.15 + width * 0.5 * progress)
        else:
            # Non-locomotion actions: stay centered
            stickman_x = int(width * 0.5)

        if character_y is not None:
            stickman_y = int(character_y)
        else:
            stickman_y = ground_y - 10  # Feet on ground

        if not character_visible:
            stickman_x = -1000
            stickman_y = -1000

        # Head center
        head_x = stickman_x
        head_y = stickman_y - body_length - head_radius

        # Joints (relative to stickman position)
        neck_y = head_y + head_radius
        hip_y = neck_y + body_length
        shoulder_y = neck_y + int(body_length * 0.15)

        # Action-specific joint offsets (angles/signals evolve deterministically with t)
        # Walking cycle (generalized for walk/run)
        if action == "walk":
            cycle_speed = 4.0
            leg_angle = math.sin(t * cycle_speed) * 0.5
            arm_angle = -math.sin(t * cycle_speed) * 0.5
            arm_length_adj = arm_length
            leg_length_adj = leg_length
        elif action == "run":
            cycle_speed = 8.0
            leg_angle = math.sin(t * cycle_speed) * 0.7
            arm_angle = -math.sin(t * cycle_speed) * 0.7
            arm_length_adj = arm_length
            leg_length_adj = leg_length
        elif action == "idle":
            # Gentle breathing / subtle sway
            breath = math.sin(t * 1.5) * 0.05
            leg_angle = breath
            arm_angle = breath * 0.5
            arm_length_adj = arm_length
            leg_length_adj = leg_length
        elif action == "point":
            # Pointing arm extends forward and up, other arm at side
            point_angle = 0.3 + 0.1 * math.sin(t * 2.0)
            leg_angle = 0.05
            arm_angle = -0.1
            arm_length_adj = int(arm_length * 1.3)
            leg_length_adj = leg_length
            # Override right arm to point
            right_arm_x = stickman_x + int(arm_length_adj * math.cos(point_angle))
            right_arm_y = shoulder_y - int(arm_length_adj * math.sin(point_angle))
        elif action == "wave":
            # Waving arm rotates up and down rapidly
            wave_angle = 0.4 + 0.3 * math.sin(t * 6.0)
            leg_angle = 0.05
            arm_angle = -0.1
            arm_length_adj = arm_length
            leg_length_adj = leg_length
            right_arm_x = stickman_x + int(arm_length_adj * math.cos(wave_angle))
            right_arm_y = shoulder_y - int(arm_length_adj * math.sin(wave_angle))
        elif action == "jump":
            # Jumping: vertical bounce + legs tucked
            bounce = int(abs(math.sin(t * 3.0)) * int(height * 0.1))
            stickman_y = ground_y - 10 - bounce
            head_y = stickman_y - body_length - head_radius
            neck_y = head_y + head_radius
            hip_y = neck_y + body_length
            shoulder_y = neck_y + int(body_length * 0.15)
            leg_angle = 0.25
            arm_angle = -math.sin(t * 3.0) * 0.5
            arm_length_adj = arm_length
            leg_length_adj = int(leg_length * 0.8)  # Legs tucked
        elif action == "talk":
            # Talking: arms gesture, small bobbing, hands near mouth
            gesture = 0.2 + 0.15 * math.sin(t * 5.0)
            bob = math.sin(t * 5.0) * 2
            head_y = head_y + int(bob)
            leg_angle = 0.05
            arm_angle = 0.1
            arm_length_adj = int(arm_length * 0.9)
            leg_length_adj = leg_length
            # One hand near mouth
            right_arm_x = stickman_x + int(head_radius * 0.5)
            right_arm_y = shoulder_y - int(arm_length_adj * 0.6) + int(gesture * 10)
        elif action == "surprised":
            # Surprised: arms up, legs apart, small shake
            shake = math.sin(t * 8.0) * 2
            head_y = head_y + int(shake)
            leg_angle = 0.3
            arm_angle = -0.6
            arm_length_adj = int(arm_length * 1.2)
            leg_length_adj = int(leg_length * 1.1)
        else:
            # Fallback to walk
            cycle_speed = 4.0
            leg_angle = math.sin(t * cycle_speed) * 0.5
            arm_angle = -math.sin(t * cycle_speed) * 0.5
            arm_length_adj = arm_length
            leg_length_adj = leg_length

        # Emotion-driven body language (posture cues, not facial animation).
        if emotion in ("happy", "excited"):
            arm_angle -= 0.24          # lifted arms, energetic stance
            leg_angle += 0.04
        elif emotion == "sad":
            arm_angle += 0.30          # drooping arms
            head_y += int(head_radius * 0.30)
        elif emotion == "frustrated":
            arm_angle += 0.18
            head_y += int(head_radius * 0.12)
        elif emotion == "focused":
            arm_angle -= 0.10

        # Compute left/right arm positions (unless overridden above)
        left_arm_x = stickman_x + int(arm_length_adj * math.cos(arm_angle))
        left_arm_y = shoulder_y + int(arm_length_adj * math.sin(arm_angle))
        right_arm_x = stickman_x - int(arm_length_adj * math.cos(arm_angle))
        right_arm_y = shoulder_y - int(arm_length_adj * math.sin(arm_angle))

        # Compute left/right leg positions
        left_leg_x = stickman_x + int(leg_length_adj * math.cos(leg_angle))
        left_leg_y = hip_y + int(leg_length_adj * math.sin(leg_angle))
        right_leg_x = stickman_x - int(leg_length_adj * math.cos(leg_angle))
        right_leg_y = hip_y - int(leg_length_adj * math.sin(leg_angle))

        return StickmanPose(
            head_x=head_x,
            head_y=head_y,
            head_radius=head_radius,
            neck_y=neck_y,
            shoulder_y=shoulder_y,
            hip_y=hip_y,
            left_arm_x=left_arm_x,
            left_arm_y=left_arm_y,
            right_arm_x=right_arm_x,
            right_arm_y=right_arm_y,
            left_leg_x=left_leg_x,
            left_leg_y=left_leg_y,
            right_leg_x=right_leg_x,
            right_leg_y=right_leg_y,
            stickman_x=stickman_x,
            stickman_y=stickman_y,
            body_length=body_length,
            arm_length=arm_length,
            leg_length=leg_length,
            line_thickness=line_thickness,
            camera_zoom=camera_zoom,
            camera_pan_x=camera_pan_x,
            camera_pan_y=camera_pan_y,
            color=color,
        )

    def _generate_animation(
        self,
        job: dict[str, Any],
        config: RenderConfig,
        output_path: str,
        motions: list[Motion] | None = None,
        camera_instructions: str = "",
    ) -> None:
        """Generate stickman animation frames and encode with FFmpeg.
        
        Args:
            job: Job specification dictionary
            config: Render configuration
            output_path: Output file path
        """
        width = config.width
        height = config.height
        fps = config.fps
        duration = int(job.get("duration_seconds", 1))
        total_frames = duration * fps
        action = self._detect_action(job)
        motion_list = motions or []
        composition = SceneComposition.from_visual_description(job.get("visual_description"))
        
        # FFmpeg command to encode raw RGB frames from stdin
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",  # Read from stdin
            "-c:v", config.video_codec,
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        
        # Start FFmpeg process
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        try:
            # Generate and write frames
            for frame_idx in range(total_frames):
                t = frame_idx / fps  # Time in seconds
                motion_state = self._evaluate_motion_state(
                    motion_list,
                    t,
                    float(duration),
                    width,
                    height,
                    action,
                    composition=composition,
                )
                self._resolve_named_characters(motion_state, t, float(duration), width, height)
                pose = self._compute_pose(
                    action,
                    t,
                    duration,
                    width,
                    height,
                    camera_instructions=camera_instructions,
                    motion_state=motion_state,
                )
                if motion_state.get("suppress_primary_character"):
                    pose.stickman_x = -10000
                    pose.stickman_y = -10000
                frame_data = self._generate_frame(
                    width,
                    height,
                    t,
                    duration,
                    frame_idx,
                    total_frames,
                    pose,
                    job=job,
                    motion_state=motion_state,
                )
                proc.stdin.write(frame_data)
            
            # Close stdin to signal end of input
            proc.stdin.close()
            
            # Wait for completion
            stdout, stderr = proc.communicate(timeout=300)
            
            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"FFmpeg encoding failed: {error_msg}")
                
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("FFmpeg encoding timed out")
        except Exception:
            proc.kill()
            raise

    def _generate_frame(
        self,
        width: int,
        height: int,
        t: float,
        duration: float,
        frame_idx: int,
        total_frames: int,
        pose: StickmanPose,
        job: dict[str, Any] | None = None,
        motion_state: dict[str, Any] | None = None,
    ) -> bytes:
        """Generate a single RGB24 frame with animated stickman.

        Args:
            width: Frame width
            height: Frame height
            t: Current time in seconds
            duration: Total duration in seconds
            frame_idx: Current frame index
            total_frames: Total number of frames
            pose: StickmanPose computed for this instant.

        Returns:
            Raw RGB24 frame data as bytes
        """
        # Create frame buffer (RGB24: 3 bytes per pixel)
        frame = bytearray(width * height * 3)

        def transform_x(x: int) -> int:
            centered = (x - (width / 2.0)) * pose.camera_zoom
            return int(centered + (width / 2.0) + pose.camera_pan_x)

        def transform_y(y: int) -> int:
            centered = (y - (height / 2.0)) * pose.camera_zoom
            return int(centered + (height / 2.0) + pose.camera_pan_y)

        # Environment-aware backdrop (falls back to the classic outdoor scene).
        env = dict((motion_state or {}).get("environment") or {})
        bg_color = tuple(env.get("background_color", (135, 206, 235)))
        frame[0:len(frame)] = bytes(tuple(bg_color)) * (width * height)

        # Ground / floor plane
        ground_norm = float(env.get("ground_y", 0.75))
        ground_y = transform_y(int(height * ground_norm))
        ground_color = tuple(env.get("ground_color", (34, 139, 34)))
        self._draw_rect(frame, width, height, 0, ground_y, width, height - ground_y, ground_color)

        # Outdoor scenes keep the sun; indoor scenes get soft wall decor.
        if env.get("type", "default") == "default":
            sun_x = transform_x(int(width * 0.85))
            sun_y = transform_y(int(height * 0.15))
            sun_radius = max(1, int(min(width, height) * 0.05 * pose.camera_zoom))
            self._draw_circle(frame, width, height, sun_x, sun_y, sun_radius, (255, 255, 0))
        else:
            accent = tuple(env.get("accent_color", (255, 223, 100)))
            self._draw_environment_layers(
                frame, width, height, transform_x, transform_y, env, accent,
                motion_state=motion_state,
            )

        # Procedural objects (typed shapes), drawn behind characters.
        for obj_state in (motion_state or {}).get("typed_objects", {}).values():
            if not obj_state.get("visible", True):
                continue
            obj_opacity = max(0.0, min(1.0, float(obj_state.get("opacity", 1.0))))
            if obj_opacity <= 0.01:
                continue
            self._draw_typed_object(
                frame, width, height, transform_x, transform_y, obj_state, t,
            )

        # Additional composed characters (multi-character support).
        for cstate in (motion_state or {}).get("named_characters", {}).values():
            self._draw_named_character(
                frame, width, height, transform_x, transform_y, cstate,
            )

        # Draw head (circle)
        self._draw_circle(
            frame,
            width,
            height,
            transform_x(pose.head_x),
            transform_y(pose.head_y),
            max(1, int(pose.head_radius)),
            pose.color,
            opacity=max(0.0, min(1.0, float((motion_state or {}).get("character_opacity", 1.0)))),
        )

        # Body (line from neck to hip)
        self._draw_line(
            frame, width, height,
            transform_x(pose.stickman_x), transform_y(pose.neck_y),
            transform_x(pose.stickman_x), transform_y(pose.hip_y),
            pose.color, pose.line_thickness,
            opacity=max(0.0, min(1.0, float((motion_state or {}).get("character_opacity", 1.0)))),
        )

        # Arms (from shoulders)
        self._draw_line(
            frame, width, height,
            transform_x(pose.stickman_x), transform_y(pose.shoulder_y),
            transform_x(pose.left_arm_x), transform_y(pose.left_arm_y),
            pose.color, pose.line_thickness,
            opacity=max(0.0, min(1.0, float((motion_state or {}).get("character_opacity", 1.0)))),
        )
        self._draw_line(
            frame, width, height,
            transform_x(pose.stickman_x), transform_y(pose.shoulder_y),
            transform_x(pose.right_arm_x), transform_y(pose.right_arm_y),
            pose.color, pose.line_thickness,
            opacity=max(0.0, min(1.0, float((motion_state or {}).get("character_opacity", 1.0)))),
        )

        # Legs (from hips)
        self._draw_line(
            frame, width, height,
            transform_x(pose.stickman_x), transform_y(pose.hip_y),
            transform_x(pose.left_leg_x), transform_y(pose.left_leg_y),
            pose.color, pose.line_thickness,
            opacity=max(0.0, min(1.0, float((motion_state or {}).get("character_opacity", 1.0)))),
        )
        self._draw_line(
            frame, width, height,
            transform_x(pose.stickman_x), transform_y(pose.hip_y),
            transform_x(pose.right_leg_x), transform_y(pose.right_leg_y),
            pose.color, pose.line_thickness,
            opacity=max(0.0, min(1.0, float((motion_state or {}).get("character_opacity", 1.0)))),
        )

        # Visual emphasis effects drawn above entities.
        self._draw_scene_effects(
            frame, width, height, motion_state or {}, t, transform_x, transform_y,
        )

        # Draw any structured object layers as simple moving squares.
        for object_state in (motion_state or {}).get("object_layers", {}).values():
            object_x = int(object_state.get("x", width * 0.8))
            object_y = int(object_state.get("y", height * 0.3))
            object_scale = float(object_state.get("scale", 1.0))
            object_opacity = max(0.0, min(1.0, float(object_state.get("opacity", 1.0))))
            object_size = max(10, int(24 * object_scale))
            self._draw_rect(
                frame,
                width,
                height,
                transform_x(object_x) - object_size // 2,
                transform_y(object_y) - object_size // 2,
                object_size,
                object_size,
                (255, 80, 80),
                opacity=object_opacity,
            )

        text_drawn = False
        if motion_state and motion_state.get("text_specs"):
            text_drawn = self._draw_text_elements(
                frame, width, height, motion_state, t, duration,
            )
        if not text_drawn and motion_state and motion_state.get("text_visible", False):
            caption = str((job or {}).get("visual_prompt") or (job or {}).get("animation_instructions") or (job or {}).get("job_id") or "scene")
            self._draw_caption_overlay(
                frame,
                width,
                height,
                caption,
                opacity=max(0.0, min(1.0, float(motion_state.get("text_opacity", 1.0)))),
                scale=max(0.75, float(motion_state.get("text_scale", 1.0))),
            )

        return bytes(frame)

























    def _draw_text_elements(
        self,
        frame: bytearray,
        width: int,
        height: int,
        state: dict[str, Any],
        t: float,
        duration: float,
    ) -> bool:
        """Render structured TextSpec captions. Returns True if anything drew."""
        if Image is None or ImageDraw is None:
            return False
        specs = state.get("text_specs") or []
        if not specs:
            return False

        margin_x = int(width * SAFE_MARGIN_RATIO)
        margin_y = int(height * SAFE_MARGIN_RATIO)
        drew_any = False

        image = Image.frombytes("RGB", (width, height), bytes(frame))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for spec_idx, spec in enumerate(specs):
            if spec_idx in (state.get("_board_hosted") or set()):
                continue  # headline hosted inside the classroom board
            text = str(spec.get("text", "")).strip()
            if not text:
                continue
            opacity = _text_opacity(spec, t, duration)
            if opacity <= 0.01:
                continue
            scale_factor = {
                "small": 0.7, "normal": 1.0, "large": 1.4, "headline": 2.0,
            }.get(str(spec.get("size", "normal")), 1.0)
            px_size = max(10, int(min(width, height) * 0.030 * scale_factor))
            font = self._load_font(px_size)
            if font is None:
                continue

            color = tuple(spec.get("color", (255, 255, 255)))
            max_px = int(width * float(spec.get("max_width", 0.8)))
            max_px = min(max_px, width - 2 * margin_x)

            words = text.split()
            lines: list[str] = []
            current = ""
            for word in words:
                trial = (current + " " + word).strip()
                try:
                    tw = draw.textlength(trial, font=font)
                except Exception:
                    tw = len(trial) * px_size * 0.55
                if tw <= max_px or not current:
                    current = trial
                else:
                    lines.append(current)
                    current = word
            if current:
                lines.append(current)

            line_h = int(px_size * 1.32)
            block_h = line_h * len(lines)

            anchor_name = str(spec.get("anchor", "center"))
            nx = float(spec.get("x", 0.5))
            ny = float(spec.get("y", 0.9))

            widest = 0
            for ln in lines:
                try:
                    lw = int(draw.textlength(ln, font=font))
                except Exception:
                    lw = len(ln) * px_size // 2
                widest = max(widest, lw)

            pad_x, pad_y = int(px_size * 0.45), int(px_size * 0.28)
            # V1.2.1: unified placement -- safe margins plus environment-decor
            # avoidance (boards/windows registered in motion_state).
            bx0, by0 = resolve_text_placement(
                nx, ny,
                widest + 2 * pad_x, block_h + 2 * pad_y,
                width, height,
                blocked_rects=state.get("blocked_rects") or [],
                anchor=anchor_name,
            )
            x0, y0 = bx0 + pad_x, by0 + pad_y
            draw.rectangle(
                [bx0, by0, bx0 + widest + 2 * pad_x, by0 + block_h + 2 * pad_y],
                fill=(10, 12, 18, int(150 * opacity)),
            )
            for i, ln in enumerate(lines):
                draw.text((x0, y0 + i * line_h), ln,
                          fill=(color[0], color[1], color[2], int(255 * opacity)),
                          font=font)
            drew_any = True

        if not drew_any:
            return False
        image.paste(overlay, (0, 0), overlay)
        frame[:] = image.tobytes()
        return True

    _FONT_CANDIDATES = (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )

    @staticmethod
    def _load_font(px_size: int):
        """Best-effort scalable font; falls back to Pillow default."""
        if ImageFont is None:
            return None
        import os as _os
        for candidate in StickmanRenderer._FONT_CANDIDATES:
            if _os.path.exists(candidate):
                try:
                    return ImageFont.truetype(candidate, px_size)
                except Exception:
                    continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _effect_target_bounds(
        self,
        state: dict[str, Any],
        target: str,
        width: int,
        height: int,
    ) -> tuple[int, int, int] | None:
        """Resolve an effect target name to (cx, cy, radius) pixels."""
        if target in ("scene", ""):
            return None
        if target in state.get("named_characters", {}):
            cs = state["named_characters"][target]
            pose = cs.get("pose")
            if pose is not None:
                return int(pose.head_x), int((pose.head_y + pose.stickman_y) / 2), max(30, int(pose.body_length * 1.6))
            sp = cs["spec"]
            return int(sp.x * width), int(sp.y * height), int(min(width, height) * 0.10)
        if target in state.get("typed_objects", {}):
            ob = state["typed_objects"][target]
            scale = float(ob.get("scale", 1.0))
            return (
                int(float(ob.get("x", width * 0.5))),
                int(float(ob.get("y", height * 0.5))),
                int(min(width, height) * 0.05 * scale * 2.2),
            )
        return None

    def _draw_scene_effects(
        self,
        frame: bytearray,
        width: int,
        height: int,
        state: dict[str, Any],
        t: float,
        transform_x,
        transform_y,
    ) -> None:
        """Render active emphasis effects (highlight, spotlight, glow, ...)."""
        for spec in state.get("effect_specs", []):
            etype = str(spec.get("type", "highlight"))
            start = float(spec.get("start", 0.0))
            dur = float(spec.get("duration", 1.0))
            end = start + dur
            if t < start or t > end or dur <= 0:
                continue
            progress = 1.0 - ((end - t) / dur) ** 2  # ease-out
            params = spec.get("parameters") or {}
            accent = tuple(params.get("color", (255, 230, 120)))
            bounds = self._effect_target_bounds(
                state, str(spec.get("target", "scene")), width, height,
            )
            if bounds is None:
                cx, cy = width // 2, height // 2
                radius = int(min(width, height) * 0.32)
            else:
                cx, cy, radius = transform_x(bounds[0]), transform_y(bounds[1]), bounds[2]

            if etype == "highlight":
                pad = int(radius * (1.35 - 0.25 * progress))
                box_w = box_h = pad * 2
                self._draw_rect(frame, width, height, cx - pad, cy - pad,
                                box_w, box_h, accent, opacity=0.22 * progress)
            elif etype in ("spotlight", "glow"):
                rings = 3
                for i in range(rings, 0, -1):
                    rr = int(radius * (0.8 + i * 0.45))
                    self._draw_circle(frame, width, height, cx, cy, rr,
                                      accent, opacity=0.16 * progress / i)
            elif etype == "circle_highlight":
                thickness = max(2, int(radius * 0.08))
                steps = 40
                for s_i in range(steps):
                    ang = (s_i / steps) * math.tau
                    px = cx + int(math.cos(ang) * radius)
                    py = cy + int(math.sin(ang) * radius)
                    self._draw_circle(frame, width, height, px, py,
                                      thickness, accent, opacity=0.85 * progress)
            elif etype == "pulse":
                osc = 0.5 + 0.5 * math.sin(t * math.pi * 4)
                rr = int(radius * (1.1 + osc * 0.35))
                self._draw_circle(frame, width, height, cx, cy, rr,
                                  accent, opacity=0.20 * progress)

    def _obj_arrow(self, frame, w, h, cx, cy, b, color, op, t):
        shaft = int(b * 3.0)
        head = int(b * 1.1)
        x0 = cx - shaft // 2
        self._draw_line(frame, w, h, x0, cy, cx + shaft // 2 - head // 2, cy,
                        color, max(2, int(b * 0.35)), opacity=op)
        tip_x = cx + shaft // 2
        self._draw_line(frame, w, h, tip_x - head, cy - head, tip_x, cy, color, max(2, int(b * 0.35)), opacity=op)
        self._draw_line(frame, w, h, tip_x - head, cy + head, tip_x, cy, color, max(2, int(b * 0.35)), opacity=op)

    def _obj_check_mark(self, frame, w, h, cx, cy, b, color, op, t):
        green = (60, 200, 90)
        self._draw_line(frame, w, h, cx - b, cy, cx - int(b * 0.2), cy + b,
                        green, max(3, int(b * 0.5)), opacity=op)
        self._draw_line(frame, w, h, cx - int(b * 0.2), cy + b, cx + b, cy - b,
                        green, max(3, int(b * 0.5)), opacity=op)

    def _obj_cross_mark(self, frame, w, h, cx, cy, b, color, op, t):
        red = (220, 70, 70)
        self._draw_line(frame, w, h, cx - b, cy - b, cx + b, cy + b,
                        red, max(3, int(b * 0.5)), opacity=op)
        self._draw_line(frame, w, h, cx + b, cy - b, cx - b, cy + b,
                        red, max(3, int(b * 0.5)), opacity=op)

    def _obj_graph(self, frame, w, h, cx, cy, b, color, op, t):
        gw, gh = int(b * 5.0), int(b * 3.4)
        x0, y0 = cx - gw // 2, cy - gh // 2
        axis = (110, 110, 120)
        self._draw_rect(frame, w, h, x0, y0 + gh - max(2, int(b * 0.14)), gw, max(2, int(b * 0.14)), axis, opacity=op)
        self._draw_rect(frame, w, h, x0, y0, max(2, int(b * 0.14)), gh, axis, opacity=op)
        bar_w = max(3, int(gw / 6.5))
        heights = [0.35, 0.62, 0.48, 0.85]
        for i, frac in enumerate(heights):
            bx = x0 + int(bw_frac := (b * 0.5) + i * (gw / len(heights)))
            bh_ = int(gh * frac)
            self._draw_rect(frame, w, h, bx, y0 + gh - bh_, bar_w, bh_,
                            tuple(min(255, c + 30) for c in color), opacity=op)

    def _obj_brain(self, frame, w, h, cx, cy, b, color, op, t):
        radius = int(b * 2.0)
        pulse = 1.0 + 0.04 * math.sin(t * math.pi * 2)
        r = int(radius * pulse)
        self._draw_circle(frame, w, h, cx, cy, r, (255, 170, 190), opacity=op)
        squiggle = (150, 80, 110)
        for i in range(4):
            ang = i * math.pi / 2 + 0.4
            sx = cx + int(math.cos(ang) * r * 0.25)
            sy = cy + int(math.sin(ang) * r * 0.25)
            ex = cx + int(math.cos(ang) * r * 0.7)
            ey = cy + int(math.sin(ang) * r * 0.7)
            self._draw_line(frame, w, h, sx, sy, ex, ey, squiggle, max(2, int(b * 0.22)), opacity=op)

    def _obj_thought_bubble(self, frame, w, h, cx, cy, b, color, op, t):
        bob = int(math.sin(t * math.pi * 2 * 0.4) * b * 0.15)
        main_r = int(b * 2.2)
        self._draw_circle(frame, w, h, cx, cy + bob, main_r, (250, 250, 255), opacity=op)
        self._draw_circle(frame, w, h, cx, cy + bob, main_r, (160, 160, 175), opacity=op * 0.8)
        tail_r = max(1, int(b * 0.45))
        self._draw_circle(frame, w, h, cx - int(main_r * 0.9), cy + int(main_r * 0.9) + bob,
                          tail_r, (250, 250, 255), opacity=op)
        self._draw_circle(frame, w, h, cx - int(main_r * 1.3), cy + int(main_r * 1.5) + bob,
                          max(1, tail_r // 2), (250, 250, 255), opacity=op)

    def _obj_clock(self, frame, w, h, cx, cy, b, color, op, t):
        radius = int(b * 1.6)
        self._draw_circle(frame, w, h, cx, cy, radius, (90, 90, 90), opacity=op)
        face = max(1, radius - max(2, int(b * 0.22)))
        self._draw_circle(frame, w, h, cx, cy, face, (245, 245, 235), opacity=op)
        angle = math.pi * 2 * ((t * 0.8) % 1.0) - math.pi / 2
        hx = cx + int(math.cos(angle) * radius * 0.62)
        hy = cy + int(math.sin(angle) * radius * 0.62)
        self._draw_line(frame, w, h, cx, cy, hx, hy, (60, 60, 60), max(2, int(b * 0.16)), opacity=op)
        angle_m = math.pi * 2 * ((t * 0.11) % 1.0) - math.pi / 2
        mx = cx + int(math.cos(angle_m) * radius * 0.42)
        my = cy + int(math.sin(angle_m) * radius * 0.42)
        self._draw_line(frame, w, h, cx, cy, mx, my, (120, 60, 60), max(2, int(b * 0.12)), opacity=op)

    def _obj_phone(self, frame, w, h, cx, cy, b, color, op, t):
        pw, ph = int(b * 1.5), int(b * 2.8)
        x0, y0 = cx - pw // 2, cy - ph // 2
        self._draw_rect(frame, w, h, x0, y0, pw, ph, (30, 30, 34), opacity=op)
        inset = max(2, int(b * 0.18))
        self._draw_rect(frame, w, h, x0 + inset, y0 + inset,
                        max(2, pw - 2 * inset), max(2, ph - 2 * inset), color, opacity=op)

    def _obj_laptop(self, frame, w, h, cx, cy, b, color, op, t):
        scr_w, scr_h = int(b * 4.4), int(b * 2.8)
        x0, y0 = cx - scr_w // 2, cy - scr_h
        self._draw_rect(frame, w, h, x0, y0, scr_w, scr_h, (40, 44, 52), opacity=op)
        inset = max(2, int(b * 0.22))
        self._draw_rect(frame, w, h, x0 + inset, y0 + inset,
                        max(2, scr_w - 2 * inset), max(2, scr_h - 2 * inset), color, opacity=op)
        kb_y = y0 + scr_h
        self._draw_rect(frame, w, h, x0 - int(scr_w * 0.10), kb_y,
                        int(scr_w * 1.2), max(2, int(b * 0.5)), (70, 74, 84), opacity=op)

    def _obj_light_bulb(self, frame, w, h, cx, cy, b, color, op, t):
        glow = 0.35 + 0.15 * math.sin(t * math.pi)
        self._draw_circle(frame, w, h, cx, cy, int(b * 2.2), (255, 240, 160), opacity=op * glow)
        self._draw_circle(frame, w, h, cx, cy, int(b * 1.4), color, opacity=op)
        base_w, base_h = int(b * 1.0), int(b * 0.7)
        self._draw_rect(frame, w, h, cx - base_w // 2, cy + int(b * 1.2),
                        base_w, base_h, (150, 150, 150), opacity=op)

    def _draw_typed_object(
        self,
        frame: bytearray,
        width: int,
        height: int,
        transform_x,
        transform_y,
        obj: dict[str, Any],
        t: float,
    ) -> None:
        """Dispatch drawing of one procedural object by its declared type."""
        otype = str(obj.get("type", "generic"))
        cx = transform_x(int(float(obj.get("x", width * 0.5))))
        cy = transform_y(int(float(obj.get("y", height * 0.5))))
        scale = max(0.05, float(obj.get("scale", 1.0)))
        base = min(width, height) * 0.045 * scale
        opacity = max(0.0, min(1.0, float(obj.get("opacity", 1.0))))
        color = tuple(obj.get("color", (200, 150, 80)))

        drawer = getattr(self, "_obj_" + otype, None)
        if drawer is not None:
            drawer(frame, width, height, cx, cy, base, color, opacity, t)
        else:
            s = int(base * 1.6)
            self._draw_rect(frame, width, height, cx - s // 2, cy - s // 2, s, s, color, opacity=opacity)
            self._draw_circle(frame, width, height, cx, cy, max(1, int(s // 4)), (255, 255, 255), opacity=opacity)

    # -- individual procedural shapes ----------------------------------------

    def _obj_book(self, frame, w, h, cx, cy, b, color, op, t):
        bw, bh = int(b * 3.2), int(b * 2.1)
        x0, y0 = cx - bw // 2, cy - bh // 2
        self._draw_rect(frame, w, h, x0, y0, bw, bh, color, opacity=op)
        spine = x0 + int(bw * 0.12)
        self._draw_rect(frame, w, h, spine - max(1, int(b * 0.15)), y0, max(2, int(b * 0.3)), bh, (255, 255, 255), opacity=op * 0.55)

    def _obj_stack_of_books(self, frame, w, h, cx, cy, b, color, op, t):
        shades = [color, tuple(min(255, c + 40) for c in color), tuple(max(0, c - 40) for c in color)]
        for i in range(3):
            bw = int(b * (3.4 - i * 0.35))
            bh = int(b * 0.85)
            x0 = cx - bw // 2 + (i % 2) * int(b * 0.25)
            y0 = cy + b - bh * (i + 1) - i * 2
            self._draw_rect(frame, w, h, x0, y0, bw, bh, shades[i % 3], opacity=op)

    def _obj_desk(self, frame, w, h, cx, cy, b, color, op, t):
        top_w, top_h = int(b * 7.0), int(b * 0.9)
        leg_h = int(b * 3.2)
        x0 = cx - top_w // 2
        y0 = cy - top_h // 2
        self._draw_rect(frame, w, h, x0, y0, top_w, top_h, color, opacity=op)
        dark = tuple(max(0, c - 50) for c in color)
        for lx in (x0 + int(top_w * 0.08), x0 + top_w - int(top_w * 0.14)):
            self._draw_rect(frame, w, h, lx, y0 + top_h, int(b * 0.45), leg_h, dark, opacity=op)

    def _obj_chair(self, frame, w, h, cx, cy, b, color, op, t):
        seat_w, seat_h = int(b * 2.8), int(b * 0.7)
        back_h = int(b * 2.6)
        x0 = cx - seat_w // 2
        y0 = cy
        lighter = tuple(min(255, c + 20) for c in color)
        self._draw_rect(frame, w, h, x0, y0 - back_h, seat_w, back_h, lighter, opacity=op)
        self._draw_rect(frame, w, h, x0, y0, seat_w, seat_h, color, opacity=op)
        dark = tuple(max(0, c - 50) for c in color)
        for lx in (x0 + 2, x0 + seat_w - int(b * 0.45)):
            self._draw_rect(frame, w, h, lx, y0 + seat_h, int(b * 0.4), int(b * 2.4), dark, opacity=op)

    def _draw_environment_layers(
        self,
        frame: bytearray,
        width: int,
        height: int,
        transform_x,
        transform_y,
        env: dict[str, Any],
        accent: tuple[int, int, int],
        motion_state: dict[str, Any] | None = None,
    ) -> None:
        """Draw light interior decor so indoor scenes do not feel empty.

        V1.2.1: large decor rects (boards, windows) are registered in
        ``motion_state["blocked_rects"]`` (screen pixels, reset every frame)
        so text placement can avoid them, and classroom boards host the scene
        headline -- or chalk marks -- so they are never an empty container.
        """
        env_type = str(env.get("type", "workspace"))
        bg = tuple(env.get("background_color", (200, 200, 200)))
        line_color = (
            max(0, bg[0] - 30),
            max(0, bg[1] - 30),
            max(0, bg[2] - 30),
        )
        state = motion_state if isinstance(motion_state, dict) else None
        blocked_rects: list[tuple[int, int, int, int]] | None = None
        if state is not None:
            blocked_rects = []
            state["blocked_rects"] = blocked_rects

        def _block_rect(px0: int, py0: int, px1: int, py1: int) -> None:
            if blocked_rects is not None:
                blocked_rects.append(
                    (min(px0, px1), min(py0, py1), max(px0, px1), max(py0, py1))
                )

        wall_line = transform_y(int(height * 0.28))
        self._draw_rect(frame, width, height, 0, wall_line, width, max(2, height // 240), line_color)

        if env_type == "classroom":
            board_x = transform_x(int(width * 0.12))
            board_y = transform_y(int(height * 0.08))
            board_w = int(width * 0.42)
            board_h = int(height * 0.16)
            self._draw_rect(frame, width, height, board_x, board_y, board_w, board_h, (40, 60, 50))
            self._draw_rect(
                frame, width, height, board_x + 6, board_y + 6,
                max(4, board_w - 12), max(4, board_h - 12), accent,
            )
            _block_rect(board_x, board_y, board_x + board_w, board_y + board_h)
            self._decorate_classroom_board(
                frame, width, height, state,
                board_x, board_y, board_w, board_h, accent,
            )
        elif env_type == "bedroom":
            win_x = transform_x(int(width * 0.68))
            win_y = transform_y(int(height * 0.06))
            win_w = int(width * 0.20)
            win_h = int(height * 0.15)
            self._draw_rect(frame, width, height, win_x, win_y, win_w, win_h, accent)
            mid = win_x + win_w // 2
            self._draw_rect(frame, width, height, mid - 1, win_y, 3, win_h, (90, 90, 90))
            _block_rect(win_x, win_y, win_x + win_w, win_y + win_h)
        elif env_type == "abstract_info_space":
            dot_r = max(1, int(min(width, height) * 0.006))
            for i in range(12):
                fx = ((i * 37) % 100) / 100.0
                fy = ((i * 61) % 55) / 100.0 + 0.05
                self._draw_circle(
                    frame, width, height,
                    transform_x(int(fx * width)), transform_y(int(fy * height)),
                    dot_r, accent, opacity=0.5,
                )

    @staticmethod
    def _chalk_color(accent: tuple[int, int, int]) -> tuple[int, int, int]:
        """Pick a chalk color with contrast against the board's accent fill."""
        lum = 0.299 * accent[0] + 0.587 * accent[1] + 0.114 * accent[2]
        return (40, 60, 50) if lum >= 140 else (245, 245, 235)

    def _decorate_classroom_board(
        self,
        frame: bytearray,
        width: int,
        height: int,
        state: dict[str, Any] | None,
        board_x: int,
        board_y: int,
        board_w: int,
        board_h: int,
        accent: tuple[int, int, int],
    ) -> None:
        """Host the scene headline inside the board, or draw chalk marks.

        Reusable V1.2.1 title rule: a headline-size text spec addressed at the
        board region is rendered as chalk writing inside the board and skipped
        by the regular text pass (``state["_board_hosted"]``). Boards with no
        headline get faint chalk lines so they are never an empty container.
        """
        chalk = self._chalk_color(accent)
        specs = ((state or {}).get("text_specs") or [])
        hosted = (state or {}).setdefault("_board_hosted", set())
        hosted.clear()
        if Image is None or ImageDraw is None:
            return
        inner_w = max(10, board_w - 24)
        for idx, spec in enumerate(specs):
            if str(spec.get("size", "")) != "headline":
                continue
            sx = float(spec.get("x", 0.5))
            sy = float(spec.get("y", 0.5))
            if not (0.10 <= sx <= 0.56 and 0.06 <= sy <= 0.26):
                continue  # headline is not addressed to the board
            text = str(spec.get("text", "")).strip()
            if not text:
                break
            measurer = ImageDraw.Draw(Image.new("RGB", (8, 8)))
            px_size = max(10, int(min(width, height) * 0.030 * 2.0))
            font = self._load_font(px_size)
            if font is None:
                return
            try:
                text_w = int(measurer.textlength(text, font=font))
            except Exception:
                text_w = len(text) * px_size * 0.55
            while text_w > inner_w and px_size > 10:
                px_size = max(10, int(px_size * 0.9))
                font = self._load_font(px_size)
                if font is None:
                    return
                try:
                    text_w = int(measurer.textlength(text, font=font))
                except Exception:
                    text_w = len(text) * px_size * 0.55
            line_h = int(px_size * 1.32)
            if line_h > board_h - 12:
                break  # does not fit the board; fall through to chalk marks
            cx = board_x + board_w // 2
            cy = board_y + board_h // 2
            self._draw_text_lines_on_frame(
                frame, width, height, [text], font, px_size,
                cx - text_w // 2, cy - line_h // 2, chalk,
            )
            hosted.add(idx)
            return
        if hosted:
            return
        # Fallback: faint chalk lines so the board is never an empty box.
        self._draw_line(
            frame, width, height,
            board_x + int(board_w * 0.12), board_y + int(board_h * 0.38),
            board_x + int(board_w * 0.62), board_y + int(board_h * 0.38),
            chalk, 2, opacity=0.45,
        )
        self._draw_line(
            frame, width, height,
            board_x + int(board_w * 0.12), board_y + int(board_h * 0.62),
            board_x + int(board_w * 0.48), board_y + int(board_h * 0.62),
            chalk, 2, opacity=0.35,
        )

    def _draw_text_lines_on_frame(
        self,
        frame: bytearray,
        width: int,
        height: int,
        lines: list[str],
        font: Any,
        px_size: int,
        x0: int,
        y0: int,
        color: tuple[int, int, int],
    ) -> None:
        """Draw opaque text lines directly onto the RGB frame buffer."""
        image = Image.frombytes("RGB", (width, height), bytes(frame))
        draw = ImageDraw.Draw(image)
        line_h = int(px_size * 1.32)
        for i, ln in enumerate(lines):
            draw.text((x0, y0 + i * line_h), ln, fill=color, font=font)
        frame[:] = image.tobytes()

    def _draw_named_character(
        self,
        frame: bytearray,
        width: int,
        height: int,
        transform_x,
        transform_y,
        cstate: dict[str, Any],
    ) -> None:
        """Render one composed character from its resolved pose."""
        if not cstate.get("visible", True):
            return
        opacity = max(0.0, min(1.0, float(cstate.get("opacity", 1.0))))
        if opacity <= 0.01:
            return
        pose = cstate.get("pose")
        if pose is None:
            return
        color = getattr(pose, "color", (255, 255, 255))
        thick = max(1, int(getattr(pose, "line_thickness", 3)))
        self._draw_circle(frame, width, height,
                          transform_x(pose.head_x), transform_y(pose.head_y),
                          max(1, int(pose.head_radius)), color, opacity=opacity)
        self._draw_line(frame, width, height,
                        transform_x(pose.stickman_x), transform_y(pose.neck_y),
                        transform_x(pose.stickman_x), transform_y(pose.hip_y),
                        color, thick, opacity=opacity)
        self._draw_line(frame, width, height,
                        transform_x(pose.stickman_x), transform_y(pose.shoulder_y),
                        transform_x(pose.left_arm_x), transform_y(pose.left_arm_y),
                        color, thick, opacity=opacity)
        self._draw_line(frame, width, height,
                        transform_x(pose.stickman_x), transform_y(pose.shoulder_y),
                        transform_x(pose.right_arm_x), transform_y(pose.right_arm_y),
                        color, thick, opacity=opacity)
        self._draw_line(frame, width, height,
                        transform_x(pose.stickman_x), transform_y(pose.hip_y),
                        transform_x(pose.left_leg_x), transform_y(pose.left_leg_y),
                        color, thick, opacity=opacity)
        self._draw_line(frame, width, height,
                        transform_x(pose.stickman_x), transform_y(pose.hip_y),
                        transform_x(pose.right_leg_x), transform_y(pose.right_leg_y),
                        color, thick, opacity=opacity)

    def _resolve_named_characters(
        self,
        state: dict[str, Any],
        t: float,
        duration: float,
        width: int,
        height: int,
    ) -> None:
        """Compute per-frame poses for every composed (named) character."""
        for cstate in state.get("named_characters", {}).values():
            spec = cstate["spec"]
            mini_state: dict[str, Any] = {
                "camera_zoom": state.get("camera_zoom", 1.0),
                "camera_pan_x": state.get("camera_pan_x", 0),
                "camera_pan_y": state.get("camera_pan_y", 0),
                "character_x": cstate.get("x") if cstate.get("x") is not None else spec.x * width,
                "character_y": cstate.get("y") if cstate.get("y") is not None else spec.y * height,
                "character_scale": cstate.get("scale", 1.0),
                "character_opacity": cstate.get("opacity", 1.0),
                "character_visible": cstate.get("visible", True),
            }
            pose = self._compute_pose(
                spec.pose,
                t,
                duration,
                width,
                height,
                camera_instructions="",
                motion_state=mini_state,
                emotion=spec.emotion,
            )
            pose.color = spec.effective_color
            cstate["pose"] = pose
            cstate["opacity"] = mini_state["character_opacity"]
            cstate["visible"] = bool(mini_state["character_visible"])

    def _apply_camera_pattern(
        self,
        state: dict[str, Any],
        spec: dict[str, Any],
        current_time: float,
        duration: float,
        width: int,
        height: int,
    ) -> None:
        """Derive camera zoom/pan from a declarative CameraSpec."""
        pattern = str(spec.get("pattern", "static"))
        cam_duration = float(spec.get("duration") or duration) or duration
        easing = str(spec.get("easing", "ease_in_out"))
        p = clamp(current_time / cam_duration if cam_duration > 0 else 1.0)
        eased = apply_easing(p, easing)

        def _target_pos() -> tuple[float, float] | None:
            name = str(spec.get("focus_target") or "")
            if name in state.get("named_characters", {}):
                cs = state["named_characters"][name]
                sp = cs["spec"]
                return (
                    cs["x"] if cs.get("x") is not None else sp.x * width,
                    cs["y"] if cs.get("y") is not None else sp.y * height,
                )
            if name in state.get("typed_objects", {}):
                ob = state["typed_objects"][name]
                return float(ob.get("x", width * 0.5)), float(ob.get("y", height * 0.5))
            return None

        if pattern == "slow_zoom_in":
            state["camera_zoom"] = interpolate_value(1.0, 1.18, eased)
        elif pattern == "slow_zoom_out":
            state["camera_zoom"] = interpolate_value(1.18, 1.0, eased)
        elif pattern == "pan_left":
            state["camera_pan_x"] = int(
                interpolate_value(PAN_RANGE_RATIO, -PAN_RANGE_RATIO, eased) * width
            )
        elif pattern == "pan_right":
            state["camera_pan_x"] = int(
                interpolate_value(-PAN_RANGE_RATIO, PAN_RANGE_RATIO, eased) * width
            )
        elif pattern == "pan_up":
            state["camera_pan_y"] = int(
                interpolate_value(PAN_RANGE_RATIO, -PAN_RANGE_RATIO, eased) * height
            )
        elif pattern == "pan_down":
            state["camera_pan_y"] = int(
                interpolate_value(-PAN_RANGE_RATIO, PAN_RANGE_RATIO, eased) * height
            )
        elif pattern == "zoom_then_pan":
            half = 0.5
            if p <= half:
                z_eased = apply_easing(p / half, easing)
                state["camera_zoom"] = interpolate_value(1.0, 1.12, z_eased)
            else:
                p_eased = apply_easing((p - half) / half, easing)
                state["camera_zoom"] = 1.12
                state["camera_pan_x"] = int(
                    interpolate_value(0.0, ZOOM_THEN_PAN_RANGE_RATIO, p_eased) * width
                )
        elif pattern in ("focus_on_character", "focus_on_object"):
            target = _target_pos()
            end_zoom = 1.35
            if target is not None:
                tx, ty = target
                end_pan_x = (width / 2.0 - tx) * end_zoom
                end_pan_y = (height / 2.0 - ty) * end_zoom
            else:
                end_pan_x = 0.0
                end_pan_y = 0.0
            # V1.2.1 safe-area clamp: the focus target stays centered by
            # construction, so only OTHER named characters need protection:
            # clamp the pan so each bystander remains inside the render-safe
            # region at max zoom. Scenes without bystanders keep the exact
            # centered-target contract (no clamping at all).
            focus_name = str(spec.get("focus_target") or "")
            margin_x = SAFE_MARGIN_RATIO * width
            margin_y = SAFE_MARGIN_RATIO * height
            lo_x, hi_x = -float("inf"), float("inf")
            lo_y, hi_y = -float("inf"), float("inf")
            for cname, cstate in (state.get("named_characters") or {}).items():
                if cname == focus_name:
                    continue
                cspec = cstate.get("spec")
                cx = cstate.get("x")
                if cx is None and cspec is not None:
                    cx = float(getattr(cspec, "x", 0.5)) * width
                cy = cstate.get("y")
                if cy is None and cspec is not None:
                    cy = float(getattr(cspec, "y", 0.75)) * height
                if cx is not None:
                    base = (float(cx) - width / 2.0) * end_zoom + width / 2.0
                    lo_x = max(lo_x, margin_x - base)
                    hi_x = min(hi_x, width - margin_x - base)
                if cy is not None:
                    base = (float(cy) - height / 2.0) * end_zoom + height / 2.0
                    lo_y = max(lo_y, margin_y - base)
                    hi_y = min(hi_y, height - margin_y - base)
            if lo_x <= hi_x:
                end_pan_x = max(lo_x, min(hi_x, end_pan_x))
            if lo_y <= hi_y:
                end_pan_y = max(lo_y, min(hi_y, end_pan_y))
            state["camera_zoom"] = interpolate_value(1.0, end_zoom, eased)
            state["camera_pan_x"] = int(interpolate_value(0.0, end_pan_x, eased))
            state["camera_pan_y"] = int(interpolate_value(0.0, end_pan_y, eased))

    def _draw_rect(
        self,
        frame: bytearray,
        width: int,
        height: int,
        x: int,
        y: int,
        w: int,
        h: int,
        color: tuple[int, int, int],
        opacity: float = 1.0,
    ) -> None:
        """Draw a filled rectangle."""
        r, g, b = color
        x, y, w, h = int(x), int(y), int(w), int(h)
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(0, min(w, width - x))
        h = max(0, min(h, height - y))
        opacity = max(0.0, min(1.0, opacity))
        
        for row in range(y, y + h):
            base = row * width * 3 + x * 3
            for col in range(w):
                idx = base + col * 3
                self._blend_pixel(frame, idx, (r, g, b), opacity)

    def _draw_circle(
        self,
        frame: bytearray,
        width: int,
        height: int,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
        opacity: float = 1.0,
    ) -> None:
        """Draw a filled circle using midpoint circle algorithm."""
        r, g, b = color
        cx, cy, radius = int(cx), int(cy), int(radius)
        cx = max(0, min(cx, width - 1))
        cy = max(0, min(cy, height - 1))
        radius = max(1, radius)
        opacity = max(0.0, min(1.0, opacity))
        
        # Bounding box
        x_min = max(0, cx - radius)
        x_max = min(width - 1, cx + radius)
        y_min = max(0, cy - radius)
        y_max = min(height - 1, cy + radius)
        
        r_squared = radius * radius
        
        for y in range(y_min, y_max + 1):
            dy = y - cy
            dy_squared = dy * dy
            # Calculate x range for this y
            dx_max = int(math.sqrt(max(0, r_squared - dy_squared)))
            x_start = max(x_min, cx - dx_max)
            x_end = min(x_max, cx + dx_max)
            
            base = y * width * 3 + x_start * 3
            for x in range(x_start, x_end + 1):
                idx = base + (x - x_start) * 3
                self._blend_pixel(frame, idx, (r, g, b), opacity)

    def _draw_line(
        self,
        frame: bytearray,
        width: int,
        height: int,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: tuple[int, int, int],
        thickness: int = 1,
        opacity: float = 1.0,
    ) -> None:
        """Draw a line using Bresenham's algorithm with thickness."""
        r, g, b = color
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        opacity = max(0.0, min(1.0, opacity))
        
        # Bresenham's line algorithm
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        
        x, y = x0, y0
        
        while True:
            # Draw thickness around the point
            for ty in range(-thickness // 2, thickness // 2 + 1):
                for tx in range(-thickness // 2, thickness // 2 + 1):
                    px, py = x + tx, y + ty
                    if 0 <= px < width and 0 <= py < height:
                        idx = (py * width + px) * 3
                        self._blend_pixel(frame, idx, (r, g, b), opacity)
            
            if x == x1 and y == y1:
                break
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    @staticmethod
    def _blend_pixel(frame: bytearray, idx: int, color: tuple[int, int, int], opacity: float) -> None:
        """Alpha blend a color into the RGB frame buffer."""
        if opacity >= 1.0:
            frame[idx] = color[0]
            frame[idx + 1] = color[1]
            frame[idx + 2] = color[2]
            return
        if opacity <= 0.0:
            return
        existing_r = frame[idx]
        existing_g = frame[idx + 1]
        existing_b = frame[idx + 2]
        frame[idx] = int(existing_r * (1.0 - opacity) + color[0] * opacity)
        frame[idx + 1] = int(existing_g * (1.0 - opacity) + color[1] * opacity)
        frame[idx + 2] = int(existing_b * (1.0 - opacity) + color[2] * opacity)

    def _draw_caption_overlay(
        self,
        frame: bytearray,
        width: int,
        height: int,
        caption: str,
        opacity: float = 1.0,
        scale: float = 1.0,
    ) -> None:
        """Render a simple caption overlay using Pillow when available."""
        if Image is None or ImageDraw is None or ImageFont is None:
            return
        opacity = max(0.0, min(1.0, opacity))
        if opacity <= 0.0:
            return

        try:
            image = Image.frombytes("RGB", (width, height), bytes(frame))
            draw = ImageDraw.Draw(image)
            caption_text = " ".join(str(caption).split())[:60]
            font_size = max(12, int(18 * scale))
            font = ImageFont.load_default()
            text_bbox = draw.textbbox((0, 0), caption_text, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
            padding_x = max(8, int(12 * scale))
            padding_y = max(4, int(8 * scale))
            box_w = text_w + padding_x * 2
            box_h = text_h + padding_y * 2
            x = max(8, (width - box_w) // 2)
            y = height - box_h - max(12, int(18 * scale))
            overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, int(160 * opacity)))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle([0, 0, box_w - 1, box_h - 1], outline=(255, 255, 255, int(200 * opacity)))
            overlay_draw.text((padding_x, padding_y), caption_text, fill=(255, 255, 255, int(255 * opacity)), font=font)
            image.paste(overlay, (x, y), overlay)
            updated = image.tobytes()
            frame[:] = updated
        except Exception:
            return


def render_stickman_job(
    job_spec: RenderJobSpec,
    config: RenderConfig | None = None,
) -> dict[str, Any]:
    """Render a single RenderJobSpec as an animated stickman scene.
    
    This is the main entry point for the animated scene renderer.
    
    Args:
        job_spec: The render job specification
        config: Optional render configuration. If not provided, uses defaults.
        
    Returns:
        Dictionary with render result information
    """
    if config is None:
        config = RenderConfig()
    
    # Convert RenderJobSpec to dict
    job_dict = job_spec.to_dict()
    
    # Force render_type to indicate stickman animation
    job_dict["render_type"] = "stickman_animation"
    
    # Create render request
    request = RenderRequest(
        job=job_dict,
        render_config=config,
        resolved_assets=[],
        resolved_characters=[],
    )
    
    # Create and use stickman renderer
    renderer = StickmanRenderer(execute_enabled=True)
    return renderer.render(request)



def _text_opacity(spec, t, scene_duration):
    """Time-dependent opacity honoring appear_at / fade_in / fade_out."""
    base = max(0.0, min(1.0, float(spec.get("opacity", 1.0))))
    appear_at = float(spec.get("appear_at", 0.0))
    if t < appear_at:
        return 0.0
    opacity = base
    fade_in = float(spec.get("fade_in", 0.0))
    if fade_in > 0:
        opacity *= max(0.0, min(1.0, (t - appear_at) / fade_in))
    dur = float(spec.get("duration", 0.0))
    end_time = appear_at + dur if dur > 0 else scene_duration
    fade_out = float(spec.get("fade_out", 0.0))
    if fade_out > 0 and t > end_time - fade_out:
        opacity *= max(0.0, min(1.0, (end_time - t) / fade_out))
    return opacity
