"""Unit tests for TTSService and MockTTSService."""

from __future__ import annotations

import os

import pytest

from src.services.tts_service import MockTTSService, TTSRequest, TTSService


def test_tts_request_creation() -> None:
    """Test standard creation of a TTSRequest."""
    req = TTSRequest(text="Hello", voice_reference="en-US-1", audio_format="mp3")
    assert req.text == "Hello"
    assert req.voice_reference == "en-US-1"
    assert req.audio_format == "mp3"


def test_default_audio_format() -> None:
    """Test that default audio format is wav."""
    req = TTSRequest(text="Hello", voice_reference="en-US-1")
    assert req.audio_format == "wav"


def test_text_validation() -> None:
    """Test validation of text parameter in TTSRequest."""
    with pytest.raises(ValueError, match="text must be a string"):
        # Type error on text parameter
        TTSRequest(text=123)  # type: ignore


def test_voice_validation() -> None:
    """Test validation of voice_reference parameter in TTSRequest."""
    with pytest.raises(ValueError, match="voice_reference must be a string"):
        # Type error on voice_reference parameter
        TTSRequest(text="Hello", voice_reference=None)  # type: ignore


def test_audio_format_validation() -> None:
    """Test validation of audio_format parameter in TTSRequest."""
    with pytest.raises(ValueError, match="audio_format must be a string"):
        # Type error on audio_format parameter
        TTSRequest(text="Hello", voice_reference="voice", audio_format=True)  # type: ignore

    with pytest.raises(ValueError, match="audio_format cannot be empty"):
        TTSRequest(text="Hello", voice_reference="voice", audio_format="")

    with pytest.raises(ValueError, match="audio_format cannot be empty"):
        TTSRequest(text="Hello", voice_reference="voice", audio_format="   ")


def test_tts_request_reaches_service() -> None:
    """Test that TTSRequest reaches the service generate method and validates type."""
    service = MockTTSService()
    with pytest.raises(ValueError, match="request must be a TTSRequest"):
        service.generate("not a request")  # type: ignore


def test_mock_tts_service_returns_completed() -> None:
    """Test that MockTTSService returns a completed status and basic fields."""
    service = MockTTSService()
    req = TTSRequest(text="Hello world", voice_reference="default", audio_format="mp3")
    result = service.generate(req)

    assert result["status"] == "completed"
    assert "audio_reference" in result
    assert "duration_seconds" in result


def test_deterministic_output() -> None:
    """Test that output is deterministic for the exact same request."""
    service = MockTTSService()
    req1 = TTSRequest(text="Hello", voice_reference="voice1", audio_format="wav")
    req2 = TTSRequest(text="Hello", voice_reference="voice1", audio_format="wav")

    res1 = service.generate(req1)
    res2 = service.generate(req2)

    assert res1["audio_reference"] == res2["audio_reference"]
    assert res1["duration_seconds"] == res2["duration_seconds"]


def test_duration_is_deterministic() -> None:
    """Test that generated duration is deterministic and based on text length."""
    service = MockTTSService()
    req1 = TTSRequest(text="Short text", voice_reference="v")
    req2 = TTSRequest(text="Much longer text that should produce a longer duration", voice_reference="v")

    res1 = service.generate(req1)
    res2 = service.generate(req2)

    assert res1["duration_seconds"] > 0
    assert res2["duration_seconds"] > res1["duration_seconds"]


def test_different_text_produces_different_reference() -> None:
    """Test that different text produces a different deterministic reference."""
    service = MockTTSService()
    req1 = TTSRequest(text="Hello", voice_reference="voice")
    req2 = TTSRequest(text="World", voice_reference="voice")

    res1 = service.generate(req1)
    res2 = service.generate(req2)

    assert res1["audio_reference"] != res2["audio_reference"]


def test_empty_text_handled() -> None:
    """Test that empty text works and produces minimum duration."""
    service = MockTTSService()
    req = TTSRequest(text="", voice_reference="voice")
    res = service.generate(req)

    assert res["status"] == "completed"
    assert res["duration_seconds"] == 1.0  # Min duration of 1.0


def test_abstract_service_raises_not_implemented_error() -> None:
    """Test that the abstract TTSService base class raises NotImplementedError."""
    # Create an instance of abstract class to verify base behavior
    class TestService(TTSService):
        pass

    service = TestService()
    req = TTSRequest(text="Hello")
    with pytest.raises(NotImplementedError):
        service.generate(req)


def test_default_behavior_remains_mock_reference() -> None:
    """Test that default MockTTSService output remains the mock:// reference."""
    service = MockTTSService()
    req = TTSRequest(text="Hello", voice_reference="voice", audio_format="wav")

    result = service.generate(req)

    assert result["audio_reference"].startswith("mock://tts/")


def test_file_backed_mode_creates_non_empty_file(tmp_path: pytest.TempPathFactory) -> None:
    """Test that file-backed mode creates a non-empty file."""
    output_dir = tmp_path / "tts-output"
    service = MockTTSService(output_directory=str(output_dir))
    req = TTSRequest(text="Hello", voice_reference="voice", audio_format="wav")

    result = service.generate(req)

    assert os.path.exists(result["audio_reference"])
    assert os.path.getsize(result["audio_reference"]) > 0


def test_file_backed_mode_returns_created_file_path(tmp_path: pytest.TempPathFactory) -> None:
    """Test that file-backed mode returns the created file path."""
    output_dir = tmp_path / "tts-output"
    service = MockTTSService(output_directory=str(output_dir))
    req = TTSRequest(text="Hello", voice_reference="voice", audio_format="wav")

    result = service.generate(req)

    assert result["audio_reference"].startswith(str(output_dir))
    assert os.path.basename(result["audio_reference"]).endswith(".wav")


def test_repeated_identical_requests_remain_deterministic_in_file_mode(tmp_path: pytest.TempPathFactory) -> None:
    """Test that repeated identical file-backed requests remain deterministic."""
    output_dir = tmp_path / "tts-output"
    service = MockTTSService(output_directory=str(output_dir))
    req1 = TTSRequest(text="Hello", voice_reference="voice", audio_format="wav")
    req2 = TTSRequest(text="Hello", voice_reference="voice", audio_format="wav")

    result1 = service.generate(req1)
    result2 = service.generate(req2)

    assert result1["audio_reference"] == result2["audio_reference"]


def test_existing_validation_still_works_with_output_directory(tmp_path: pytest.TempPathFactory) -> None:
    """Test that request validation still works when output_directory is provided."""
    service = MockTTSService(output_directory=str(tmp_path))

    with pytest.raises(ValueError, match="request must be a TTSRequest"):
        service.generate("not a request")  # type: ignore
