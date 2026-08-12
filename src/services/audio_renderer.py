"""Audio renderer service abstraction.

Provides the audio rendering contract without implementing TTS, voice
synthesis, or real audio generation yet. Mirrors the existing
``Renderer`` / ``MockRenderer`` architecture used by the video pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.models.content_package import AudioRequest


@dataclass
class AudioRenderRequest:
    """Request object passed to audio renderers.

    Wraps an existing ``AudioRequest`` and optionally the associated job
    dictionary. Does not duplicate the fields of ``AudioRequest``.
    """

    audio_request: AudioRequest
    job: dict[str, Any] = field(default_factory=dict)


class AudioRenderer:
    """Abstract base class for audio renderers.

    Subclasses implement ``render`` to produce an audio output reference.
    """

    def render(self, request: AudioRenderRequest) -> dict[str, Any]:
        """Render audio for a single request.

        Args:
            request: Audio render request containing the AudioRequest.

        Returns:
            Result dictionary with scene_number, status, audio_reference,
            and duration_seconds.
        """
        raise NotImplementedError


class MockAudioRenderer(AudioRenderer):
    """Deterministic mock audio renderer for testing.

    Does not perform actual audio generation. Returns deterministic mock
    results without creating files or calling external services.
    """

    def render(self, request: AudioRenderRequest) -> dict[str, Any]:
        """Create a deterministic mock audio render result.

        Args:
            request: Audio render request containing the AudioRequest.

        Returns:
            Mock result with scene_number, status, audio_reference,
            and duration_seconds.

        Raises:
            ValueError: If the request is missing or invalid.
        """
        audio = self._validate_request(request)

        scene_number = audio.scene_number
        duration_seconds = audio.duration_seconds

        return {
            "scene_number": scene_number,
            "status": "completed",
            "audio_reference": f"mock://audio/scene_{scene_number}",
            "duration_seconds": duration_seconds,
        }

    def _validate_request(self, request: AudioRenderRequest) -> AudioRequest:
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

        if not isinstance(audio, AudioRequest):
            raise ValueError("audio_request must be an AudioRequest")

        if audio.scene_number <= 0:
            raise ValueError("scene_number must be positive")

        return audio