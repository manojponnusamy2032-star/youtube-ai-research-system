"""Focused tests for the Transition model, validation, and assembly."""
from __future__ import annotations

import pytest

from src.models.content_package import SUPPORTED_TRANSITION_TYPES, MotionIntent, Transition
from src.services.video_assembler import VideoAssembler


def _out(num: int, transition=None) -> dict:
    record = {
        "job_id": f"scene-{num}",
        "scene_number": num,
        "status": "completed",
        "output_reference": f"scene_{num}.mp4",
        "duration_seconds": 2,
    }
    if transition is not None:
        record["transition_to_next"] = transition
    return record


# --- Transition model ---

def test_cut_defaults_to_zero_duration() -> None:
    t = Transition(type="cut")
    assert t.type == "cut" and t.duration == 0.0 and t.parameters == {}


def test_cut_forces_zero_duration() -> None:
    assert Transition(type="cut", duration=5.0).duration == 0.0


def test_all_eight_transition_types_supported() -> None:
    assert SUPPORTED_TRANSITION_TYPES == {
        "cut", "crossfade", "fade", "fade_to_black",
        "slide_left", "slide_right", "slide_up", "slide_down",
    }


def test_unknown_type_rejected() -> None:
    with pytest.raises(ValueError, match="unknown transition type"):
        Transition(type="teleport")


def test_type_lowercased() -> None:
    assert Transition(type="CrossFade", duration=0.5).type == "crossfade"


def test_non_cut_zero_duration_rejected() -> None:
    with pytest.raises(ValueError, match="duration must be positive"):
        Transition(type="crossfade", duration=0.0)


def test_negative_duration_rejected() -> None:
    with pytest.raises(ValueError, match="duration must be positive"):
        Transition(type="fade", duration=-1.0)


def test_parameters_must_be_dict() -> None:
    with pytest.raises(ValueError, match="parameters must be a dictionary"):
        Transition(type="fade", duration=0.5, parameters="bad")  # type: ignore[arg-type]


def test_to_dict() -> None:
    assert Transition(type="crossfade", duration=0.5, parameters={"curve": "smooth"}).to_dict() == {
        "type": "crossfade", "duration": 0.5, "parameters": {"curve": "smooth"},
    }


# --- Validation ---

def test_cut_ignores_max_duration() -> None:
    Transition(type="cut").validate(max_duration=1.0)


def test_non_cut_within_max_passes() -> None:
    Transition(type="crossfade", duration=0.5).validate(max_duration=2.0)


def test_non_cut_over_max_rejected() -> None:
    with pytest.raises(ValueError, match="transition duration exceeds"):
        Transition(type="crossfade", duration=2.5).validate(max_duration=2.0)


def test_non_cut_at_max_passes() -> None:
    Transition(type="fade", duration=2.0).validate(max_duration=2.0)


# --- Legacy compatibility (default cut) ---

def test_no_transition_uses_concat() -> None:
    result = VideoAssembler().assemble([_out(1), _out(2)])
    assert result["status"] == "command_built"
    assert "filter_complex" not in result
    assert "concat" in result["command"]


def test_empty_string_transition_defaults_to_cut() -> None:
    result = VideoAssembler().assemble([_out(1, ""), _out(2)])
    assert "filter_complex" not in result


def test_string_transition_normalized_with_default_duration() -> None:
    result = VideoAssembler().assemble([_out(1, "crossfade"), _out(2)])
    assert "xfade" in result["filter_complex"]
    plan = result["transition_plan"][0]["transition_to_next"]
    assert plan["type"] == "crossfade" and plan["duration"] == 0.25


def test_invalid_transition_rejected() -> None:
    with pytest.raises(ValueError, match="transition_to_next must be"):
        VideoAssembler().assemble([_out(1, 123), _out(2)])  # type: ignore[arg-type]


# --- Multiple scene transitions ---

def test_deterministic_multi_transition_plan() -> None:
    outputs = [
        _out(1, {"type": "crossfade", "duration": 0.25, "parameters": {}}),
        _out(2, {"type": "slide_left", "duration": 0.25, "parameters": {}}),
        _out(3),
    ]
    a = VideoAssembler().assemble(outputs)
    b = VideoAssembler().assemble(outputs)
    assert a["command"] == b["command"]
    assert len(a["transition_plan"]) == 2
    assert a["transition_plan"][0]["transition_to_next"]["type"] == "crossfade"
    assert a["transition_plan"][1]["transition_to_next"]["type"] == "slide_left"


def test_final_scene_has_no_outgoing_transition() -> None:
    result = VideoAssembler().assemble([
        _out(1, {"type": "crossfade", "duration": 0.25, "parameters": {}}),
        _out(2),
    ])
    assert len(result["transition_plan"]) == 1
    assert result["transition_plan"][0]["scene_number"] == 1


# --- Scene-aware selection (roles) ---

def test_scene_aware_transition_by_role() -> None:
    from unittest.mock import MagicMock
    from src.services.content_generation_service import ContentGenerationService
    svc = ContentGenerationService(MagicMock())

    def intent(role: str) -> MotionIntent:
        return MotionIntent(scene_role=role, primary_focus="scene", camera_pattern="hold", energy="medium")

    cases = [
        ("hook", "explanation", "crossfade"),
        ("explanation", "explanation", "cut"),
        ("explanation", "proof", "crossfade"),
        ("proof", "cta", "fade_to_black"),
        ("explanation", "comparison", "slide_up"),
        ("explanation", "cta", "fade"),
        ("b_roll", "explanation", "crossfade"),
    ]
    for cur, nxt, expected in cases:
        t = svc._default_transition_to_next(
            scene_number=2, total_scenes=5,
            current_intent=intent(cur), next_intent=intent(nxt),
        )
        assert t is not None, f"{cur}->{nxt}"
        assert t.type == expected, f"{cur}->{nxt}: got {t.type}, want {expected}"


def test_no_repeated_non_cut_transition() -> None:
    from unittest.mock import MagicMock
    from src.services.content_generation_service import ContentGenerationService
    svc = ContentGenerationService(MagicMock())

    def intent(role: str) -> MotionIntent:
        return MotionIntent(scene_role=role, primary_focus="scene", camera_pattern="hold", energy="medium")

    first = svc._default_transition_to_next(
        scene_number=2, total_scenes=5,
        current_intent=intent("explanation"), next_intent=intent("comparison"),
        previous_transition_type="cut",
    )
    second = svc._default_transition_to_next(
        scene_number=3, total_scenes=5,
        current_intent=intent("explanation"), next_intent=intent("comparison"),
        previous_transition_type=first.type if first else "cut",
    )
    assert first is not None and second is not None
    assert first.type == "slide_up"
    assert second.type == "slide_down"
    assert first.type != second.type
