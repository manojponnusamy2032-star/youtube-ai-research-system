"""Video assembler service for combining rendered scenes.

Builds a deterministic FFmpeg concat command that combines rendered scene
MP4 files in scene-number order. Optionally executes FFmpeg when enabled.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import Any

from src.models.content_package import RenderConfig


class VideoAssembler:
    """Assembles multiple scene videos into a single final video.

    Accepts a list of render output records and produces a deterministic
    FFmpeg concat command. When ``execute_enabled`` is True, the command
    is executed via subprocess.
    """

    def __init__(
        self,
        config: RenderConfig | None = None,
        execute_enabled: bool = False,
    ) -> None:
        """Initialize the video assembler.

        Args:
            config: Optional existing RenderConfig. A default is used if omitted.
            execute_enabled: If True, assemble() will execute FFmpeg. Default: False
        """
        self.config = config if config is not None else RenderConfig()
        self.execute_enabled = execute_enabled

    def is_available(self) -> bool:
        """Check if FFmpeg executable is available on PATH.

        Returns:
            True if ffmpeg is found, False otherwise
        """
        return shutil.which("ffmpeg") is not None

    def assemble(self, render_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        """Combine rendered scene outputs into a single final video.

        Args:
            render_outputs: List of render output records. Each record must
                contain ``job_id``, ``scene_number``, ``output_reference``,
                and ``status``.

        Returns:
            Dictionary with the generated output path and concat command.
            If ``execute_enabled`` is True, includes execution results.

        Raises:
            ValueError: If the input is invalid (not a list, empty, failed
                output, missing scene_number, duplicate scene_number, or
                missing output_reference).
        """
        self._validate_inputs(render_outputs)

        # Sort by scene_number.
        sorted_outputs = sorted(render_outputs, key=lambda o: o["scene_number"])

        # Build the deterministic output path.
        output_path = self._build_output_path()

        # Build the deterministic FFmpeg concat command.
        command, concat_content = self._build_concat_command(sorted_outputs, output_path)

        # If execution is not enabled, return command information only.
        if not self.execute_enabled:
            return {
                "status": "command_built",
                "output_reference": output_path,
                "total_scenes": len(sorted_outputs),
                "command": command,
                "concat_content": concat_content,
                "ffmpeg_available": self.is_available(),
                "message": "FFmpeg execution not yet implemented",
            }

        # Execute the assembly.
        return self._execute_assembly(command, output_path, len(sorted_outputs), concat_content)

    def _validate_inputs(self, render_outputs: list[dict[str, Any]]) -> None:
        """Validate render output records for assembly.

        Args:
            render_outputs: List of render output records.

        Raises:
            ValueError: If the input is invalid.
        """
        if not isinstance(render_outputs, list):
            raise ValueError("render_outputs must be a list")

        if len(render_outputs) == 0:
            raise ValueError("render_outputs cannot be empty")

        seen_scene_numbers: set[Any] = set()

        for idx, output in enumerate(render_outputs):
            if not isinstance(output, dict):
                raise ValueError(f"Output {idx} must be a dictionary")

            if "job_id" not in output or not str(output.get("job_id", "")).strip():
                raise ValueError(f"Output {idx} missing job_id")

            status = output.get("status")
            if status != "completed":
                raise ValueError(f"Output {idx} (job {output.get('job_id')}) is not completed")

            if "scene_number" not in output:
                raise ValueError(f"Output {idx} (job {output.get('job_id')}) missing scene_number")

            scene_number = output["scene_number"]
            if scene_number in seen_scene_numbers:
                raise ValueError(f"Duplicate scene_number: {scene_number}")
            seen_scene_numbers.add(scene_number)

            output_reference = output.get("output_reference")
            if not output_reference:
                raise ValueError(f"Output {idx} (job {output.get('job_id')}) missing output_reference")

    def _build_output_path(self) -> str:
        """Build the deterministic final output file path.

        Returns:
            Full output file path.
        """
        config = self.config
        video_format = config.video_format.lstrip(".")
        filename = f"final_video.{video_format}"
        output_path = os.path.join(config.output_directory, filename)
        return os.path.normpath(output_path)

    def _build_concat_command(
        self,
        sorted_outputs: list[dict[str, Any]],
        output_path: str,
    ) -> tuple[list[str], str]:
        """Build a deterministic FFmpeg concat command.

        Args:
            sorted_outputs: Outputs sorted by scene_number.
            output_path: Final output file path.

        Returns:
            Tuple of (command arguments list, concat file content).
        """
        concat_lines = []
        for output in sorted_outputs:
            output_ref = output["output_reference"]
            # Normalize to forward slashes for FFmpeg concat demuxer
            # (backslashes are treated as escape characters on Windows).
            normalized_path = output_ref.replace("\\", "/")
            escaped_path = normalized_path.replace("'", "\\'")
            concat_lines.append(f"file '{escaped_path}'")

        concat_content = "\n".join(concat_lines)

        command = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", "-",
            "-c:v", self.config.video_codec,
            "-c:a", self.config.audio_format,
            "-movflags", "+faststart",
            output_path,
        ]

        return command, concat_content

    def _execute_assembly(
        self,
        command: list[str],
        output_path: str,
        expected_scenes: int,
        concat_content: str,
    ) -> dict[str, Any]:
        """Execute the FFmpeg concat command safely.

        Args:
            command: FFmpeg command as list of arguments.
            output_path: Expected final output file path.
            expected_scenes: Number of scenes expected to be assembled.
            concat_content: Concat file content to pass via stdin.

        Returns:
            Dictionary with assembly result.
        """
        if not self.is_available():
            return {
                "status": "failed",
                "output_reference": None,
                "total_scenes": expected_scenes,
                "assembled_scenes": 0,
                "error": "FFmpeg is not available on PATH",
                "command": command,
            }

        # Write concat content to a temporary file. The concat demuxer
        # reading from stdin is unreliable on Windows, so use a file input.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(concat_content)
            concat_file = f.name

        # Replace the stdin input with the concat file path.
        exec_command = list(command)
        stdin_idx = exec_command.index("-i")
        exec_command[stdin_idx + 1] = concat_file

        try:
            start_time = time.time()
            result = subprocess.run(
                exec_command,
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
                    "total_scenes": expected_scenes,
                    "assembled_scenes": 0,
                    "error": f"FFmpeg failed with return code {result.returncode}",
                    "command": command,
                    "stderr": result.stderr[:500] if result.stderr else "",
                }

            # Verify output file exists.
            if not os.path.exists(output_path):
                return {
                    "status": "failed",
                    "output_reference": None,
                    "total_scenes": expected_scenes,
                    "assembled_scenes": 0,
                    "error": f"FFmpeg completed but output file not found: {output_path}",
                    "command": command,
                }

            # Verify output file is non-empty.
            if os.path.getsize(output_path) == 0:
                return {
                    "status": "failed",
                    "output_reference": None,
                    "total_scenes": expected_scenes,
                    "assembled_scenes": 0,
                    "error": f"FFmpeg completed but output file is empty: {output_path}",
                    "command": command,
                }

            return {
                "status": "completed",
                "output_reference": output_path,
                "total_scenes": expected_scenes,
                "assembled_scenes": expected_scenes,
                "command": command,
                "return_code": result.returncode,
                "execution_time_seconds": round(elapsed_time, 2),
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "output_reference": None,
                "total_scenes": expected_scenes,
                "assembled_scenes": 0,
                "error": "FFmpeg execution timed out after 300 seconds",
                "command": command,
            }
        except Exception as e:
            return {
                "status": "failed",
                "output_reference": None,
                "total_scenes": expected_scenes,
                "assembled_scenes": 0,
                "error": f"Assembly failed: {str(e)}",
                "command": command,
            }