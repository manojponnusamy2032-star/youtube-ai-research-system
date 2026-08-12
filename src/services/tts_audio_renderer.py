"""Text-to-speech backed audio renderer."""

from __future__ import annotations

from typing import Any

from src.models.content_package import AudioRequest
from src.services.audio_renderer import AudioRenderRequest, AudioRenderer
from src.services.tts_service import TTSRequest, TTSService


class TTSAudioRenderer(AudioRenderer):
    """Audio renderer that delegates narration generation to a TTS service."""

    def __init__(
        self,
        tts_service: TTSService,
        fallback_renderer: AudioRenderer | None = None,
    ) -> None:
        if tts_service is None:
            raise ValueError("tts_service cannot be None")

        self.tts_service = tts_service
        self.fallback_renderer = fallback_renderer

    def render(self, request: AudioRenderRequest) -> dict[str, Any]:
        """Render narration audio using the injected TTS service."""
        audio = self._validate_request(request)

        if audio.narration_text == "":
            if self.fallback_renderer is not None:
                return self.fallback_renderer.render(request)

            return {
                "scene_number": audio.scene_number,
                "status": "no_narration",
                "audio_reference": None,
                "duration_seconds": 0,
                "message": "No narration text provided",
            }

        tts_request = TTSRequest(
            text=audio.narration_text,
            voice_reference=audio.voice_reference,
            audio_format=audio.audio_format,
        )

        try:
            tts_result = self.tts_service.generate(tts_request)
        except Exception as exc:
            if self.fallback_renderer is not None:
                return self.fallback_renderer.render(request)

            return {
                "scene_number": audio.scene_number,
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0,
                "error": f"TTS generation failed: {str(exc)}",
            }

        if not isinstance(tts_result, dict):
            return {
                "scene_number": audio.scene_number,
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0,
                "error": "TTS service returned an invalid result",
            }

        result: dict[str, Any] = dict(tts_result)
        result["scene_number"] = audio.scene_number
        return result

    def _validate_request(self, request: AudioRenderRequest) -> AudioRequest:
        if request is None:
            raise ValueError("Audio render request cannot be None")
        if not isinstance(request, AudioRenderRequest):
            raise ValueError("request must be an AudioRenderRequest")

        audio = request.audio_request
        if not isinstance(audio, AudioRequest):
            raise ValueError("audio_request must be an AudioRequest")

        return audio
