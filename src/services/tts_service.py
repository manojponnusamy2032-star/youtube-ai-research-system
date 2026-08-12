"""Text-to-Speech (TTS) abstraction and mock service.

Provides a clean interface for TTS translation, defining the TTSRequest dataclass,
the abstract base class TTSService, and a deterministic MockTTSService.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class TTSRequest:
    """Request data for Text-to-Speech generation."""

    text: str = ""
    voice_reference: str = ""
    audio_format: str = "wav"

    def __post_init__(self) -> None:
        """Validate input values."""
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")
        if not isinstance(self.voice_reference, str):
            raise ValueError("voice_reference must be a string")
        if not isinstance(self.audio_format, str):
            raise ValueError("audio_format must be a string")
        if not self.audio_format.strip():
            raise ValueError("audio_format cannot be empty")


class TTSService:
    """Abstract base class for TTS services.

    Defines the contract for text-to-speech generation.
    """

    def generate(self, request: TTSRequest) -> dict[str, Any]:
        """Generate speech audio from text.

        Args:
            request: The TTS request containing text and formatting options.

        Returns:
            Dictionary with status, audio_reference, and duration_seconds.
        """
        raise NotImplementedError


class MockTTSService(TTSService):
    """Deterministic mock implementation of TTSService.

    Returns deterministic outputs for testing without calling external APIs,
    subprocesses, or writing files by default. If an output directory is
    provided, it materializes a deterministic local placeholder audio file.
    """

    def __init__(self, output_directory: str | None = None) -> None:
        self.output_directory = output_directory

    def generate(self, request: TTSRequest) -> dict[str, Any]:
        """Deterministically generate a mock audio reference and duration.

        Args:
            request: The TTS request.

        Returns:
            Dictionary with status, audio_reference, and duration_seconds.
        """
        if not isinstance(request, TTSRequest):
            raise ValueError("request must be a TTSRequest")

        # Generate a deterministic hash based on text and voice
        combined = f"{request.text}:{request.voice_reference}:{request.audio_format}"
        text_hash = hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]

        audio_ref = f"mock://tts/{text_hash}.{request.audio_format}"

        if self.output_directory is not None:
            output_dir = self.output_directory
            os.makedirs(output_dir, exist_ok=True)
            extension = request.audio_format.lstrip(".")
            output_path = os.path.join(output_dir, f"{text_hash}.{extension}")
            payload = f"mock-audio:{request.text}:{request.voice_reference}:{request.audio_format}".encode("utf-8")
            with open(output_path, "wb") as handle:
                handle.write(payload)
            audio_ref = os.path.abspath(output_path)

        # Deterministic duration based on text length (approx 15 characters per second)
        char_count = len(request.text)
        duration = max(1.0, round(char_count / 15.0, 2))

        return {
            "status": "completed",
            "audio_reference": audio_ref,
            "duration_seconds": duration,
        }
