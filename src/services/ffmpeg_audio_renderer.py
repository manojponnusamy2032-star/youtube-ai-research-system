"""FFmpeg-based audio renderer.

Generates a deterministic test-tone audio file using FFmpeg's built-in
lavfi sine source. This is NOT TTS — it produces a pipeline-validation
audio signal without external APIs or paid services.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any

from src.services.audio_renderer import AudioRenderRequest, AudioRenderer


class FFmpegAudioRenderer(AudioRenderer):
    """Renders a deterministic audio signal using FFmpeg.

    When ``execute_enabled`` is False (default), returns command
    information only. When True, executes FFmpeg via subprocess.
    """

    def __init__(
        self,
        output_directory: str = "output",
        execute_enabled: bool = False,
    ) -> None:
        """Initialize the FFmpeg audio renderer.

        Args:
            output_directory: Directory for generated audio files.
            execute_enabled: If True, render() will execute FFmpeg. Default: False
        """
        self.output_directory = output_directory
        self.execute_enabled = execute_enabled

    def is_available(self) -> bool:
        """Check if FFmpeg executable is available on PATH.

        Returns:
            True if ffmpeg is found, False otherwise
        """
        return shutil.which("ffmpeg") is not None

    def render(self, request: AudioRenderRequest) -> dict[str, Any]:
        """Render a deterministic audio signal for a request.

        Args:
            request: Audio render request containing the AudioRequest.

        Returns:
            Dictionary with render result information.

        Raises:
            ValueError: If the request is invalid.
        """
        audio = self._validate_request(request)

        # Build deterministic output path.
        output_path = self._build_output_path(audio)

        # Build deterministic FFmpeg command.
        command = self.build_command(request, output_path)

        # If execution is not enabled, return command information only.
        if not self.execute_enabled:
            return {
                "scene_number": audio.scene_number,
                "status": "command_built",
                "audio_reference": output_path,
                "duration_seconds": audio.duration_seconds,
                "command": command,
                "ffmpeg_available": self.is_available(),
                "message": "FFmpeg execution not yet implemented",
            }

        # Execute FFmpeg.
        return self._execute_ffmpeg(command, output_path, audio)

    def build_command(self, request: AudioRenderRequest, output_path: str) -> list[str]:
        """Build a deterministic FFmpeg command for audio generation.

        Args:
            request: Audio render request containing the AudioRequest.
            output_path: Full path for the output audio file.

        Returns:
            List of FFmpeg command arguments.

        Raises:
            ValueError: If the request is invalid.
        """
        audio = self._validate_request(request)

        duration = max(audio.duration_seconds, 1)
        audio_format = audio.audio_format.lstrip(".")

        # Map audio format to FFmpeg codec.
        codec_map = {
            "aac": "aac",
            "mp3": "libmp3lame",
            "wav": "pcm_s16le",
            "m4a": "aac",
            "ogg": "libvorbis",
        }
        codec = codec_map.get(audio_format, "aac")

        command = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration}",
            "-c:a", codec,
            "-b:a", "128k",
            output_path,
        ]

        return command

    def _validate_request(self, request: AudioRenderRequest) -> Any:
        """Validate the audio render request.

        Args:
            request: Audio render request to validate.

        Returns:
            The validated AudioRequest.

        Raises:
            ValueError: If the request or its fields are invalid.
        """
        if request is None:
            raise ValueError("Audio render request cannot be None")

        if not isinstance(request, AudioRenderRequest):
            raise ValueError("request must be an AudioRenderRequest")

        audio = request.audio_request
        if audio is None:
            raise ValueError("Audio render request missing audio_request")

        if audio.scene_number <= 0:
            raise ValueError("scene_number must be positive")

        return audio

    def _build_output_path(self, audio: Any) -> str:
        """Build the deterministic output file path.

        Args:
            audio: The AudioRequest.

        Returns:
            Full output file path.
        """
        audio_format = audio.audio_format.lstrip(".")
        filename = f"audio_scene_{audio.scene_number}.{audio_format}"
        output_path = os.path.join(self.output_directory, filename)
        return os.path.normpath(output_path)

    def _execute_ffmpeg(
        self,
        command: list[str],
        output_path: str,
        audio: Any,
    ) -> dict[str, Any]:
        """Execute FFmpeg command safely.

        Args:
            command: FFmpeg command as list of arguments.
            output_path: Expected output file path.
            audio: The AudioRequest.

        Returns:
            Dictionary with execution result.
        """
        if not self.is_available():
            return {
                "scene_number": audio.scene_number,
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": audio.duration_seconds,
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
                    "scene_number": audio.scene_number,
                    "status": "failed",
                    "audio_reference": None,
                    "duration_seconds": audio.duration_seconds,
                    "error": f"FFmpeg failed with return code {result.returncode}",
                    "command": command,
                    "stderr": result.stderr[:500] if result.stderr else "",
                }

            # Verify output file exists.
            if not os.path.exists(output_path):
                return {
                    "scene_number": audio.scene_number,
                    "status": "failed",
                    "audio_reference": None,
                    "duration_seconds": audio.duration_seconds,
                    "error": f"FFmpeg completed but output file not found: {output_path}",
                    "command": command,
                }

            # Verify output file is non-empty.
            if os.path.getsize(output_path) == 0:
                return {
                    "scene_number": audio.scene_number,
                    "status": "failed",
                    "audio_reference": None,
                    "duration_seconds": audio.duration_seconds,
                    "error": f"FFmpeg completed but output file is empty: {output_path}",
                    "command": command,
                }

            return {
                "scene_number": audio.scene_number,
                "status": "completed",
                "audio_reference": output_path,
                "duration_seconds": audio.duration_seconds,
                "command": command,
                "return_code": result.returncode,
                "execution_time_seconds": round(elapsed_time, 2),
            }

        except subprocess.TimeoutExpired:
            return {
                "scene_number": audio.scene_number,
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": audio.duration_seconds,
                "error": "FFmpeg execution timed out after 300 seconds",
                "command": command,
            }
        except Exception as e:
            return {
                "scene_number": audio.scene_number,
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": audio.duration_seconds,
                "error": f"Audio rendering failed: {str(e)}",
                "command": command,
            }