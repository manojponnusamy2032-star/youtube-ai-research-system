"""Tests for the offline Piper TTS service."""

from __future__ import annotations

import os
import subprocess
import wave
from unittest.mock import MagicMock, patch

import pytest

from src.services.piper_tts_service import PiperTTSService
from src.services.tts_service import TTSRequest


def _voice_model(tmp_path) -> str:
    """Create a placeholder voice model file."""
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    return str(model)


def _write_wav(path: str, seconds: float = 1.0, rate: int = 22050) -> None:
    """Write a silent WAV file of the requested duration."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))


def test_is_available_requires_existing_model(tmp_path) -> None:
    """Availability depends on a model path that exists."""
    assert PiperTTSService(voice_model=_voice_model(tmp_path)).is_available()
    assert not PiperTTSService(voice_model="/missing/voice.onnx").is_available()


def test_build_command_uses_model_and_output(tmp_path) -> None:
    """The command passes the model and output file to Piper."""
    service = PiperTTSService(voice_model=_voice_model(tmp_path))

    command = service.build_command("/tmp/out.wav")

    assert "--model" in command
    assert command[command.index("--model") + 1] == service.voice_model
    assert command[command.index("--output-file") + 1] == "/tmp/out.wav"


def test_generate_reports_missing_model() -> None:
    """A missing voice model fails cleanly instead of raising."""
    service = PiperTTSService(voice_model="/missing/voice.onnx")

    result = service.generate(TTSRequest(text="hello"))

    assert result["status"] == "failed"
    assert "PIPER_VOICE_MODEL" in result["error"]


def test_generate_rejects_empty_text(tmp_path) -> None:
    """Empty narration is rejected."""
    service = PiperTTSService(voice_model=_voice_model(tmp_path))

    with pytest.raises(ValueError):
        service.generate(TTSRequest(text="   "))


def test_generate_returns_duration_on_success(tmp_path) -> None:
    """A successful run reports the real WAV duration."""
    service = PiperTTSService(
        voice_model=_voice_model(tmp_path),
        output_directory=str(tmp_path / "audio"),
    )

    def fake_run(command, **kwargs):
        _write_wav(command[command.index("--output-file") + 1], seconds=2.0)
        return MagicMock(returncode=0, stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        result = service.generate(TTSRequest(text="hello world"))

    assert result["status"] == "completed"
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.01)
    assert os.path.exists(result["audio_reference"])


def test_generate_reports_nonzero_exit(tmp_path) -> None:
    """A Piper failure is surfaced with its return code."""
    service = PiperTTSService(
        voice_model=_voice_model(tmp_path),
        output_directory=str(tmp_path / "audio"),
    )

    with patch("subprocess.run", return_value=MagicMock(returncode=1, stderr="boom")):
        result = service.generate(TTSRequest(text="hello"))

    assert result["status"] == "failed"
    assert "return code 1" in result["error"]


def test_generate_reports_timeout(tmp_path) -> None:
    """A timeout is reported rather than propagated."""
    service = PiperTTSService(
        voice_model=_voice_model(tmp_path),
        output_directory=str(tmp_path / "audio"),
        timeout_seconds=5,
    )

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("piper", 5)):
        result = service.generate(TTSRequest(text="hello"))

    assert result["status"] == "failed"
    assert "timed out" in result["error"]


def test_output_path_is_deterministic(tmp_path) -> None:
    """The same text maps to the same output file."""
    service = PiperTTSService(
        voice_model=_voice_model(tmp_path),
        output_directory=str(tmp_path / "audio"),
    )

    first = service._build_output_path(TTSRequest(text="same text"))
    second = service._build_output_path(TTSRequest(text="same text"))

    assert first == second
