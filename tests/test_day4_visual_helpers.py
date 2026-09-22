"""Day-4 tests (part 1): Visual planner helpers.

Covers: camera selection avoiding repetition, transition selection by
beat-pair and emphasis, state-change diffing, forced changes, duration
scaling, and rotation helpers.
"""
from __future__ import annotations

from src.orchestration.schemas.visual_beat import VisualState
from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.services.visual_beat_planner import (
    _compute_changes,
    _force_changes,
    _pick_camera,
    _recommend_transition,
    _rotate_action,
    _rotate_emotion,
    _scale_durations,
)


def test_pick_camera_avoids_repetition():
    chosen = _pick_camera("EXPLANATION", "low", "static")
    assert chosen != "static"


def test_pick_camera_pools_valid():
    for emphasis in ("high", "medium", "low"):
        chosen = _pick_camera("HOOK", emphasis, "nonexistent")
        assert chosen in SUPPORTED_CAMERA_PATTERNS


def test_recommend_transition_low_emphasis_is_cut():
    t_type, dur = _recommend_transition("PROBLEM", "EXPLANATION", "low")
    assert t_type == "cut"
    assert dur == 0.3


def test_recommend_transition_problem_solution():
    t_type, dur = _recommend_transition("PROBLEM", "SOLUTION", "high")
    assert t_type == "slide_up"
    assert dur == 0.8


def test_compute_changes_detects_all_dimensions():
    prev = VisualState()
    new = VisualState(
        character_action="wave", character_emotion="happy",
        character_pose="wave", camera_pattern="slow_zoom_in",
        environment="office", objects=["calendar"],
    )
    changes = _compute_changes(prev, new)
    assert set(changes) == {"action", "emotion", "pose", "camera",
                            "environment", "objects"}


def test_compute_changes_empty_when_identical():
    prev = VisualState()
    assert _compute_changes(prev, VisualState()) == []


def test_force_changes_differs_from_previous():
    prev = VisualState(character_action="talk", character_emotion="neutral")
    action, emotion = _force_changes(prev, "talk", "neutral")
    assert action != prev.character_action
    assert emotion != prev.character_emotion


def test_rotate_action_differs():
    assert _rotate_action("talk") != "talk"


def test_rotate_emotion_differs():
    assert _rotate_emotion("neutral") != "neutral"


def test_scale_durations_preserves_total():
    result = _scale_durations(30, 3, "high")
    assert sum(result) == 30
    assert all(d >= 3 for d in result)


def test_scale_durations_single():
    result = _scale_durations(10, 1, "low")
    assert result == [10]
