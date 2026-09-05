"""Focused unit tests for the V1.6-D camera execution layer.

Covers feature-flag gating (default off), explicit camera preservation, V1.4
camera/story decision consumption, zoom/pan execution, focal-point handling,
bounds and safety, invalid/missing camera metadata fallback, multi-element and
empty scenes, scene-role fallback, camera continuity between consecutive
scenes, compatibility with the earlier V1.6 family layers, determinism, and
unchanged renderer behavior when the flag is OFF.
"""

from __future__ import annotations

import copy
import math

from src.models.content_package import Motion
from src.services.scene_composition import CameraSpec, SUPPORTED_CAMERA_PATTERNS
import src.services.camera_execution as camera_module
from src.services.camera_execution import (
    apply_camera_execution,
    apply_camera_execution_sequence,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _characters(*names: str) -> list[dict]:
    return [
        {"name": name, "x": 0.3 + 0.2 * i, "y": 0.7}
        for i, name in enumerate(names)
    ]


def _objects(*names: str) -> list[dict]:
    return [{"name": name, "type": "book", "x": 0.6, "y": 0.8} for name in names]


def _description(**overrides: object) -> dict:
    desc: dict = {"characters": _characters("hero"), "objects": [], "camera": {}}
    desc.update(overrides)
    return desc


def _planning_metadata(
    pattern: str | None = None,
    focus_target: str | None = None,
    *,
    attention_target: str | None = None,
    recommended_camera: str | None = None,
) -> dict:
    metadata: dict = {"scene_index": 0}
    if pattern is not None or focus_target is not None:
        camera_meta: dict = {}
        if pattern is not None:
            camera_meta["recommended_pattern"] = pattern
        if focus_target is not None:
            camera_meta["focus_target"] = focus_target
        metadata["camera"] = camera_meta
    if attention_target is not None:
        metadata["attention"] = {"primary_target": attention_target}
    if recommended_camera is not None:
        metadata["recommended_camera"] = recommended_camera
    return metadata


def _camera_motion() -> Motion:
    return Motion(
        type="zoom",
        target="camera",
        start_time=0.0,
        duration=1.0,
        parameters={"from": 1.0, "to": 1.2},
    )


def _decision_dict(decision: camera_module.CameraExecutionDecision) -> dict:
    return decision.to_dict()


# ---------------------------------------------------------------------------
# 1. Feature flag OFF preserves existing behavior
# ---------------------------------------------------------------------------


def test_flag_default_is_off() -> None:
    assert camera_module.VISUAL_CAMERA_EXECUTION_ENABLED is False


def test_flag_off_preserves_description(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", False)
    desc = _description(camera={"pattern": "pan_left"})
    original = copy.deepcopy(desc)
    new, decision = apply_camera_execution(
        desc, scene_index=0, scene_role="hook", duration=4.0
    )
    # Same content, no camera_execution key, no camera mutation.
    assert new == original
    assert "camera_execution" not in new
    assert new["camera"]["pattern"] == "pan_left"
    assert decision.skipped is True


def test_flag_off_sequence_returns_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", False)
    descs = [
        _description(camera={"pattern": "pan_right"}),
        _description(camera={}),
    ]
    new_descs, report = apply_camera_execution_sequence(descs)
    assert new_descs == descs
    assert report.enabled is False
    assert report.applied_count == 0
    assert report.skipped_count == 2


def test_flag_off_renderer_behavior_unchanged(monkeypatch) -> None:
    """OFF must not write any camera spec the renderer would newly execute."""
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", False)
    # The default scene has no camera -> renderer keeps its static default.
    desc = {"characters": _characters("hero")}
    new, decision = apply_camera_execution(
        desc, scene_index=0, scene_role="explanation", duration=4.0
    )
    assert decision.skipped is True
    assert "camera" not in new or new["camera"] == {}


# ---------------------------------------------------------------------------
# 2. Feature flag ON executes valid camera decisions
# ---------------------------------------------------------------------------


def test_flag_on_executes_planning_zoom(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(camera={})
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        scene_role="hook",
        duration=4.0,
        planning_metadata=_planning_metadata("slow_zoom_in", focus_target="hero"),
    )
    assert decision.changed is True
    executed = new["camera"]
    assert executed["pattern"] == "slow_zoom_in"
    assert executed["pattern"] in camera_module.SUPPORTED_CAMERA_PATTERNS
    assert executed["easing"] == "ease_in_out"
    assert 0.4 <= float(executed["duration"]) <= 4.0
    # Planner decision remains authoritative -> executed pattern equals it.
    metadata = _decision_dict(decision)
    assert metadata["pattern"] == "slow_zoom_in"
    assert metadata["source"] == "v14_camera_decision"


# ---------------------------------------------------------------------------
# 3. Deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_repeated_execution(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(camera={})
    kwargs = {
        "scene_index": 2,
        "scene_role": "comparison",
        "duration": 5.0,
        "planning_metadata": _planning_metadata(
            None, None, recommended_camera="pan_left"
        ),
    }
    first, first_decision = apply_camera_execution(desc, **kwargs)
    second, second_decision = apply_camera_execution(desc, **kwargs)
    assert first == second
    assert _decision_dict(first_decision) == _decision_dict(second_decision)


def test_sequence_is_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    descs = [_description(camera={}) for _ in range(3)]
    roles = ["hook", "explanation", "comparison"]
    first, first_report = apply_camera_execution_sequence(
        descs, scene_roles=roles, durations=[4.0, 4.0, 4.0]
    )
    second, second_report = apply_camera_execution_sequence(
        descs, scene_roles=roles, durations=[4.0, 4.0, 4.0]
    )
    assert first == second
    assert first_report.to_dict() == second_report.to_dict()

# ---------------------------------------------------------------------------
# 4. Explicit camera instructions are preserved
# ---------------------------------------------------------------------------


def test_explicit_camera_spec_preserved(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(camera={"pattern": "pan_left", "focus_target": "hero"})
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        scene_role="hook",
        duration=4.0,
        planning_metadata=_planning_metadata("slow_zoom_in", "hero"),
    )
    assert new["camera"]["pattern"] == "pan_left"
    assert decision.changed is False
    assert "explicit_camera_preserved" in decision.warnings


def test_explicit_camera_motion_deferred(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(camera={})
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        camera_motions=[_camera_motion()],
        planning_metadata=_planning_metadata("slow_zoom_in", "hero"),
    )
    # The renderer executes the camera Motion and suppresses the declarative
    # spec; the execution layer must not write one.
    assert "camera" not in new or new["camera"] == {}
    assert decision.skipped is True
    assert "explicit_camera_motion_preserved" in decision.warnings


# ---------------------------------------------------------------------------
# 5. V1.4/V1.5 camera decisions are correctly consumed
# ---------------------------------------------------------------------------


def test_v14_camera_decision_consumed(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("pan_right", focus_target="hero"),
    )
    assert new["camera"]["pattern"] == "pan_right"
    assert decision.source == "v14_camera_decision"


def test_v14_story_recommendation_consumed(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata(recommended_camera="slow_zoom_out"),
    )
    assert new["camera"]["pattern"] == "slow_zoom_out"
    assert decision.source == "v14_story_recommendation"


# ---------------------------------------------------------------------------
# 6/7. Zoom in / zoom out execution
# ---------------------------------------------------------------------------


def test_zoom_in_execution(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, _ = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("slow_zoom_in"),
    )
    assert new["camera"]["pattern"] == "slow_zoom_in"
    assert float(new["camera"]["duration"]) >= 0.4


def test_zoom_out_execution(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, _ = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("slow_zoom_out"),
    )
    assert new["camera"]["pattern"] == "slow_zoom_out"


# ---------------------------------------------------------------------------
# 8. Pan execution
# ---------------------------------------------------------------------------


def test_pan_execution(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, _ = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("pan_left"),
    )
    assert new["camera"]["pattern"] == "pan_left"

# ---------------------------------------------------------------------------
# 9. Focal-point handling
# ---------------------------------------------------------------------------


def test_focus_pattern_resolves_character(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "hero"),
    )
    assert new["camera"]["pattern"] == "focus_on_character"
    assert new["camera"]["focus_target"] == "hero"


def test_focus_pattern_resolves_object(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(
        characters=_characters("hero"), objects=_objects("clock"), camera={}
    )
    new, _ = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_object", "clock"),
    )
    assert new["camera"]["pattern"] == "focus_on_object"
    assert new["camera"]["focus_target"] == "clock"


def test_attention_target_resolves_focus(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, _ = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata(
            "focus_on_character", attention_target="hero"
        ),
    )
    assert new["camera"]["focus_target"] == "hero"


def test_explicit_focus_target_beats_planning(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(
        characters=_characters("hero", "sidekick"),
        camera={"focus_target": "sidekick"},
    )
    new, _ = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "hero"),
    )
    assert new["camera"]["focus_target"] == "sidekick"


def test_unresolvable_focus_downgrades_safely(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(characters=_characters("hero"), camera={})
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "ghost"),
    )
    assert new["camera"]["pattern"] == "slow_zoom_in"
    assert "focus_target_unresolvable" in decision.warnings


# ---------------------------------------------------------------------------
# 10. Camera bounds and safety
# ---------------------------------------------------------------------------


def test_patterns_are_from_supported_vocabulary(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(camera={})
    new, _ = apply_camera_execution(
        desc,
        scene_index=0,
        scene_role="hook",
        duration=4.0,
        planning_metadata=_planning_metadata("slow_zoom_in"),
    )
    assert new["camera"]["pattern"] in SUPPORTED_CAMERA_PATTERNS


def test_duration_is_bounded_and_finite(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    for duration in (0.0, -3.0, float("nan"), float("inf"), 1000.0):
        new, _ = apply_camera_execution(
            _description(camera={}),
            scene_index=0,
            duration=duration,
            planning_metadata=_planning_metadata("slow_zoom_in"),
        )
        value = float(new["camera"]["duration"])
        assert math.isfinite(value)
        assert 0.0 < value


def test_never_emits_unsupported_patterns(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("warp_speed"),
    )
    assert new["camera"]["pattern"] == "static"
    assert decision.source == "safe_fallback"


# ---------------------------------------------------------------------------
# 11-12. Invalid / missing camera metadata safely falls back
# ---------------------------------------------------------------------------


def test_invalid_planning_metadata_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(
        _description(camera={}),
        scene_index=0,
        scene_role="",
        duration=4.0,
        planning_metadata={"camera": {"recommended_pattern": "explode"}},
    )
    assert new["camera"]["pattern"] == "static"
    assert decision.changed is True
    assert decision.source == "safe_fallback"


def test_missing_planning_metadata_uses_scene_fallback(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(
        _description(camera={}), scene_index=0, scene_role="hook", duration=4.0
    )
    assert decision.changed is True
    assert new["camera"]["pattern"] in SUPPORTED_CAMERA_PATTERNS


def test_missing_camera_and_planning_falls_back_to_static(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(
        _description(camera={}), scene_index=0, scene_role="unknown", duration=4.0
    )
    assert new["camera"]["pattern"] == "static"
    assert decision.source == "safe_fallback"


def test_none_description_is_safe(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, decision = apply_camera_execution(None, scene_index=0, duration=4.0)
    assert isinstance(new, dict)
    assert new["camera"]["pattern"] == "static"

# ---------------------------------------------------------------------------
# 13-16. Multi-element and empty scenes
# ---------------------------------------------------------------------------


def test_single_character_scene(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(characters=_characters("hero"), camera={})
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "hero"),
    )
    assert new["camera"]["pattern"] == "focus_on_character"
    assert new["camera"]["focus_target"] == "hero"
    assert decision.changed is True


def test_multi_character_scene(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(characters=_characters("hero", "coach", "student"), camera={})
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "coach"),
    )
    assert new["camera"]["focus_target"] == "coach"
    assert decision.changed is True


def test_character_and_object_scene(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(
        characters=_characters("hero"),
        objects=_objects("clock", "notebook"),
        camera={},
    )
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_object", "notebook"),
    )
    assert new["camera"]["pattern"] == "focus_on_object"
    assert new["camera"]["focus_target"] == "notebook"
    assert decision.changed is True


def test_empty_visual_scene_safe(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc: dict = {"characters": [], "objects": [], "camera": {}}
    new, decision = apply_camera_execution(
        desc, scene_index=0, scene_role="hook", duration=4.0
    )
    assert new["camera"]["pattern"] in SUPPORTED_CAMERA_PATTERNS
    assert decision.changed is True


def test_focus_on_empty_scene_degrades_gracefully(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc: dict = {"characters": [], "objects": [], "camera": {}}
    new, decision = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "ghost"),
    )
    assert new["camera"]["pattern"] == "slow_zoom_in"
    assert "focus_target_unresolvable" in decision.warnings


# ---------------------------------------------------------------------------
# 17. Camera continuity between consecutive scenes
# ---------------------------------------------------------------------------


def test_sequence_continuity_avoids_reversal(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    descs = [_description(camera={}) for _ in range(3)]
    roles = ["comparison", "comparison", "comparison"]
    new_descs, report = apply_camera_execution_sequence(
        descs, scene_roles=roles, durations=[4.0, 4.0, 4.0]
    )
    patterns = [desc["camera"]["pattern"] for desc in new_descs]
    # pan_left at index 0 must not be directly followed by pan_right.
    assert patterns[0] == "pan_left"
    assert patterns[1] in {"static", "pan_left", "slow_zoom_in"}
    assert report.applied_count == 3


def test_previous_camera_passed_into_next_scene(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    seen: list[dict | None] = []

    def spy(desc, **kwargs):
        seen.append(kwargs.get("previous_camera"))
        return apply_camera_execution(desc, **kwargs)

    monkeypatch.setattr(camera_module, "apply_camera_execution", spy)
    descs = [_description(camera={}) for _ in range(2)]
    apply_camera_execution_sequence(
        descs, scene_roles=["hook", "comparison"], durations=[4.0, 4.0]
    )
    assert seen[0] is None
    assert seen[1] is not None


def test_continuity_does_not_overwrite_planning(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    descs = [_description(camera={}) for _ in range(2)]
    planning = [None, _planning_metadata("pan_left")]
    new_descs, _ = apply_camera_execution_sequence(
        descs,
        planning,
        scene_roles=["hook", "comparison"],
        durations=[4.0, 4.0],
    )
    # The V1.4 decision (pan_left) is honored even though the previous scene
    # also picked pan_left (continuity must not rewrite planner output).
    assert new_descs[1]["camera"]["pattern"] == "pan_left"


# ---------------------------------------------------------------------------
# 18. Produced camera spec is renderer-executable
# ---------------------------------------------------------------------------


def test_produced_camera_is_renderer_executable(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    new, _ = apply_camera_execution(
        _description(characters=_characters("hero"), camera={}),
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "hero"),
    )
    # CameraSpec accepts the documented fields the renderer consumes.
    spec = CameraSpec(**new["camera"])
    assert spec.pattern == "focus_on_character"
    assert spec.focus_target == "hero"
    assert spec.easing == "ease_in_out"

# ---------------------------------------------------------------------------
# 19-21. V1.6-A / V1.6-B / V1.6-C compatibility
# ---------------------------------------------------------------------------


def test_compatible_with_v16a_background_variation(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    # V1.6-A writes environment + a decision key; V1.6-D must not touch it.
    desc = _description(
        characters=_characters("hero"),
        objects=_objects("clock"),
        camera={},
        environment={"type": "classroom"},
        background_variation={"changed": True, "assigned_type": "classroom"},
    )
    new, _ = apply_camera_execution(desc, scene_index=0, scene_role="hook", duration=4.0)
    assert new["environment"]["type"] == "classroom"
    assert new["background_variation"]["changed"] is True
    assert new["camera"]["pattern"] in SUPPORTED_CAMERA_PATTERNS


def test_camera_uses_v16b_varied_characters(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(
        characters=_characters("hero", "guide"),
        camera={},
        character_variation={"changed": True, "position_variations": ["guide"]},
    )
    new, _ = apply_camera_execution(
        desc,
        scene_index=0,
        duration=4.0,
        planning_metadata=_planning_metadata("focus_on_character", "guide"),
    )
    assert new["character_variation"]["changed"] is True
    assert new["camera"]["focus_target"] == "guide"


def test_camera_tolerates_v16c_motion_variation_metadata(monkeypatch) -> None:
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    desc = _description(
        characters=_characters("hero"),
        objects=_objects("clock"),
        camera={},
        motion_variation={
            "changed": True,
            "target_id": "hero",
            "motion_type": "scale",
        },
    )
    new, _ = apply_camera_execution(
        desc,
        scene_index=0,
        scene_role="hook",
        duration=4.0,
        camera_motions=[_camera_motion()],
    )
    # V1.6-C metadata survives; explicit camera motion still wins.
    assert new["motion_variation"]["changed"] is True
    assert "camera" not in new or new["camera"] == {}
