"""Tests for AudioRequest data contract."""

from __future__ import annotations

import pytest

from src.models.content_package import AudioRequest, RenderJobSpec


def test_default_audio_request() -> None:
    """Test AudioRequest with minimal required fields."""
    request = AudioRequest(scene_number=1)

    assert request.scene_number == 1
    assert request.duration_seconds == 0
    assert request.narration_text == ""
    assert request.voice_reference == ""
    assert request.background_music_reference == ""
    assert request.sound_effect_references == []
    assert request.audio_format == "aac"


def test_custom_audio_request() -> None:
    """Test AudioRequest with all fields set."""
    request = AudioRequest(
        scene_number=2,
        duration_seconds=15,
        narration_text="Hello world",
        voice_reference="voice/en-us-female",
        background_music_reference="music/upbeat",
        sound_effect_references=["sfx/whoosh", "sfx/ding"],
        audio_format="aac",
    )

    assert request.scene_number == 2
    assert request.duration_seconds == 15
    assert request.narration_text == "Hello world"
    assert request.voice_reference == "voice/en-us-female"
    assert request.background_music_reference == "music/upbeat"
    assert request.sound_effect_references == ["sfx/whoosh", "sfx/ding"]
    assert request.audio_format == "aac"


def test_scene_number_validation() -> None:
    """Test that invalid scene numbers are rejected."""
    with pytest.raises(ValueError, match="scene_number must be positive"):
        AudioRequest(scene_number=0)

    with pytest.raises(ValueError, match="scene_number must be positive"):
        AudioRequest(scene_number=-1)


def test_duration_validation() -> None:
    """Test that negative duration is rejected."""
    with pytest.raises(ValueError, match="duration_seconds cannot be negative"):
        AudioRequest(scene_number=1, duration_seconds=-5)


def test_audio_format_validation() -> None:
    """Test that empty audio format is rejected."""
    with pytest.raises(ValueError, match="audio_format cannot be empty"):
        AudioRequest(scene_number=1, audio_format="  ")


def test_sound_effect_list_default() -> None:
    """Test that sound effects default to an empty list."""
    request = AudioRequest(scene_number=1)

    assert request.sound_effect_references == []
    assert isinstance(request.sound_effect_references, list)


def test_custom_sound_effects() -> None:
    """Test that custom sound effects are preserved."""
    request = AudioRequest(
        scene_number=1,
        sound_effect_references=["sfx/explosion", "sfx/click"],
    )

    assert request.sound_effect_references == ["sfx/explosion", "sfx/click"]


def test_serialization() -> None:
    """Test that AudioRequest serializes correctly."""
    request = AudioRequest(
        scene_number=3,
        duration_seconds=20,
        narration_text="Narration text",
        voice_reference="voice/male-deep",
        background_music_reference="music/cinematic",
        sound_effect_references=["sfx/whoosh"],
        audio_format="aac",
    )

    data = request.to_dict()

    assert data == {
        "scene_number": 3,
        "duration_seconds": 20,
        "narration_text": "Narration text",
        "voice_reference": "voice/male-deep",
        "background_music_reference": "music/cinematic",
        "sound_effect_references": ["sfx/whoosh"],
        "audio_format": "aac",
    }


def test_optional_audio_request_backward_compatible() -> None:
    """Test that RenderJobSpec works without an audio_request."""
    spec = RenderJobSpec(
        job_id="job-1",
        scene_number=1,
        duration_seconds=10,
        render_type="host_footage",
        character_ids=[],
        asset_ids=[],
        visual_prompt="visual",
        animation_instructions="animate",
        camera_instructions="camera",
        audio_requirements="Narration: Hello",
    )

    assert spec.audio_request is None

    # With audio_request attached
    audio = AudioRequest(scene_number=1, duration_seconds=10)
    spec_with_audio = RenderJobSpec(
        job_id="job-2",
        scene_number=2,
        duration_seconds=10,
        render_type="host_footage",
        character_ids=[],
        asset_ids=[],
        visual_prompt="visual",
        animation_instructions="animate",
        camera_instructions="camera",
        audio_requirements="Narration: Hi",
        audio_request=audio,
    )

    assert spec_with_audio.audio_request is audio
    assert spec_with_audio.audio_request.scene_number == 1


def test_deterministic_repeated_serialization() -> None:
    """Test that repeated serialization is deterministic."""
    request = AudioRequest(
        scene_number=1,
        duration_seconds=10,
        narration_text="Test",
    )

    data1 = request.to_dict()
    data2 = request.to_dict()

    assert data1 == data2