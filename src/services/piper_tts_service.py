"""Offline Piper text-to-speech service.

Implements the TTSService contract using the Piper neural TTS engine, which
runs locally with no API key and no per-request cost. Audio is produced as
16-bit PCM WAV files.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import wave
from typing import Any

from src.services.tts_service import TTSRequest, TTSService

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ENV = "PIPER_VOICE_MODEL"


class PiperTTSService(TTSService):
    """Generates narration audio locally with Piper."""

    def __init__(
        self,
        voice_model: str | None = None,
        output_directory: str = "output/audio",
        timeout_seconds: int = 300,
    ) -> None:
        """Initialize the Piper TTS service.

        Args:
            voice_model: Path to a Piper ``.onnx`` voice model. Defaults to
                the ``PIPER_VOICE_MODEL`` environment variable.
            output_directory: Directory where WAV files are written.
            timeout_seconds: Timeout for a single synthesis call.
        """
        self.voice_model = voice_model or os.environ.get(DEFAULT_VOICE_ENV, "")
        self.output_directory = output_directory
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """Return True when a Piper runtime and a voice model are present."""
        return bool(self.voice_model) and os.path.exists(self.voice_model)

    def build_command(self, output_path: str) -> list[str]:
        """Build the Piper command used to synthesize a single file.

        Args:
            output_path: Destination WAV path.

        Returns:
            Command arguments for Piper.
        """
        piper_binary = shutil.which("piper")
        base = [piper_binary] if piper_binary else [sys.executable, "-m", "piper"]
        return [*base, "--model", self.voice_model, "--output-file", output_path]

    def generate(self, request: TTSRequest) -> dict[str, Any]:
        """Synthesize narration audio for a request.

        Args:
            request: TTS request holding the narration text.

        Returns:
            Dictionary with status, audio_reference and duration_seconds.
            On failure, status is ``failed`` and ``error`` explains why.
        """
        if not isinstance(request, TTSRequest):
            raise ValueError("request must be a TTSRequest")
        if not request.text.strip():
            raise ValueError("text cannot be empty")

        if not self.is_available():
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": (
                    "Piper voice model not found. Set PIPER_VOICE_MODEL to a "
                    "downloaded .onnx voice."
                ),
            }

        output_path = self._build_output_path(request)
        command = self.build_command(output_path)

        try:
            result = subprocess.run(
                command,
                input=request.text,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": f"Piper timed out after {self.timeout_seconds}s",
                "command": command,
            }
        except OSError as error:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": f"Piper could not be executed: {error}",
                "command": command,
            }

        if result.returncode != 0:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": f"Piper failed with return code {result.returncode}",
                "command": command,
                "stderr": (result.stderr or "")[:500],
            }

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": f"Piper produced no audio at {output_path}",
                "command": command,
            }

        duration = self.probe_duration(output_path)
        logger.info(f"Piper synthesized {output_path} ({duration}s)")
        return {
            "status": "completed",
            "audio_reference": os.path.abspath(output_path),
            "duration_seconds": duration,
            "command": command,
        }

    @staticmethod
    def probe_duration(wav_path: str) -> float:
        """Return the duration of a WAV file in seconds."""
        with wave.open(wav_path, "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate() or 1
        return round(frames / rate, 3)

    def _build_output_path(self, request: TTSRequest) -> str:
        """Build a deterministic output path for a request."""
        digest = hashlib.md5(
            f"{request.text}:{request.voice_reference}".encode("utf-8")
        ).hexdigest()[:12]
        os.makedirs(self.output_directory, exist_ok=True)
        return os.path.join(self.output_directory, f"narration_{digest}.wav")
