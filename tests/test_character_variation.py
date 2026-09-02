"""V1.6-B character staging & pose variation service unit tests.

Proves that the layer is:
- deterministic (identical inputs -> identical outputs);
- flag-gated (OFF by default, no-op when OFF);
- explicit-intent preserving (present pose/scale/x keys never overwritten);
- vocabulary-safe (only SUPPORTED_POSES values are assigned);
- collision-aware (anchors avoid staged characters and objects);
- continuity-preserving (identity+role hashing keeps staging stable);
- non-mutating (inputs are copied, never modified).
"""
from __future__ import annotations

import copy
import json

import src.services.character_variation as char_var_module
from src.services.character_variation import (
    PRIMARY_SCALE,
    SUPPORTING_SCALE,
    CharacterVariationDecision,
    apply_character_variation,
)
from src.services.scene_composition import SUPPORTED_POSES


def _char(name, **extra):
    d = {"name": name}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# 1. Flag defaults and OFF behavior
# ---------------------------------------------------------------------------


def test_feature_flag_defaults_off() -> None:
    assert char_var_module.VISUAL_CHARACTER_VARIATION_ENABLED is False


def test_apply_flag_off_returns_characters_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", False)
    characters = [_char("student", x=0.35, y=0.75)]
    new_characters, decision = apply_character_variation(
        characters,
        [],
        scene_index=2,
        scene_role="hook",
    )
    assert new_characters == characters
    assert decision.skipped is True
    assert decision.changed is False
    assert "flag OFF" in decision.reason


# ---------------------------------------------------------------------------
# 2. Pose variation (role-driven, only when absent)
# ---------------------------------------------------------------------------


def test_flag_on_applies_role_pose_when_absent(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("student", x=0.35, y=0.75)],
        [],
        scene_index=0,
        scene_role="hook",
    )
    assert new_characters[0]["pose"] == "surprised"
    assert decision.pose_changed is True
    assert decision.pose_variations == ("student",)


def test_explicit_pose_preserved(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    for explicit in ("idle", "walk", "point"):
        new_characters, decision = apply_character_variation(
            [_char("student", pose=explicit)],
            [],
            scene_index=0,
            scene_role="hook",
        )
        assert new_characters[0]["pose"] == explicit
        assert decision.pose_changed is False


def test_unknown_role_keeps_default_pose(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("student")],
        [],
        scene_index=0,
        scene_role="nonexistent_role",
    )
    assert "pose" not in new_characters[0]
    assert decision.pose_changed is False


def test_variation_poses_subset_of_supported() -> None:
    assert char_var_module.supported_variation_poses() <= SUPPORTED_POSES


# ---------------------------------------------------------------------------
# 3. Scale variation (structural, multi-character only)
# ---------------------------------------------------------------------------


def test_multi_character_scale_primary_supporting(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("guide"), _char("friend")],
        [],
        scene_index=0,
        scene_role="solution",
    )
    scales = {c["name"]: c["scale"] for c in new_characters}
    assert set(scales.values()) == {PRIMARY_SCALE, SUPPORTING_SCALE}
    assert decision.scale_changed is True


def test_explicit_scale_preserved(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("guide", scale=1.3), _char("friend", scale=0.7)],
        [],
        scene_index=0,
        scene_role="solution",
    )
    assert new_characters[0]["scale"] == 1.3
    assert new_characters[1]["scale"] == 0.7
    assert decision.scale_changed is False


def test_single_character_scale_untouched(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("student")],
        [],
        scene_index=0,
        scene_role="explanation",
    )
    assert "scale" not in new_characters[0]
    assert decision.scale_changed is False


def test_focus_character_gets_primary_scale(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("guide"), _char("friend")],
        [],
        scene_index=0,
        scene_role="solution",
        focus_target="friend",
    )
    scales = {c["name"]: c["scale"] for c in new_characters}
    assert scales["friend"] == PRIMARY_SCALE
    assert scales["guide"] == SUPPORTING_SCALE
    assert decision.focus_character == "friend"


# ---------------------------------------------------------------------------
# 4. Position variation (anchors, only when absent)
# ---------------------------------------------------------------------------


def test_explicit_position_preserved(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("student", x=0.42, y=0.76)],
        [],
        scene_index=0,
        scene_role="hook",
    )
    assert new_characters[0]["x"] == 0.42
    assert decision.position_changed is False


def test_position_anchor_applied_when_absent(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("student")],
        [],
        scene_index=0,
        scene_role="hook",
    )
    assert new_characters[0]["x"] in char_var_module.POSITION_ANCHORS
    assert decision.position_changed is True


# ---------------------------------------------------------------------------
# 5. Collision avoidance
# ---------------------------------------------------------------------------


def test_multi_character_distinct_anchors(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    new_characters, decision = apply_character_variation(
        [_char("guide"), _char("friend")],
        [],
        scene_index=0,
        scene_role="solution",
    )
    xs = [c["x"] for c in new_characters]
    assert xs[0] in char_var_module.POSITION_ANCHORS
    assert xs[1] in char_var_module.POSITION_ANCHORS
    assert abs(xs[0] - xs[1]) >= 0.12
    assert decision.position_changed is True


def test_anchor_avoids_nearby_object(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    # An object sitting exactly on one anchor forces the other anchor.
    new_characters, _ = apply_character_variation(
        [_char("student")],
        [{"name": "board", "type": "screen", "x": char_var_module.POSITION_ANCHORS[0], "y": 0.4}],
        scene_index=0,
        scene_role="hook",
    )
    assert new_characters[0]["x"] == char_var_module.POSITION_ANCHORS[1]


def test_no_free_anchor_keeps_default(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    objects = [
        {"name": "left", "type": "desk", "x": char_var_module.POSITION_ANCHORS[0], "y": 0.5},
        {"name": "right", "type": "desk", "x": char_var_module.POSITION_ANCHORS[1], "y": 0.5},
    ]
    new_characters, decision = apply_character_variation(
        [_char("student")],
        objects,
        scene_index=0,
        scene_role="hook",
    )
    assert "x" not in new_characters[0]
    assert decision.position_changed is False
    assert any("no free anchor" in w for w in decision.warnings)


# ---------------------------------------------------------------------------
# 6. Continuity (identity + role hashing)
# ---------------------------------------------------------------------------


def test_continuity_same_identity_and_role(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    first, _ = apply_character_variation(
        [_char("student")], [], scene_index=0, scene_role="explanation"
    )
    second, _ = apply_character_variation(
        [_char("student")], [], scene_index=1, scene_role="explanation"
    )
    assert first[0]["x"] == second[0]["x"]
    assert first[0]["pose"] == second[0]["pose"]


def test_role_change_produces_valid_staging(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    hook, _ = apply_character_variation([_char("student")], [], scene_index=0, scene_role="hook")
    solution, _ = apply_character_variation([_char("student")], [], scene_index=1, scene_role="solution")
    assert hook[0]["x"] in char_var_module.POSITION_ANCHORS
    assert solution[0]["x"] in char_var_module.POSITION_ANCHORS
    assert hook[0]["pose"] != solution[0]["pose"]


# ---------------------------------------------------------------------------
# 7. Determinism / immutability / serializability
# ---------------------------------------------------------------------------


def test_determinism_identical_inputs(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    characters = [_char("guide"), _char("friend")]
    objects = [{"name": "board", "type": "screen", "x": 0.7, "y": 0.4}]
    first_desc, first_decision = apply_character_variation(
        copy.deepcopy(characters), copy.deepcopy(objects),
        scene_index=3, scene_role="solution", focus_target="guide",
    )
    second_desc, second_decision = apply_character_variation(
        copy.deepcopy(characters), copy.deepcopy(objects),
        scene_index=3, scene_role="solution", focus_target="guide",
    )
    assert first_desc == second_desc
    assert first_decision == second_decision


def test_inputs_never_mutated(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    characters = [_char("guide"), _char("friend", scale=1.2)]
    objects = [{"name": "board", "type": "screen", "x": 0.7, "y": 0.4}]
    characters_before = copy.deepcopy(characters)
    objects_before = copy.deepcopy(objects)
    apply_character_variation(characters, objects, scene_index=0, scene_role="hook")
    assert characters == characters_before
    assert objects == objects_before


def test_decision_json_serializable(monkeypatch) -> None:
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", True)
    _, decision = apply_character_variation(
        [_char("student")], [], scene_index=0, scene_role="hook"
    )
    json.dumps(decision.to_dict(), sort_keys=True)
    assert isinstance(decision, CharacterVariationDecision)