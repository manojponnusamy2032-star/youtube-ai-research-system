from __future__ import annotations

from src.models.content_package import Motion, SUPPORTED_MOTION_TYPES
import src.services.motion_variation as motion_module
from src.services.motion_variation import apply_motion_variation


def _characters():
    return [{"name": "student"}]


def test_flag_off_preserves_motion_list(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", False)
    existing = [Motion(type="scale", target="character", target_id="student", start_time=0, duration=1, parameters={"from": 1, "to": 1.1})]
    result = apply_motion_variation(_characters(), [], existing, scene_role="hook")
    assert result.motions == tuple(existing)
    assert result.decision.skipped is True


def test_hook_selection_is_deterministic_and_supported(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    first = apply_motion_variation(_characters(), [], scene_index=0, scene_role="hook", duration=3)
    second = apply_motion_variation(_characters(), [], scene_index=0, scene_role="hook", duration=3)
    assert first.to_dict() == second.to_dict()
    assert first.decision.intent in {"react", "emphasize"}
    assert first.motions[-1].type in SUPPORTED_MOTION_TYPES
    assert first.motions[-1].target_id == "student"


def test_scene_roles_can_select_different_intents(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    hook = apply_motion_variation(_characters(), [], scene_index=0, scene_role="hook")
    explanation = apply_motion_variation(_characters(), [{"name": "graph"}], scene_index=1, scene_role="explanation", primary_focus="object")
    assert hook.decision.intent != explanation.decision.intent


def test_adjacent_same_role_can_avoid_repeating_motion(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    first = apply_motion_variation(_characters(), [], scene_index=0, scene_role="hook")
    second = apply_motion_variation(_characters(), [], scene_index=1, scene_role="hook")
    assert first.decision.intent != second.decision.intent


def test_explicit_motion_is_preserved(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    existing = [Motion(type="scale", target="character", target_id="student", start_time=0, duration=1, parameters={"from": 1, "to": 1.4})]
    result = apply_motion_variation(_characters(), [], existing, scene_role="hook")
    assert result.motions == tuple(existing)
    assert result.decision.skipped is True


def test_explicit_character_action_is_preserved(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    result = apply_motion_variation(_characters(), [], scene_role="character_action", explicit_character_action="walk")
    assert not result.decision.changed
    assert result.decision.skipped


def test_object_interaction_targets_object(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    result = apply_motion_variation(
        [{"name": "student"}], [{"name": "notebook", "type": "notebook"}],
        scene_role="object_interaction", primary_focus="object",
    )
    assert result.decision.target == "object"
    assert result.decision.target_id == "notebook"
    assert result.motions[-1].type == "scale"


def test_empty_and_unknown_scenes_are_safe(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    assert apply_motion_variation([], [], scene_role="unknown").decision.skipped
    assert apply_motion_variation(None, None).motions == ()


def test_unsupported_primitive_falls_back_safely(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    monkeypatch.setitem(motion_module._INTENT_TYPES, "react", ("unsupported",))
    result = apply_motion_variation(_characters(), [], scene_role="hook")
    assert result.decision.skipped
    assert "unsupported_motion_fallback" in result.decision.warnings


def test_multi_character_scene_stays_valid(monkeypatch):
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    result = apply_motion_variation([{"name": "student"}, {"name": "coach"}], [], scene_role="comparison")
    assert len(result.motions) == 1
    assert result.motions[0].target == "character"
    result.motions[0].validate(scene_duration=1.0)


def test_flag_default_is_off():
    assert motion_module.VISUAL_MOTION_VARIATION_ENABLED is False
