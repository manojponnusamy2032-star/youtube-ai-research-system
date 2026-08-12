"""FFmpeg renderer service foundation.

Provides FFmpeg command building and availability detection without execution.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from src.agents.render_job_executor import RenderRequest
from src.models.content_package import RenderConfig


class FFmpegRenderer:
    """FFmpeg renderer service that builds commands without executing them."""

    def __init__(self, asset_root: str = "assets", execute_enabled: bool = False) -> None:
        """Initialize the FFmpeg renderer.
        
        Args:
            asset_root: Root directory for assets
            execute_enabled: If True, render() will execute FFmpeg. Default: False
        """
        self.asset_root = asset_root
        self.execute_enabled = execute_enabled

    def is_available(self) -> bool:
        """Check if FFmpeg executable is available on PATH.
        
        Returns:
            True if ffmpeg is found, False otherwise
        """
        return shutil.which("ffmpeg") is not None

    def build_command(self, request: RenderRequest, output_path: str) -> list[str]:
        """Build a deterministic FFmpeg command for a render request.
        
        Args:
            request: Render request containing job and configuration
            output_path: Full path for the output file
            
        Returns:
            List of FFmpeg command arguments
            
        Raises:
            ValueError: If output_path is unsafe or configuration is invalid
        """
        config = request.render_config
        
        # Validate configuration
        self._validate_config(config)
        
        # Validate and sanitize output path
        self._validate_output_path(output_path)
        
        # Build command
        command = [
            "ffmpeg",
            "-y",  # Overwrite output files
            "-f", "lavfi",  # Use lavfi input format
            "-i", f"color=c=black:s={config.width}x{config.height}:r={config.fps}:d=1",  # 1 second placeholder
            "-c:v", config.video_codec,
            "-preset", "fast",
            "-crf", "23",
            "-c:a", config.audio_format,
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            "-movflags", "+faststart",
            output_path,
        ]
        
        return command

    def render(self, request: RenderRequest) -> dict[str, Any]:
        """Render a job using FFmpeg if execution is enabled.
        
        If execute_enabled is False (default), returns command information only.
        If execute_enabled is True, executes FFmpeg via subprocess.
        
        Args:
            request: Render request containing job and configuration
            
        Returns:
            Dictionary with render result information
        """
        config = request.render_config
        
        # Build output path from config
        output_path = self._build_output_path(config, request.job.get("job_id", "unknown"))
        
        try:
            command = self.build_command(request, output_path)
            
            # If execution is not enabled, return command information only
            if not self.execute_enabled:
                return {
                    "job_id": str(request.job["job_id"]),
                    "status": "command_built",
                    "output_reference": output_path,
                    "duration_seconds": int(request.job.get("duration_seconds", 0)),
                    "command": command,
                    "ffmpeg_available": self.is_available(),
                    "message": "FFmpeg execution not yet implemented",
                }
            
            # Execute FFmpeg
            return self._execute_ffmpeg(command, output_path, request)
            
        except Exception as e:
            return {
                "job_id": str(request.job.get("job_id", "unknown")),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": str(e),
            }
    
    def _execute_ffmpeg(self, command: list[str], output_path: str, request: RenderRequest) -> dict[str, Any]:
        """Execute FFmpeg command safely.
        
        Args:
            command: FFmpeg command as list of arguments
            output_path: Expected output file path
            request: Original render request
            
        Returns:
            Dictionary with execution result
        """
        # Check if FFmpeg is available
        if not self.is_available():
            return {
                "job_id": str(request.job["job_id"]),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": "FFmpeg is not available on PATH",
                "command": command,
            }
        
        try:
            # Execute FFmpeg with timeout
            start_time = time.time()
            result = subprocess.run(
                command,
                shell=False,  # Never use shell=True for security
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            elapsed_time = time.time() - start_time
            
            # Check if process succeeded
            if result.returncode != 0:
                return {
                    "job_id": str(request.job["job_id"]),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": int(request.job.get("duration_seconds", 0)),
                    "error": f"FFmpeg failed with return code {result.returncode}",
                    "command": command,
                    "stderr": result.stderr[:500] if result.stderr else "",  # Limit log size
                }
            
            # Verify output file exists
            if not os.path.exists(output_path):
                return {
                    "job_id": str(request.job["job_id"]),
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": int(request.job.get("duration_seconds", 0)),
                    "error": f"FFmpeg completed but output file not found: {output_path}",
                    "command": command,
                }
            
            # Success
            return {
                "job_id": str(request.job["job_id"]),
                "status": "completed",
                "output_reference": output_path,
                "duration_seconds": int(request.job.get("duration_seconds", 0)),
                "command": command,
                "return_code": result.returncode,
                "execution_time_seconds": round(elapsed_time, 2),
            }
            
        except subprocess.TimeoutExpired:
            return {
                "job_id": str(request.job["job_id"]),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": "FFmpeg execution timed out after 300 seconds",
                "command": command,
            }
        except Exception as e:
            return {
                "job_id": str(request.job["job_id"]),
                "status": "failed",
                "output_reference": None,
                "duration_seconds": 0,
                "error": f"FFmpeg execution failed: {str(e)}",
                "command": command,
            }
    
    def _find_scene_input(self, request: RenderRequest) -> str | None:
        """Find a usable visual input for the scene from resolved assets.
        
        Args:
            request: Render request containing resolved assets
            
        Returns:
            Path to input file if found, None otherwise
        """
        # Check resolved assets first (images, videos)
        for asset_path in request.resolved_assets:
            if os.path.exists(asset_path):
                # Support common image formats
                if asset_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    return asset_path
                # Support common video formats
                if asset_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    return asset_path
        
        # Check resolved characters (typically images)
        for char_path in request.resolved_characters:
            if os.path.exists(char_path):
                if char_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                    return char_path
        
        return None
    
    def _validate_render_type(self, render_type: str) -> None:
        """Validate render type is supported.
        
        Args:
            render_type: Render type string from job
            
        Raises:
            ValueError: If render type is not supported
        """
        supported_types = {
            "host_footage",
            "b-roll",
            "screen_capture",
            "comparison",
            "end_screen",
        }
        
        if render_type not in supported_types:
            raise ValueError(f"Unsupported render type: {render_type}")
    
    def _build_scene_command(self, request: RenderRequest, output_path: str) -> list[str]:
        """Build FFmpeg command for scene rendering with asset or placeholder.
        
        Args:
            request: Render request containing job and configuration
            output_path: Full path for the output file
            
        Returns:
            List of FFmpeg command arguments
        """
        config = request.render_config
        job = request.job
        
        # Validate duration
        duration = int(job.get("duration_seconds", 0))
        if duration < 0:
            raise ValueError(f"Invalid duration: {duration}")
        
        # Validate render type
        render_type = str(job.get("render_type", "host_footage"))
        self._validate_render_type(render_type)
        
        # Try to find a visual asset
        input_path = self._find_scene_input(request)
        
        if input_path:
            # Use the actual asset as input
            if input_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                # Image input - loop for duration
                command = [
                    "ffmpeg",
                    "-y",
                    "-loop", "1",
                    "-i", input_path,
                    "-c:v", config.video_codec,
                    "-preset", "fast",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-t", str(duration) if duration > 0 else "1",
                    "-c:a", config.audio_format,
                    "-b:a", "128k",
                    "-ar", "44100",
                    "-ac", "2",
                    "-movflags", "+faststart",
                    output_path,
                ]
            else:
                # Video input
                command = [
                    "ffmpeg",
                    "-y",
                    "-i", input_path,
                    "-c:v", config.video_codec,
                    "-preset", "fast",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-t", str(duration) if duration > 0 else "1",
                    "-c:a", config.audio_format,
                    "-b:a", "128k",
                    "-ar", "44100",
                    "-ac", "2",
                    "-movflags", "+faststart",
                    output_path,
                ]
        else:
            # No asset - use deterministic placeholder
            command = [
                "ffmpeg",
                "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s={config.width}x{config.height}:r={config.fps}:d={duration if duration > 0 else 1}",
                "-c:v", config.video_codec,
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", config.audio_format,
                "-b:a", "128k",
                "-ar", "44100",
                "-ac", "2",
                "-movflags", "+faststart",
                output_path,
            ]
        
        return command
    
    def build_command(self, request: RenderRequest, output_path: str) -> list[str]:
        """Build a deterministic FFmpeg command for a render request.
        
        Args:
            request: Render request containing job and configuration
            output_path: Full path for the output file
            
        Returns:
            List of FFmpeg command arguments
            
        Raises:
            ValueError: If output_path is unsafe or configuration is invalid
        """
        config = request.render_config
        
        # Validate configuration
        self._validate_config(config)
        
        # Validate and sanitize output path
        self._validate_output_path(output_path)
        
        # Build scene-aware command
        command = self._build_scene_command(request, output_path)
        
        return command

    def _validate_config(self, config: RenderConfig) -> None:
        """Validate render configuration.
        
        Args:
            config: Render configuration to validate
            
        Raises:
            ValueError: If configuration is invalid
        """
        if config.width <= 0:
            raise ValueError(f"Invalid width: {config.width}")
        if config.height <= 0:
            raise ValueError(f"Invalid height: {config.height}")
        if config.fps <= 0:
            raise ValueError(f"Invalid FPS: {config.fps}")
        if not config.video_format:
            raise ValueError("Video format cannot be empty")
        if not config.video_codec:
            raise ValueError("Video codec cannot be empty")
        if not config.audio_format:
            raise ValueError("Audio format cannot be empty")

    def _validate_output_path(self, output_path: str) -> None:
        """Validate output path for safety.
        
        Args:
            output_path: Output file path to validate
            
        Raises:
            ValueError: If path is unsafe
        """
        # Convert to Path for validation
        path = Path(output_path)
        
        # Check for path traversal attempts
        try:
            resolved = path.resolve()
            # Ensure the path doesn't escape reasonable bounds
            if ".." in path.parts:
                raise ValueError(f"Path traversal detected in: {output_path}")
        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid output path: {output_path}") from e

    def _build_output_path(self, config: RenderConfig, job_id: str) -> str:
        """Build output file path from configuration.
        
        Args:
            config: Render configuration
            job_id: Job identifier
            
        Returns:
            Full output file path
        """
        # Apply filename template
        filename = config.filename_template.format(job_id=job_id)
        
        # Join with output directory
        output_path = os.path.join(config.output_directory, filename)
        
        # Normalize path
        output_path = os.path.normpath(output_path)
        
        return output_path