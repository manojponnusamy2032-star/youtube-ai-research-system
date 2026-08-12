"""Tests for the TTSAudioRenderer."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import pytest

from src.models.content_package import AudioRequest
from src.services.audio_renderer import AudioRenderRequest, AudioRenderer
from src.services.tts_audio_renderer import TTSAudioRenderer
from src.services.tts_service import MockTTSService, TTSService


class RecordingTTSService(MockTTSService):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []

    def generate(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return super().generate(request)


class FailingTTSService(TTSService):
    def generate(self, request: Any) -> dict[str, Any]:
        raise RuntimeError("simulated failure")


class FakeFallbackRenderer(AudioRenderer):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.last_request: AudioRenderRequest | None = None

    def render(self, request: AudioRenderRequest) -> dict[str, Any]:
        self.last_request = request
        return self.result


def make_audio_request(**overrides: Any) -> AudioRequest:
    return AudioRequest(
        scene_number=overrides.get("scene_number", 1),
        duration_seconds=overrides.get("duration_seconds", 5),
        narration_text=overrides.get("narration_text", "Hello world"),
        voice_reference=overrides.get("voice_reference", "default"),
        audio_format=overrides.get("audio_format", "wav"),
    )


def make_tts_renderer(tts_service: TTSService, fallback: AudioRenderer | None = None) -> TTSAudioRenderer:
    return TTSAudioRenderer(tts_service=tts_service, fallback_renderer=fallback)


def test_tts_service_is_called():
    service = RecordingTTSService()
    renderer = make_tts_renderer(service)
    request = AudioRenderRequest(audio_request=make_audio_request())

    result = renderer.render(request)

    assert len(service.requests) == 1
    assert result["status"] == "completed"


def test_narration_text_reaches_tts_request():
    service = RecordingTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(narration_text="Hello world")
    request = AudioRenderRequest(audio_request=audio_request)

    renderer.render(request)

    assert service.requests[0].text == "Hello world"


def test_voice_reference_reaches_tts_request():
    service = RecordingTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(voice_reference="narrator-one")
    request = AudioRenderRequest(audio_request=audio_request)

    renderer.render(request)

    assert service.requests[0].voice_reference == "narrator-one"


def test_audio_format_reaches_tts_request():
    service = RecordingTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(audio_format="mp3")
    request = AudioRenderRequest(audio_request=audio_request)

    renderer.render(request)

    assert service.requests[0].audio_format == "mp3"


def test_tts_result_reaches_renderer_result():
    service = MockTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request()
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)
    expected_duration = max(1.0, round(len(audio_request.narration_text) / 15.0, 2))

    assert result["status"] == "completed"
    assert result["audio_reference"].startswith("mock://tts/")
    assert result["duration_seconds"] == expected_duration


def test_scene_number_is_preserved():
    service = MockTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(scene_number=3)
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert result["scene_number"] == 3


def test_tts_duration_is_preserved():
    service = MockTTSService()
    renderer = make_tts_renderer(service)
    narration_text = "This is a longer narration."
    audio_request = make_audio_request(narration_text=narration_text)
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)
    expected_duration = max(1.0, round(len(narration_text) / 15.0, 2))

    assert result["duration_seconds"] == expected_duration


def test_empty_narration_skips_tts():
    service = RecordingTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(narration_text="")
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert result["status"] == "no_narration"
    assert result["audio_reference"] is None
    assert result["duration_seconds"] == 0
    assert len(service.requests) == 0


def test_empty_narration_uses_fallback_renderer():
    fallback_result = {
        "scene_number": 1,
        "status": "fallback",
        "audio_reference": "mock://fallback",
        "duration_seconds": 5,
    }
    fallback = FakeFallbackRenderer(fallback_result)
    service = MockTTSService()
    renderer = make_tts_renderer(service, fallback=fallback)
    audio_request = make_audio_request(narration_text="")
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert fallback.last_request is request
    assert result == fallback_result


def test_tts_failure_uses_fallback():
    fallback_result = {
        "scene_number": 1,
        "status": "fallback",
        "audio_reference": "mock://fallback",
        "duration_seconds": 5,
    }
    fallback = FakeFallbackRenderer(fallback_result)
    service = FailingTTSService()
    renderer = make_tts_renderer(service, fallback=fallback)
    audio_request = make_audio_request(narration_text="Hello world")
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert fallback.last_request is request
    assert result == fallback_result


def test_tts_failure_without_fallback_returns_failure():
    service = FailingTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(narration_text="Hello world")
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert result["status"] == "failed"
    assert result["scene_number"] == 1
    assert "TTS generation failed" in result["error"]


def test_injected_tts_service_is_used():
    service = RecordingTTSService()
    renderer = make_tts_renderer(service)

    assert renderer.tts_service is service


def test_deterministic_mock_tts_service_works_through_renderer():
    service = MockTTSService()
    renderer = make_tts_renderer(service)
    narration_text = "Hello deterministic world"
    audio_request = make_audio_request(narration_text=narration_text, voice_reference="alice", audio_format="wav")
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)
    expected_hash = hashlib.md5(f"{narration_text}:alice:wav".encode("utf-8")).hexdigest()[:12]
    assert result["audio_reference"] == f"mock://tts/{expected_hash}.wav"


def test_no_external_calls_are_made():
    service = MockTTSService()
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(narration_text="Hello world")
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert result["status"] == "completed"
    assert result["audio_reference"].startswith("mock://tts/")


def test_file_backed_tts_output_reaches_renderer_result(tmp_path):
    service = MockTTSService(output_directory=str(tmp_path))
    renderer = make_tts_renderer(service)
    audio_request = make_audio_request(narration_text="Hello world", voice_reference="default", audio_format="wav")
    request = AudioRenderRequest(audio_request=audio_request)

    result = renderer.render(request)

    assert result["status"] == "completed"
    assert os.path.isabs(result["audio_reference"])
    assert os.path.exists(result["audio_reference"])
    assert result["audio_reference"].startswith(str(tmp_path))
