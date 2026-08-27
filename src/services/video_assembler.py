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

from src.models.content_package import RenderConfig, Transition


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
        normalized_outputs = self._normalize_transitions(sorted_outputs)

        # Build the deterministic output path.
        output_path = self._build_output_path()

        # Build the deterministic FFmpeg command.
        # Use filter-complex when non-cut transitions are present, when audio
        # presence is mixed across scenes, or when any scene carries external
        # narration audio that must be muxed into the timeline. The concat
        # demuxer silently drops audio when input files disagree on audio
        # streams, so mixed audio scenes must use the filter path to keep
        # audio intact.
        use_filter_path = (
            self._uses_transition_filters(normalized_outputs)
            or self._has_mixed_audio(normalized_outputs)
            or any(self._scene_audio_reference(o) for o in normalized_outputs)
        )
        if use_filter_path:
            command, filter_complex, transition_plan = self._build_transition_command(
                normalized_outputs,
                output_path,
            )
            if not self.execute_enabled:
                return {
                    "status": "command_built",
                    "output_reference": output_path,
                    "total_scenes": len(sorted_outputs),
                    "command": command,
                    "filter_complex": filter_complex,
                    "transition_plan": transition_plan,
                    "ffmpeg_available": self.is_available(),
                    "message": "FFmpeg execution not yet implemented",
                }

            return self._execute_assembly(
                command,
                output_path,
                len(sorted_outputs),
                concat_content=None,
            )

        command, concat_content = self._build_concat_command(normalized_outputs, output_path)

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

    @staticmethod
    def _ensure_output_directory(output_path: str) -> None:
        """Create the parent directory of the output path when needed.

        Args:
            output_path: Full output file path.
        """
        directory = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(directory, exist_ok=True)

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

    def _normalize_transitions(self, sorted_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize transition metadata on sorted render outputs."""
        normalized: list[dict[str, Any]] = []
        for output in sorted_outputs:
            record = dict(output)
            transition = self._normalize_transition(record.get("transition_to_next"))
            if transition is not None:
                record["transition_to_next"] = transition
            normalized.append(record)
        return normalized

    def _detect_audio(self, output: dict[str, Any]) -> bool:
        """Return True if a scene output contains an audio stream.

        Uses the explicit ``has_audio`` flag when present on the record.
        Otherwise probes the file with ffprobe when it exists. Defaults to
        True when the file is not available, preserving legacy behavior for
        command-building against placeholder paths.
        """
        if "has_audio" in output:
            return bool(output.get("has_audio"))
        output_ref = output.get("output_reference")
        if output_ref and os.path.exists(output_ref):
            try:
                probe = subprocess.run(
                    [
                        "ffprobe",
                        "-v", "error",
                        "-select_streams", "a",
                        "-show_entries", "stream=index",
                        "-of", "csv=p=0",
                        str(output_ref),
                    ],
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return probe.returncode == 0 and bool(probe.stdout.strip())
            except (subprocess.SubprocessError, OSError):
                return False
        return True

    def _has_mixed_audio(self, sorted_outputs: list[dict[str, Any]]) -> bool:
        """Return True when scene outputs disagree on audio presence."""
        if not sorted_outputs:
            return False
        flags = [self._detect_audio(output) for output in sorted_outputs]
        return any(flags) and not all(flags)

    @staticmethod
    def _scene_audio_reference(output: dict[str, Any]) -> str | None:
        """Return the external narration audio path for a scene, if any.

        Args:
            output: Render output record.

        Returns:
            Audio file path string or None when the scene has no narration.
        """
        reference = output.get("audio_reference")
        if isinstance(reference, str) and reference.strip():
            return reference
        audio_result = output.get("audio_result")
        if isinstance(audio_result, dict):
            nested = audio_result.get("audio_reference")
            if isinstance(nested, str) and nested.strip():
                return nested
        return None

    def _normalize_transition(self, transition: Any) -> Transition | None:
        """Convert raw transition data into a structured Transition."""
        if transition is None or transition == "":
            return None
        if isinstance(transition, Transition):
            return transition
        if isinstance(transition, dict):
            return Transition(**transition)
        if isinstance(transition, str):
            return Transition(type=transition, duration=0.0 if transition.lower() == "cut" else 0.25, parameters={})
        raise ValueError("transition_to_next must be a Transition, dict, string, or None")

    def _uses_transition_filters(self, sorted_outputs: list[dict[str, Any]]) -> bool:
        """Return True if any adjacent scene transition needs filter-complex processing."""
        for output in sorted_outputs[:-1]:
            transition = output.get("transition_to_next")
            if isinstance(transition, Transition) and transition.type != "cut":
                return True
            if isinstance(transition, dict) and str(transition.get("type", "")).strip().lower() != "cut":
                return True
            if isinstance(transition, str) and transition.strip() and transition.strip().lower() != "cut":
                return True
        return False

    def _build_transition_command(
        self,
        sorted_outputs: list[dict[str, Any]],
        output_path: str,
    ) -> tuple[list[str], str, list[dict[str, Any]]]:
        """Build an FFmpeg filter-complex command with structured transitions."""
        command = ["ffmpeg", "-y"]
        filter_parts: list[str] = []
        transition_plan: list[dict[str, Any]] = []

        durations = [float(output.get("duration_seconds", 0.0)) for output in sorted_outputs]
        # Detect audio presence per scene so silent scenes get a synthesized
        # silence track instead of failing with "stream specifier :a matches
        # no streams".
        has_audio_flags = [self._detect_audio(output) for output in sorted_outputs]
        input_cursor = 0

        for index, output in enumerate(sorted_outputs):
            output_ref = output["output_reference"]
            # Track real FFmpeg input positions: each scene contributes one
            # video input, plus one extra audio input (narration or silence)
            # when its MP4 carries no native audio stream.
            video_input_index = input_cursor
            input_cursor += 1
            command.extend(["-i", output_ref])
            # settb unifies the timebase across all video branches; without it
            # chaining xfade after concat fails with "timebase do not match".
            filter_parts.append(
                f"[{video_input_index}:v]setpts=PTS-STARTPTS,settb=AVTB[srcv{index}]"
            )
            scene_audio = self._scene_audio_reference(output)
            if has_audio_flags[index]:
                filter_parts.append(
                    f"[{video_input_index}:a]asetpts=PTS-STARTPTS[srca{index}]"
                )
            elif scene_audio:
                # Attach the scene's narration audio, padded/trimmed to the
                # exact scene duration so transitions stay synchronized.
                command.extend(["-t", f"{durations[index]:.3f}", "-i", scene_audio])
                filter_parts.append(
                    f"[{input_cursor}:a]asetpts=PTS-STARTPTS,"
                    f"apad,atrim=0:{durations[index]:.3f}[srca{index}]"
                )
                input_cursor += 1
            else:
                # Synthesize silence so concat/acrossfade filters always see
                # an audio stream. Duration matches the scene exactly.
                command.extend([
                    "-f", "lavfi",
                    "-t", f"{durations[index]:.3f}",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                ])
                filter_parts.append(
                    f"[{input_cursor}:a]asetpts=PTS-STARTPTS[srca{index}]"
                )
                input_cursor += 1

        current_v = "srcv0"
        current_a = "srca0"
        current_duration = durations[0]

        for index in range(1, len(sorted_outputs)):
            output = sorted_outputs[index - 1]
            next_duration = durations[index]
            transition = self._normalize_transition(output.get("transition_to_next")) or Transition(
                type="cut",
                duration=0.0,
                parameters={},
            )
            if transition.type != "cut":
                transition.validate(max_duration=min(durations[index - 1], next_duration))

            next_v = f"srcv{index}"
            next_a = f"srca{index}"
            out_v = f"v{index}"
            out_a = f"a{index}"

            transition_plan.append(
                {
                    "scene_number": int(output.get("scene_number", index)),
                    "transition_to_next": transition.to_dict(),
                    "next_scene_number": int(sorted_outputs[index].get("scene_number", index + 1)),
                }
            )

            if transition.type == "cut":
                filter_parts.append(
                    f"[{current_v}][{current_a}][{next_v}][{next_a}]concat=n=2:v=1:a=1[{out_v}][{out_a}]"
                )
                current_duration += next_duration
            else:
                transition_name = self._map_transition_name(transition.type)
                offset = max(0.0, current_duration - transition.duration)
                filter_parts.append(
                    f"[{current_v}][{next_v}]xfade=transition={transition_name}:duration={transition.duration:.3f}:offset={offset:.3f}[{out_v}]"
                )
                filter_parts.append(
                    f"[{current_a}][{next_a}]acrossfade=d={transition.duration:.3f}[{out_a}]"
                )
                current_duration = current_duration + next_duration - transition.duration

            current_v = out_v
            current_a = out_a

        filter_complex = ";".join(filter_parts)
        command.extend([
            "-filter_complex",
            filter_complex,
            "-map",
            f"[{current_v}]",
            "-map",
            f"[{current_a}]",
            "-c:v",
            self.config.video_codec,
            "-c:a",
            self.config.audio_format,
            "-movflags",
            "+faststart",
            output_path,
        ])

        return command, filter_complex, transition_plan

    @staticmethod
    def _map_transition_name(transition_type: str) -> str:
        """Map a structured transition type to FFmpeg xfade transition name."""
        mapping = {
            "crossfade": "dissolve",
            "fade": "fade",
            "fade_to_black": "fadeblack",
            "slide_left": "slideleft",
            "slide_right": "slideright",
            "slide_up": "slideup",
            "slide_down": "slidedown",
        }
        return mapping.get(transition_type, "fade")

    def _execute_assembly(
        self,
        command: list[str],
        output_path: str,
        expected_scenes: int,
        concat_content: str | None,
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

        self._ensure_output_directory(output_path)
        exec_command = list(command)
        concat_file = None
        if concat_content is not None:
            # Write concat content to a temporary file. The concat demuxer
            # reading from stdin is unreliable on Windows, so use a file input.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(concat_content)
                concat_file = f.name

            # Replace the stdin input with the concat file path.
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
        finally:
            if concat_file and os.path.exists(concat_file):
                try:
                    os.unlink(concat_file)
                except OSError:
                    pass
