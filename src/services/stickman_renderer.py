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
from src.models.content_package import RenderConfig, RenderJobSpec
from src.services.ffmpeg_renderer import FFmpegRenderer


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
        
        # Build output path
        output_path = self.ffmpeg_renderer._build_output_path(config, job.get("job_id", "unknown"))
        
        # Validate output path
        self.ffmpeg_renderer._validate_output_path(output_path)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if not self.execute_enabled:
            # Return command info only
            return {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "command_built",
                "output_reference": output_path,
                "duration_seconds": int(job.get("duration_seconds", 0)),
                "command": "stickman procedural generation (not executed)",
                "ffmpeg_available": self.is_available(),
            }
        
        # Check FFmpeg availability
        if not self.is_available():
            return {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": "FFmpeg is not available on PATH",
            }
        
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

        video_target_path = output_path
        temp_video_path = None
        if audio_request:
            temp_video_path = output_path + ".temp_video.mp4"
            video_target_path = temp_video_path

        try:
            # Generate and encode animation
            self._generate_animation(job, config, video_target_path)
            
            # Verify video output
            if not os.path.exists(video_target_path):
                return {
                    "job_id": str(job.get("job_id", "unknown")),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": int(job.get("duration_seconds", 0)),
                    "error": f"Video output file not created: {video_target_path}",
                }

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
                return {
                    "job_id": str(job.get("job_id", "unknown")),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": int(job.get("duration_seconds", 0)),
                    "error": f"Output file too small: {file_size} bytes",
                }
            
            return {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "completed",
                "output_reference": output_path,
                "duration_seconds": int(job.get("duration_seconds", 0)),
                "file_size_bytes": file_size,
            }
            
        except Exception as e:
            return {
                "job_id": str(job.get("job_id", "unknown")),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": f"Stickman rendering failed: {str(e)}",
            }

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
        head_radius = int(scale * 0.15)
        body_length = int(scale * 0.5)
        leg_length = int(scale * 0.45)
        arm_length = int(scale * 0.4)
        line_thickness = max(2, int(scale * 0.02))
        color = (255, 255, 255)

        # Character horizontal position
        progress = t / duration if duration > 0 else 0
        if action in ("walk", "run"):
            # Walk/run: move left-to-center as before
            stickman_x = int(width * 0.15 + width * 0.5 * progress)
        else:
            # Non-locomotion actions: stay centered
            stickman_x = int(width * 0.5)
        stickman_y = ground_y - 10  # Feet on ground

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
            color=color,
        )

    def _generate_animation(self, job: dict[str, Any], config: RenderConfig, output_path: str) -> None:
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
            frame_size = width * height * 3  # RGB24
            
            for frame_idx in range(total_frames):
                t = frame_idx / fps  # Time in seconds
                pose = self._compute_pose(action, t, duration, width, height)
                frame_data = self._generate_frame(width, height, t, duration, frame_idx, total_frames, pose)
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

        # Fill background (light blue sky)
        bg_r, bg_g, bg_b = 135, 206, 235
        for i in range(0, len(frame), 3):
            frame[i] = bg_r
            frame[i + 1] = bg_g
            frame[i + 2] = bg_b

        # Draw ground (green)
        ground_y = int(height * 0.75)
        ground_color = (34, 139, 34)  # Forest green
        self._draw_rect(frame, width, height, 0, ground_y, width, height - ground_y, ground_color)

        # Draw sun (yellow circle in top right)
        sun_x = int(width * 0.85)
        sun_y = int(height * 0.15)
        sun_radius = int(min(width, height) * 0.05)
        self._draw_circle(frame, width, height, sun_x, sun_y, sun_radius, (255, 255, 0))

        # Draw head (circle)
        self._draw_circle(frame, width, height, pose.head_x, pose.head_y, pose.head_radius, pose.color)

        # Body (line from neck to hip)
        self._draw_line(
            frame, width, height,
            pose.stickman_x, pose.neck_y,
            pose.stickman_x, pose.hip_y,
            pose.color, pose.line_thickness,
        )

        # Arms (from shoulders)
        self._draw_line(
            frame, width, height,
            pose.stickman_x, pose.shoulder_y,
            pose.left_arm_x, pose.left_arm_y,
            pose.color, pose.line_thickness,
        )
        self._draw_line(
            frame, width, height,
            pose.stickman_x, pose.shoulder_y,
            pose.right_arm_x, pose.right_arm_y,
            pose.color, pose.line_thickness,
        )

        # Legs (from hips)
        self._draw_line(
            frame, width, height,
            pose.stickman_x, pose.hip_y,
            pose.left_leg_x, pose.left_leg_y,
            pose.color, pose.line_thickness,
        )
        self._draw_line(
            frame, width, height,
            pose.stickman_x, pose.hip_y,
            pose.right_leg_x, pose.right_leg_y,
            pose.color, pose.line_thickness,
        )

        return bytes(frame)

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
    ) -> None:
        """Draw a filled rectangle."""
        r, g, b = color
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(0, min(w, width - x))
        h = max(0, min(h, height - y))
        
        for row in range(y, y + h):
            base = row * width * 3 + x * 3
            for col in range(w):
                idx = base + col * 3
                frame[idx] = r
                frame[idx + 1] = g
                frame[idx + 2] = b

    def _draw_circle(
        self,
        frame: bytearray,
        width: int,
        height: int,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a filled circle using midpoint circle algorithm."""
        r, g, b = color
        cx = max(0, min(cx, width - 1))
        cy = max(0, min(cy, height - 1))
        radius = max(1, radius)
        
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
                frame[idx] = r
                frame[idx + 1] = g
                frame[idx + 2] = b

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
    ) -> None:
        """Draw a line using Bresenham's algorithm with thickness."""
        r, g, b = color
        
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
                        frame[idx] = r
                        frame[idx + 1] = g
                        frame[idx + 2] = b
            
            if x == x1 and y == y1:
                break
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy


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