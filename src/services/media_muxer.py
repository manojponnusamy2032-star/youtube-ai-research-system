"""Media muxer service.

Combines a video file and an audio file into a single output file using
FFmpeg. Execution is opt-in via ``execute_enabled``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any


class MediaMuxer:
    """Muxes a video file and an audio file into a single output.

    When ``execute_enabled`` is False (default), returns command
    information only. When True, executes FFmpeg via subprocess.
    """

    def __init__(self, execute_enabled: bool = False) -> None:
        """Initialize the media muxer.

        Args:
            execute_enabled: If True, mux() will execute FFmpeg. Default: False
        """
        self.execute_enabled = execute_enabled

    def is_available(self) -> bool:
        """Check if FFmpeg executable is available on PATH.

        Returns:
            True if ffmpeg is found, False otherwise
        """
        return shutil.which("ffmpeg") is not None

    def build_command(
        self,
        video_reference: str,
        audio_reference: str,
        output_path: str,
    ) -> list[str]:
        """Build a deterministic FFmpeg mux command.

        Args:
            video_reference: Path to the input video file.
            audio_reference: Path to the input audio file.
            output_path: Full path for the output file.

        Returns:
            List of FFmpeg command arguments.

        Raises:
            ValueError: If any reference is empty.
        """
        self._validate_inputs(video_reference, audio_reference, output_path)

        command = [
            "ffmpeg",
            "-y",
            "-i", video_reference,
            "-i", audio_reference,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            "-map", "0:v:0",
            "-map", "1:a:0",
            output_path,
        ]

        return command

    def mux(
        self,
        video_reference: str,
        audio_reference: str,
        output_path: str,
    ) -> dict[str, Any]:
        """Mux a video and audio file into a single output.

        Args:
            video_reference: Path to the input video file.
            audio_reference: Path to the input audio file.
            output_path: Full path for the output file.

        Returns:
            Dictionary with mux result information.

        Raises:
            ValueError: If any reference is empty.
        """
        self._validate_inputs(video_reference, audio_reference, output_path)

        command = self.build_command(video_reference, audio_reference, output_path)

        # If execution is not enabled, return command information only.
        if not self.execute_enabled:
            return {
                "status": "command_built",
                "output_reference": output_path,
                "video_reference": video_reference,
                "audio_reference": audio_reference,
                "command": command,
                "ffmpeg_available": self.is_available(),
                "message": "FFmpeg execution not yet implemented",
            }

        # Execute FFmpeg.
        return self._execute_mux(command, output_path, video_reference, audio_reference)

    def _validate_inputs(
        self,
        video_reference: str,
        audio_reference: str,
        output_path: str,
    ) -> None:
        """Validate mux inputs.

        Args:
            video_reference: Path to the input video file.
            audio_reference: Path to the input audio file.
            output_path: Full path for the output file.

        Raises:
            ValueError: If any reference is empty.
        """
        if not video_reference:
            raise ValueError("video_reference cannot be empty")
        if not audio_reference:
            raise ValueError("audio_reference cannot be empty")
        if not output_path:
            raise ValueError("output_path cannot be empty")

    def _execute_mux(
        self,
        command: list[str],
        output_path: str,
        video_reference: str,
        audio_reference: str,
    ) -> dict[str, Any]:
        """Execute the FFmpeg mux command safely.

        Args:
            command: FFmpeg command as list of arguments.
            output_path: Expected output file path.
            video_reference: Input video file path.
            audio_reference: Input audio file path.

        Returns:
            Dictionary with mux result.
        """
        if not self.is_available():
            return {
                "status": "failed",
                "output_reference": None,
                "video_reference": video_reference,
                "audio_reference": audio_reference,
                "error": "FFmpeg is not available on PATH",
                "command": command,
            }

        try:
            start_time = time.time()
            result = subprocess.run(
                command,
                shell=False,  # Never use shell=True for security
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            elapsed_time = time.time() - start_time

            if result.returncode != 0:
                return {
                    "status": "failed",
                    "output_reference": None,
                    "video_reference": video_reference,
                    "audio_reference": audio_reference,
                    "error": f"FFmpeg failed with return code {result.returncode}",
                    "command": command,
                    "stderr": result.stderr[:500] if result.stderr else "",
                }

            # Verify output file exists.
            if not os.path.exists(output_path):
                return {
                    "status": "failed",
                    "output_reference": None,
                    "video_reference": video_reference,
                    "audio_reference": audio_reference,
                    "error": f"FFmpeg completed but output file not found: {output_path}",
                    "command": command,
                }

            # Verify output file is non-empty.
            if os.path.getsize(output_path) == 0:
                return {
                    "status": "failed",
                    "output_reference": None,
                    "video_reference": video_reference,
                    "audio_reference": audio_reference,
                    "error": f"FFmpeg completed but output file is empty: {output_path}",
                    "command": command,
                }

            return {
                "status": "completed",
                "output_reference": output_path,
                "video_reference": video_reference,
                "audio_reference": audio_reference,
                "command": command,
                "return_code": result.returncode,
                "execution_time_seconds": round(elapsed_time, 2),
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "output_reference": None,
                "video_reference": video_reference,
                "audio_reference": audio_reference,
                "error": "FFmpeg execution timed out after 300 seconds",
                "command": command,
            }
        except Exception as e:
            return {
                "status": "failed",
                "output_reference": None,
                "video_reference": video_reference,
                "audio_reference": audio_reference,
                "error": f"Muxing failed: {str(e)}",
                "command": command,
            }