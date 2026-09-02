"""V1.5 visual planning application layer tests.

Covers flag gating, per-scene and sequence-level application, camera /
composition / attention safety policies (explicit-intent precedence, target
resolution, vocabulary validation), determinism, deep no-mutation, frozen
output, JSON serialization, and V1.4-A through F integration.
"""
from __future__ import annotations

import copy
import dataclasses
import json

import pytest

import src.services.visual_planning_application as app_module
from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.services.visual_planning_application import (
    VisualPlanningApplicationDecision,
    VisualPlanningApplicationReport,
    apply_visual_planning,
    apply_visual_planning_sequence,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _camera_decision(
    pattern: str = "static",
    focus_target: str | None = None,
    scene_index: int = 0,
) -> dict:
    return {
        "scene_index": scene_index,
        "recommended_pattern": pattern,
        "focus_target": focus_target,
        "continuity_from_previous": "established",
        "repeated_with_previous": False,
        "explicit_camera_preserved": False,
        "warnings": [],
    }


def _composition_decision(
    comp_type: str = "single_subject",
    scene_index: int = 0,
) -> dict:
    return {
        "scene_index": scene_index,
        "composition_type": comp_type,
        "primary_region": "center",
        "secondary_region": None,
        "text_region": "top",
        "subject_regions": ("center",),
        "recommended_scale": "medium",
        "recommended_alignment": "center",
        "repeated_with_previous": False,
        "warnings": [],
    }


def _attention_decision(
    primary_target: str | None = None,
    scene_index: int = 0,
) -> dict:
    return {
        "scene_index": scene_index,
        "primary_target": primary_target,
        "secondary_target": None,
        "target_kind": "character" if primary_target else None,
        "handoff_from_previous": "new",
        "handoff_to_next": "new",
        "retained_from_previous": False,
        "target_changed": True,
        "explicit_focus_preserved": False,
        "warnings": [],
    }


def _visual_planning(
    scene_index: int = 0,
    camera: dict | None = None,
    composition: dict | None = None,
    attention: dict | None = None,
    treatment: str = "establish",
) -> dict:
    """Build a V1.4-F ``visual_planning`` metadata dict.

    Only the channels explicitly supplied are included; a ``None`` channel is
    omitted so per-channel tests can exercise one policy in isolation.
    """
    vp: dict = {
        "scene_index": scene_index,
        "treatment": treatment,
        "recommended_motions": ["emphasize"],
        "recommended_camera": (camera or {}).get("recommended_pattern", ""),
        "recommended_transition": "crossfade",
        "diversity": {"scene_index": scene_index, "flags": ()},
    }
    if camera is not None:
        vp["camera"] = camera
    if composition is not None:
        vp["composition"] = composition
    if attention is not None:
        vp["attention"] = attention
    return vp


def _desc(
    characters: tuple[str, ...] = ("guide",),
    objects: tuple[str, ...] = (),
    camera: dict | None = None,
    x: float = 0.3,
    y: float = 0.7,
) -> dict:
    return {
        "characters": [
            {"name": name, "x": x + i * 0.1, "y": y, "scale": 1.0}
            for i, name in enumerate(characters)
        ],
        "objects": [
            {"name": name, "type": "brain", "x": 0.72, "y": 0.7, "scale": 1.0}
            for name in objects
        ],
        "text_elements": [{"text": "Headline", "size": "headline", "x": 0.5, "y": 0.12}],
        "environment": {"type": "study_desk"},
        "effects": [],
        "camera": dict(camera or {}),
    }


# ---------------------------------------------------------------------------
# 1. Empty sequence
# ---------------------------------------------------------------------------


def test_empty_sequence() -> None:
    new_descs, report = apply_visual_planning_sequence([], [])
    assert new_descs == []
    assert report.decisions == ()
    assert report.applied_count == 0
    assert report.skipped_count == 0
    assert report.warning_count == 0


# ---------------------------------------------------------------------------
# 2. Single scene
# ---------------------------------------------------------------------------


def test_single_scene(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",))
    vp = _visual_planning(
        0,
        camera=_camera_decision("focus_on_character", "guide"),
        attention=_attention_decision("guide"),
    )
    new_descs, report = apply_visual_planning_sequence([desc], [vp])
    assert len(new_descs) == 1
    assert dict(new_descs[0]) != dict(desc)  # staging inputs changed
    assert new_descs[0]["camera"]["pattern"] == "focus_on_character"
    assert new_descs[0]["camera"]["focus_target"] == "guide"
    assert report.applied_count == 1
    assert report.skipped_count == 0
    assert len(report.decisions) == 1
    assert report.decisions[0].changed is True


# ---------------------------------------------------------------------------
# 3. Multi-scene application
# ---------------------------------------------------------------------------


def test_multi_scene_application(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    descs = [
        _desc(characters=("guide",)),
        _desc(characters=("mentor",)),
        _desc(characters=("guide",)),
    ]
    vps = [
        _visual_planning(
            0,
            camera=_camera_decision("focus_on_character", "guide"),
            attention=_attention_decision("guide"),
        ),
        _visual_planning(
            1,
            camera=_camera_decision("pan_left"),
            attention=_attention_decision("mentor"),
        ),
        _visual_planning(
            2,
            camera=_camera_decision("static"),
            attention=_attention_decision("guide"),
        ),
    ]
    new_descs, report = apply_visual_planning_sequence(descs, vps)
    assert len(new_descs) == 3
    assert report.applied_count == 3
    assert report.skipped_count == 0
    assert [d.scene_index for d in report.decisions] == [0, 1, 2]
    assert new_descs[1]["camera"]["pattern"] == "pan_left"
    assert new_descs[2]["camera"]["focus_target"] == "guide"


# ---------------------------------------------------------------------------
# 4. Flag OFF behavior
# ---------------------------------------------------------------------------


def test_flag_off_behavior(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", False)
    descs = [_desc(characters=("guide",)), _desc(characters=("mentor",))]
    vps = [_visual_planning(0), _visual_planning(1)]
    new_descs, report = apply_visual_planning_sequence(descs, vps)
    # Returns the same objects (unchanged), in the same order.
    assert new_descs == descs
    assert report.enabled is False
    assert report.applied_count == 0
    assert report.skipped_count == 2
    assert report.decisions == ()


# ---------------------------------------------------------------------------
# 5. V1.4 disabled behavior
# ---------------------------------------------------------------------------


def test_v14_disabled_behavior(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    descs = [_desc(characters=("guide",)), _desc(characters=("mentor",))]
    # Empty visual_plannings == V1.4 never ran.
    new_descs, report = apply_visual_planning_sequence(descs, [])
    assert new_descs == descs
    assert report.enabled is True
    assert report.applied_count == 0
    assert report.skipped_count == 2
    assert "V1.4 did not run" in report.summary


# ---------------------------------------------------------------------------
# 6. Valid camera recommendation application
# ---------------------------------------------------------------------------


def test_valid_camera_recommendation_application(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",), objects=("clock",))
    vp = _visual_planning(
        0,
        camera=_camera_decision("focus_on_character", "guide"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.changed is True
    assert decision.camera_changed is True
    assert decision.applied_camera == "focus_on_character"
    assert new_desc["camera"]["pattern"] == "focus_on_character"
    assert new_desc["camera"]["focus_target"] == "guide"


# ---------------------------------------------------------------------------
# 7. Invalid camera target rejection
# ---------------------------------------------------------------------------


def test_invalid_camera_target_rejection(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",), objects=("clock",))
    vp = _visual_planning(
        0,
        camera=_camera_decision("focus_on_character", "ghost_character"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.changed is False
    assert decision.camera_changed is False
    assert any("not resolvable" in w for w in decision.warnings)
    assert new_desc["camera"] == desc["camera"]


# ---------------------------------------------------------------------------
# 8. Explicit camera preservation
# ---------------------------------------------------------------------------


def test_explicit_camera_preservation(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",), camera={"pattern": "slow_zoom_in"})
    vp = _visual_planning(
        0,
        camera=_camera_decision("pan_right"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.changed is False
    assert decision.camera_changed is False
    assert any("explicit camera preserved" in w for w in decision.warnings)
    assert new_desc["camera"]["pattern"] == "slow_zoom_in"


# ---------------------------------------------------------------------------
# 9. Valid composition application
# ---------------------------------------------------------------------------


def test_valid_composition_application(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",))
    vp = _visual_planning(
        0,
        composition=_composition_decision("single_subject"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.composition_changed is True
    assert decision.applied_composition == "single_subject"
    assert new_desc["recommended_composition"] == "single_subject"
    # Positions untouched.
    assert new_desc["characters"] == desc["characters"]


# ---------------------------------------------------------------------------
# 10. Incompatible composition rejection
# ---------------------------------------------------------------------------


def test_incompatible_composition_rejection(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",))  # only one subject
    vp = _visual_planning(
        0,
        composition=_composition_decision("comparison"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.composition_changed is False
    assert decision.changed is False
    assert any("comparison requires" in w for w in decision.warnings)
    assert "recommended_composition" not in new_desc
    assert new_desc["characters"] == desc["characters"]


# ---------------------------------------------------------------------------
# 11. Explicit positions preservation
# ---------------------------------------------------------------------------


def test_explicit_positions_preservation(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(
        characters=("guide", "mentor"),
        x=0.20, y=0.62,
    )
    original_positions = [
        (c["x"], c["y"]) for c in desc["characters"]
    ]
    vp = _visual_planning(
        0,
        composition=_composition_decision("comparison"),
        camera=_camera_decision("static"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert [(c["x"], c["y"]) for c in new_desc["characters"]] == original_positions
    # Explicit positions were never rearranged by composition.
    assert new_desc["characters"] == desc["characters"]


# ---------------------------------------------------------------------------
# 12. Valid attention application
# ---------------------------------------------------------------------------


def test_valid_attention_application(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",))
    vp = _visual_planning(
        0,
        camera=_camera_decision("static"),
        attention=_attention_decision("guide"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.attention_changed is True
    assert decision.applied_attention == "guide"
    assert new_desc["camera"]["focus_target"] == "guide"


# ---------------------------------------------------------------------------
# 13. Invalid attention target rejection
# ---------------------------------------------------------------------------


def test_invalid_attention_target_rejection(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",), objects=("clock",))
    vp = _visual_planning(
        0,
        attention=_attention_decision("ghost_target"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.attention_changed is False
    assert decision.changed is False
    assert any("not resolvable" in w for w in decision.warnings)
    assert "focus_target" not in new_desc["camera"]


# ---------------------------------------------------------------------------
# 14. Explicit focus preservation
# ---------------------------------------------------------------------------


def test_explicit_focus_preservation(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",), camera={"focus_target": "guide"})
    vp = _visual_planning(
        0,
        camera=_camera_decision("static"),
        attention=_attention_decision("mentor"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.attention_changed is False
    assert any("explicit focus preserved" in w for w in decision.warnings)
    assert new_desc["camera"]["focus_target"] == "guide"


# ---------------------------------------------------------------------------
# 15. No target invention
# ---------------------------------------------------------------------------


def test_no_target_invention(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",), objects=("clock",))
    vp = _visual_planning(
        0,
        camera=_camera_decision("focus_on_object", "nonexistent_prop"),
        attention=_attention_decision("ghost"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    # No invented target may reach the camera dict.
    applied_focus = new_desc["camera"].get("focus_target")
    assert applied_focus is None or applied_focus in {"guide", "clock"}


# ---------------------------------------------------------------------------
# 16. Deterministic repeated execution
# ---------------------------------------------------------------------------


def test_deterministic_repeated_execution(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    descs = [
        _desc(characters=("guide",)),
        _desc(characters=("mentor",)),
        _desc(characters=("guide",), objects=("clock",)),
    ]
    vps = [
        _visual_planning(0, camera=_camera_decision("focus_on_character", "guide")),
        _visual_planning(1, camera=_camera_decision("pan_left")),
        _visual_planning(2, camera=_camera_decision("focus_on_object", "clock")),
    ]
    first_out, first_report = apply_visual_planning_sequence(descs, vps)
    second_out, second_report = apply_visual_planning_sequence(descs, vps)
    assert first_out == second_out
    assert first_report.to_dict() == second_report.to_dict()
    # Stable ordering: decisions align with scene indices.
    assert [d.scene_index for d in first_report.decisions] == [0, 1, 2]


# ---------------------------------------------------------------------------
# 17. Deep no-mutation
# ---------------------------------------------------------------------------


def test_deep_no_mutation(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",), objects=("clock",), camera={"pattern": "static"})
    vp = _visual_planning(
        0,
        camera=_camera_decision("focus_on_character", "guide"),
        composition=_composition_decision("single_subject"),
        attention=_attention_decision("guide"),
    )
    desc_before = copy.deepcopy(desc)
    vp_before = copy.deepcopy(vp)

    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    # The input staging dict and planning metadata are untouched.
    assert desc == desc_before
    assert vp == vp_before
    # The new output is a distinct object graph.
    assert new_desc is not desc
    assert new_desc["camera"] is not desc["camera"]


# ---------------------------------------------------------------------------
# 18. Frozen / immutable output
# ---------------------------------------------------------------------------


def test_frozen_immutable_output(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",))
    vp = _visual_planning(0, camera=_camera_decision("pan_left"))
    _, decision = apply_visual_planning(desc, vp, scene_index=0)
    _, report = apply_visual_planning_sequence([desc], [vp])

    assert dataclasses.is_dataclass(decision)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.scene_index = 99  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.applied_count = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 19. JSON serialization
# ---------------------------------------------------------------------------


def test_json_serialization(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",))
    vp = _visual_planning(0, camera=_camera_decision("pan_left"))
    _, report = apply_visual_planning_sequence([desc], [vp])
    payload = report.to_dict()
    dumped = json.dumps(payload, sort_keys=True)
    assert json.loads(dumped)["applied_count"] == 1
    assert json.loads(dumped)["decisions"][0]["scene_index"] == 0


# ---------------------------------------------------------------------------
# 20. Supported vocabulary validation
# ---------------------------------------------------------------------------


def test_supported_vocabulary_validation(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    desc = _desc(characters=("guide",))
    vp = _visual_planning(0, camera=_camera_decision("warp_speed"))
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.camera_changed is False
    assert any("unsupported camera pattern" in w for w in decision.warnings)
    assert new_desc["camera"] == desc["camera"]


def test_all_applied_camera_patterns_from_supported_vocabulary(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    descs = [_desc(characters=("guide",)) for _ in range(4)]
    vps = [
        _visual_planning(i, camera=_camera_decision(p, "guide"))
        for i, p in enumerate(
            ["focus_on_character", "slow_zoom_in", "pan_right", "focus_on_character"]
        )
    ]
    new_descs, report = apply_visual_planning_sequence(descs, vps)
    for idx, desc in enumerate(new_descs):
        pattern = desc["camera"].get("pattern")
        if report.decisions[idx].camera_changed:
            assert pattern in SUPPORTED_CAMERA_PATTERNS


# ---------------------------------------------------------------------------
# 21. V1.4-A/B/C/D/E integration
# ---------------------------------------------------------------------------
# The real planner outputs serialize via to_dict() into exactly the dict
# shapes the application layer consumes (recommended_pattern/focus_target,
# composition_type, primary_target). Here we demonstrate the application
# layer is a pure function of those shapes.


def test_v14_planner_output_shape_integration(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    from src.services.attention_planner import AttentionDecision
    from src.services.camera_planner import CameraDecision
    from src.services.composition_planner import CompositionDecision
    from src.services.visual_story_planner import VisualStoryDecision

    story = VisualStoryDecision(
        scene_index=0,
        beat_type="HOOK",
        treatment="establish",
        focus_target="guide",
        camera_pattern="focus_on_character",
        preferred_motion_types=("emphasize",),
        transition_type="crossfade",
        repeated_with_previous=False,
        warnings=(),
    )
    composition = CompositionDecision(
        scene_index=0,
        composition_type="single_subject",
        primary_region="center",
        secondary_region=None,
        text_region="top",
        subject_regions=("center",),
        recommended_scale="medium",
        recommended_alignment="center",
        repeated_with_previous=False,
        warnings=(),
    )
    camera = CameraDecision(
        scene_index=0,
        recommended_pattern="focus_on_character",
        focus_target="guide",
        continuity_from_previous="established",
        repeated_with_previous=False,
        explicit_camera_preserved=False,
        warnings=(),
    )
    attention = AttentionDecision(
        scene_index=0,
        primary_target="guide",
        secondary_target=None,
        target_kind="character",
        handoff_from_previous="new",
        handoff_to_next="new",
        retained_from_previous=False,
        target_changed=True,
        explicit_focus_preserved=False,
        warnings=(),
    )

    visual_planning = {
        "scene_index": 0,
        "treatment": story.treatment,
        "recommended_camera": story.camera_pattern,
        "diversity": {"scene_index": 0, "flags": ()},
        "composition": composition.to_dict(),
        "camera": camera.to_dict(),
        "attention": attention.to_dict(),
    }
    desc = _desc(characters=("guide",))
    new_desc, decision = apply_visual_planning(desc, visual_planning, scene_index=0)
    assert decision.camera_changed is True
    assert decision.composition_changed is True
    # Camera applied a focus target (focus_on_character -> guide), so the
    # attention recommendation is honored via the camera focus constraint
    # rather than by overwriting it (attention defers to camera targets).
    assert decision.attention_changed is False
    assert any("camera focus already applied" in w for w in decision.warnings)
    assert new_desc["camera"]["pattern"] == "focus_on_character"
    assert new_desc["camera"]["focus_target"] == "guide"


# ---------------------------------------------------------------------------
# 22. V1.4-F integration
# ---------------------------------------------------------------------------


def test_v14_f_visual_planning_metadata_shape(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", True)
    # The exact dict shape "visual_planning" that V1.4-F's _merge_visual_planning
    # attaches to each scene semantic context, including the top-level
    # recommended_camera used for advisory display.
    vp = {
        "scene_index": 0,
        "treatment": "establish",
        "recommended_motions": ["emphasize"],
        "recommended_camera": "focus_on_character",
        "recommended_transition": "crossfade",
        "diversity": {"scene_index": 0, "flags": ()},
        "composition": _composition_decision(scene_index=0),
        "camera": _camera_decision("focus_on_character", "guide"),
        "attention": _attention_decision("guide"),
    }
    desc = _desc(characters=("guide",))
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert decision.changed is True
    assert new_desc["camera"]["pattern"] == "focus_on_character"
    assert new_desc["camera"]["focus_target"] == "guide"


# ---------------------------------------------------------------------------
# 23. V1.2/V1.3 compatibility
# ---------------------------------------------------------------------------
# The layer only ever touches the camera dict (+ additive composition
# metadata). Legacy visual_prompt/animation/camera_instructions and explicit
# positions/motions/transitions are never altered.


def test_v12_v13_compatibility_legacy_fields_untouched() -> None:
    desc = _desc(
        characters=("guide", "mentor"),
        camera={"pattern": "static", "focus_target": "guide"},
    )
    desc["visual_prompt"] = "legacy prompt"
    desc["animation_instructions"] = "legacy animation"
    desc["camera_instructions"] = "legacy camera"
    desc["motions"] = [{"type": "emphasize", "target": "character"}]
    vp = _visual_planning(
        0,
        camera=_camera_decision("pan_right", "mentor"),
        attention=_attention_decision("mentor"),
    )
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    # Legacy fields and explicit positions preserved byte-for-byte.
    assert new_desc["visual_prompt"] == "legacy prompt"
    assert new_desc["animation_instructions"] == "legacy animation"
    assert new_desc["camera_instructions"] == "legacy camera"
    assert new_desc["motions"] == desc["motions"]
    assert new_desc["characters"] == desc["characters"]
    # Explicit camera pattern preserved, focus preserved, no camera change.
    assert decision.camera_changed is False
    assert decision.attention_changed is False
    assert new_desc["camera"]["pattern"] == "static"
    assert new_desc["camera"]["focus_target"] == "guide"


# ---------------------------------------------------------------------------
# 24. Disabled-mode byte-equivalence where practical
# ---------------------------------------------------------------------------


def test_disabled_mode_byte_equivalence(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", False)
    desc = _desc(characters=("guide",), camera={"pattern": "static"})
    vp = _visual_planning(
        0,
        camera=_camera_decision("slow_zoom_in"),
        attention=_attention_decision("guide"),
    )
    # Flag OFF must leave the staging description 100% byte-identical.
    new_desc, decision = apply_visual_planning(desc, vp, scene_index=0)
    assert json.dumps(new_desc, sort_keys=True) == json.dumps(desc, sort_keys=True)
    assert decision.changed is False
    assert decision.camera_changed is False
