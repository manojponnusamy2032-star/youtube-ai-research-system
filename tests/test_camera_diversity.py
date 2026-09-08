"""Focused unit tests for the V1.6-G camera diversity layer."""

from __future__ import annotations

import copy

import pytest

import src.services.camera_diversity as camera_div


def _camera_spec(pattern="slow_zoom_in", focus_target="hero", **overrides):
    spec = {"pattern": pattern, "focus_target": focus_target, "duration": 4.0, "easing": "ease_in_out"}
    spec.update(overrides)
    return spec


def _desc(camera=None, characters=None, objects=None):
    d = {}
    if camera is not None:
        d["camera"] = camera
    if characters is not None:
        d["characters"] = characters
    if objects is not None:
        d["objects"] = objects
    return d


@pytest.fixture
def enable(monkeypatch):
    monkeypatch.setattr(camera_div, "VISUAL_CAMERA_DIVERSITY_ENABLED", True)


# ---------------------------------------------------------------------------
# 1. Feature flag
# ---------------------------------------------------------------------------


def test_flag_defaults_off():
    import importlib

    module = importlib.import_module("src.services.camera_diversity")
    importlib.reload(module)
    assert module.VISUAL_CAMERA_DIVERSITY_ENABLED is False


def test_off_returns_description_unchanged():
    desc = _desc(camera=_camera_spec())
    result = camera_div.apply_camera_diversity(desc, scene_index=0)
    assert result.visual_description is desc
    assert result.decision.skipped is True
    assert result.decision.changed is False


def test_off_never_mutates_input():
    desc = _desc(camera=_camera_spec())
    snapshot = copy.deepcopy(desc)
    camera_div.apply_camera_diversity(desc, scene_index=0)
    assert desc == snapshot


# ---------------------------------------------------------------------------
# 2. G4: attention-target safety (placeholder focus_target)
# ---------------------------------------------------------------------------


def test_g4_placeholder_character_focus_cleared(enable):
    desc = _desc(camera=_camera_spec("focus_on_character", "character"))
    result = camera_div.apply_camera_diversity(desc, scene_index=0, cast=["hero"])
    assert result.decision.focus_target == ""
    assert result.decision.pattern == "focus_on_character"


def test_g4_placeholder_empty_focus_cleared(enable):
    desc = _desc(camera=_camera_spec("focus_on_object", ""))
    result = camera_div.apply_camera_diversity(desc, scene_index=0, cast=["hero"])
    assert result.decision.focus_target == ""


def test_g4_real_focus_target_preserved(enable):
    desc = _desc(camera=_camera_spec("focus_on_character", "hero"))
    result = camera_div.apply_camera_diversity(desc, scene_index=0, cast=["hero"])
    assert result.decision.focus_target == "hero"


def test_g4_no_pattern_change_when_focus_cleared(enable):
    desc = _desc(camera=_camera_spec("focus_on_character", "character"))
    result = camera_div.apply_camera_diversity(desc, scene_index=0, cast=["hero"])
    assert result.decision.pattern == "focus_on_character"
    assert result.decision.changed is False


# ---------------------------------------------------------------------------
# 3. G1: camera diversity
# ---------------------------------------------------------------------------


def test_g1_repeated_pattern_switches(enable):
    desc = _desc(camera=_camera_spec("slow_zoom_in"))
    result = camera_div.apply_camera_diversity(
        desc, scene_index=2, scene_role="explanation",
        previous_camera_patterns=("slow_zoom_in", "slow_zoom_in"),
    )
    assert result.decision.changed is True
    assert result.decision.pattern != "slow_zoom_in"
    assert "diversity" in result.decision.reason


def test_g1_single_occurrence_stays(enable):
    desc = _desc(camera=_camera_spec("slow_zoom_in"))
    result = camera_div.apply_camera_diversity(
        desc, scene_index=0, scene_role="hook",
        previous_camera_patterns=(),
    )
    assert result.decision.pattern == "slow_zoom_in"
    assert result.decision.changed is False


def test_g1_static_never_changes(enable):
    desc = _desc(camera=_camera_spec("static"))
    result = camera_div.apply_camera_diversity(
        desc, scene_index=5, scene_role="hook",
        previous_camera_patterns=("static", "static", "static"),
    )
    assert result.decision.pattern == "static"
    assert result.decision.changed is False


def test_g1_role_aware_alternative(enable):
    desc = _desc(camera=_camera_spec("slow_zoom_in"))
    result = camera_div.apply_camera_diversity(
        desc, scene_index=2, scene_role="contrast",
        previous_camera_patterns=("slow_zoom_in", "slow_zoom_in"),
    )
    assert result.decision.pattern != "slow_zoom_in"


def test_g1_deterministic(enable):
    desc = _desc(camera=_camera_spec("slow_zoom_in"))
    r1 = camera_div.apply_camera_diversity(
        desc, scene_index=2, scene_role="explanation",
        previous_camera_patterns=("slow_zoom_in", "slow_zoom_in"),
    )
    r2 = camera_div.apply_camera_diversity(
        desc, scene_index=2, scene_role="explanation",
        previous_camera_patterns=("slow_zoom_in", "slow_zoom_in"),
    )
    assert r1.decision.to_dict() == r2.decision.to_dict()


# ---------------------------------------------------------------------------
# 4. G3: activity hint
# ---------------------------------------------------------------------------


def test_g3_activity_hint_values():
    assert camera_div._activity_hint("hook", 1) == "medium"
    assert camera_div._activity_hint("hook", 2) == "high"
    assert camera_div._activity_hint("explanation", 1) == "medium"
    assert camera_div._activity_hint("general", 1) == "low"


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------


def test_invalid_input_non_dict(enable):
    result = camera_div.apply_camera_diversity(None, scene_index=0)
    assert result.decision.skipped is True


def test_no_camera_spec(enable):
    desc = _desc()
    result = camera_div.apply_camera_diversity(desc, scene_index=0)
    assert result.decision.pattern == "static"


def test_sequence_flag_off_returns_same_objects(monkeypatch):
    monkeypatch.setattr(camera_div, "VISUAL_CAMERA_DIVERSITY_ENABLED", False)
    descs = [_desc(camera=_camera_spec()), _desc(camera=_camera_spec())]
    result, report = camera_div.apply_camera_diversity_sequence(descs, scene_roles=["hook", "problem"])
    assert result[0] is descs[0]
    assert result[1] is descs[1]
    assert report.enabled is False
    assert report.applied_count == 0