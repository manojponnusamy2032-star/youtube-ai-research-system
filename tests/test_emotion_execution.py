"""Focused unit tests for the V1.6-F character emotion execution layer.

Verifies that ``src.services.emotion_execution`` deterministically stages a
single ``emotion`` key on the character the scene is emotionally about,
deriving it from planner-authoritative semantics (V1.4 treatment -> V1.3
beat -> scene role -> neutral), while preserving explicit authored emotion,
never mutating caller-owned inputs, and staying safe on malformed input.
"""

from __future__ import annotations

import copy

import pytest

import src.services.emotion_execution as emotion
from src.services.emotion_execution import (
    BEAT_EMOTIONS,
    NEUTRAL_EMOTION,
    ROLE_EMOTIONS,
    TREATMENT_EMOTIONS,
    apply_emotion_execution,
)
from src.services.scene_composition import SUPPORTED_EMOTIONS, CharacterSpec


def make_characters():
    """Two characters: hero (attention target) and side (non-target)."""
    return [
        {"name": "hero", "x": 0.3, "y": 0.75},
        {"name": "side", "x": 0.7, "y": 0.75},
    ]


def _planning(treatment: str, target: str = "hero", kind: str = "character"):
    return {
        "story": {"treatment": treatment},
        "attention": {"primary_target": target, "target_kind": kind},
    }


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(emotion, "VISUAL_EMOTION_EXECUTION_ENABLED", True)


# ---------------------------------------------------------------------------
# 1. Feature flag OFF preserves existing behavior
# ---------------------------------------------------------------------------


def test_flag_defaults_off():
    import importlib

    module = importlib.import_module("src.services.emotion_execution")
    importlib.reload(module)
    assert module.VISUAL_EMOTION_EXECUTION_ENABLED is False


def test_off_returns_original_members_unchanged():
    characters = make_characters()
    result = apply_emotion_execution(characters)
    assert result.characters[0] is characters[0]
    assert result.characters[1] is characters[1]
    assert result.decision.skipped is True
    assert result.decision.changed is False
    assert "disabled" in result.decision.reason
    assert all("emotion" not in member for member in result.characters)


def test_off_skips_even_with_rich_planning():
    characters = make_characters()
    result = apply_emotion_execution(
        characters, planning_metadata=_planning("problem_focus")
    )
    assert result.decision.changed is False
    assert all("emotion" not in member for member in result.characters)


# ---------------------------------------------------------------------------
# 2. Determinism and no-mutation
# ---------------------------------------------------------------------------


def test_deterministic_repeat(enabled):
    kwargs = dict(
        scene_role="hook",
        planning_metadata=_planning("problem_focus"),
        beat={"type": "problem"},
    )
    first = apply_emotion_execution(make_characters(), **kwargs)
    second = apply_emotion_execution(make_characters(), **kwargs)
    assert first.decision.to_dict() == second.decision.to_dict()
    assert first.characters == second.characters


def test_no_mutation_of_caller_inputs(enabled):
    characters = make_characters()
    snapshot = copy.deepcopy(characters)
    planning = _planning("compare")
    planning_snapshot = copy.deepcopy(planning)
    beat = {"type": "contrast"}
    beat_snapshot = copy.deepcopy(beat)
    apply_emotion_execution(
        characters, planning_metadata=planning, beat=beat
    )
    assert characters == snapshot
    assert planning == planning_snapshot
    assert beat == beat_snapshot
    # The bearer replacement is a copy: the original dict object is intact.
    assert "emotion" not in characters[0]


def test_explicit_emotion_preserved_untouched(enabled):
    characters = [{"name": "hero", "x": 0.3, "emotion": "sad"}]
    result = apply_emotion_execution(
        characters, planning_metadata=_planning("problem_focus")
    )
    assert result.decision.source == "explicit"
    assert result.decision.changed is False
    assert result.decision.skipped is True
    assert result.characters[0] is characters[0]
    assert result.characters[0]["emotion"] == "sad"


# ---------------------------------------------------------------------------
# 3. Bearer selection (V1.4-E attention primary target)
# ---------------------------------------------------------------------------


def test_attention_character_target_selected_as_bearer(enabled):
    characters = make_characters()
    result = apply_emotion_execution(
        characters, planning_metadata=_planning("explain")
    )
    assert result.decision.bearer == "hero"
    assert result.characters[1] is characters[1]  # non-target untouched
    assert "emotion" not in characters[1]


def test_missing_attention_target_falls_back_to_first_character(enabled):
    result = apply_emotion_execution(make_characters(), planning_metadata={})
    assert result.decision.bearer == "hero"


def test_object_attention_target_safely_skips(enabled):
    planning = _planning("explain", target="ball", kind="object")
    characters = make_characters()
    result = apply_emotion_execution(characters, planning_metadata=planning)
    assert result.decision.changed is False
    assert result.decision.skipped is True
    assert "attention_target_is_object:ball" in result.decision.warnings
    assert all("emotion" not in member for member in result.characters)


def test_absent_attention_character_safely_skips(enabled):
    planning = _planning("explain", target="ghost", kind="character")
    result = apply_emotion_execution(
        make_characters(), planning_metadata=planning
    )
    assert result.decision.changed is False
    assert "attention_target_absent:ghost" in result.decision.warnings
    assert all("emotion" not in member for member in result.characters)


# ---------------------------------------------------------------------------
# 4. Semantic mapping tables (treatment -> beat -> role -> neutral)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "treatment,expected", sorted(TREATMENT_EMOTIONS.items())
)
def test_all_treatment_mappings(enabled, treatment, expected):
    result = apply_emotion_execution(
        make_characters(), planning_metadata=_planning(treatment)
    )
    assert result.decision.emotion == expected
    assert result.decision.source == "treatment"
    assert result.decision.changed is True
    assert result.characters[0]["emotion"] == expected


@pytest.mark.parametrize("expected", sorted(set(BEAT_EMOTIONS.values())))
def test_beat_fallback_without_treatment(enabled, expected):
    beat = {
        beat_type
        for beat_type, emotion_value in BEAT_EMOTIONS.items()
        if emotion_value == expected
    }
    for beat_type in beat:
        result = apply_emotion_execution(
            make_characters(), planning_metadata={}, beat={"type": beat_type}
        )
        assert result.decision.emotion == expected
        assert result.decision.source == "beat"


@pytest.mark.parametrize(
    "role,expected", sorted(ROLE_EMOTIONS.items())
)
def test_role_fallback_without_planning(enabled, role, expected):
    result = apply_emotion_execution(make_characters(), scene_role=role)
    assert result.decision.emotion == expected
    assert result.decision.source == "role"


def test_neutral_fallback_for_unknown_role(enabled):
    result = apply_emotion_execution(
        make_characters(), scene_role="totally_unknown_role"
    )
    assert result.decision.emotion == NEUTRAL_EMOTION
    assert result.decision.source == "neutral"


def test_no_forced_alternation_consecutive_same_treatment(enabled):
    """Semantic correctness over variety: same treatment -> same emotion."""
    first = apply_emotion_execution(
        make_characters(), planning_metadata=_planning("problem_focus")
    )
    second = apply_emotion_execution(
        make_characters(), planning_metadata=_planning("problem_focus")
    )
    assert first.decision.emotion == second.decision.emotion == "frustrated"


def test_unknown_treatment_warns_and_falls_through_to_beat(enabled):
    result = apply_emotion_execution(
        make_characters(),
        planning_metadata=_planning("mystery_treatment"),
        beat={"type": "solution"},
    )
    assert "unknown_treatment:mystery_treatment" in result.decision.warnings
    assert result.decision.emotion == "happy"
    assert result.decision.source == "beat"


# ---------------------------------------------------------------------------
# 5. Malformed input and scene-shape safety
# ---------------------------------------------------------------------------


def test_empty_character_list_skips(enabled):
    result = apply_emotion_execution([])
    assert result.decision.skipped is True
    assert result.decision.changed is False
    assert result.characters == ()


def test_none_characters_skips(enabled):
    result = apply_emotion_execution(None)
    assert result.decision.skipped is True


def test_malformed_planning_metadata_is_safe(enabled):
    result = apply_emotion_execution(
        make_characters(),
        planning_metadata={"story": "not-a-dict", "attention": 42},
        scene_role="hook",
    )
    assert result.decision.emotion == "excited"
    assert result.decision.source == "role"


def test_non_dict_members_warn_and_skip(enabled):
    result = apply_emotion_execution(["not-a-dict", None])
    assert result.decision.skipped is True
    assert "non_dict_members" in result.decision.warnings


def test_single_character_scene(enabled):
    result = apply_emotion_execution(
        [{"name": "solo", "x": 0.5}], scene_role="hook"
    )
    assert result.decision.bearer == "solo"
    assert result.decision.changed is True
    assert result.characters[0]["emotion"] == "excited"


def test_single_emotion_bearer_invariant(enabled):
    characters = [
        {"name": "a", "x": 0.2},
        {"name": "b", "x": 0.5},
        {"name": "c", "x": 0.8},
    ]
    planning = _planning("explain", target="b")
    result = apply_emotion_execution(characters, planning_metadata=planning)
    with_emotion = [m for m in result.characters if "emotion" in m]
    assert len(with_emotion) == 1
    assert with_emotion[0]["name"] == "b"
    # Non-target members pass through by reference (untouched).
    assert result.characters[0] is characters[0]
    assert result.characters[2] is characters[2]


# ---------------------------------------------------------------------------
# 6. Contracts: validation, CharacterSpec compatibility, serialization
# ---------------------------------------------------------------------------


def test_every_mapped_emotion_is_supported():
    for emotion_value in list(TREATMENT_EMOTIONS.values()) + list(
        BEAT_EMOTIONS.values()
    ) + list(ROLE_EMOTIONS.values()):
        assert emotion_value in SUPPORTED_EMOTIONS


def test_staged_dict_is_characterspec_compatible(enabled):
    result = apply_emotion_execution(
        make_characters(), planning_metadata=_planning("proof")
    )
    spec = CharacterSpec(**result.characters[0])
    assert spec.emotion == "focused"


def test_decision_serialization_stable(enabled):
    result = apply_emotion_execution(
        make_characters(), planning_metadata=_planning("cta")
    )
    payload = result.decision.to_dict()
    assert payload == {
        "scene_index": 0,
        "bearer": "hero",
        "emotion": "excited",
        "source": "treatment",
        "changed": True,
        "skipped": False,
        "reason": "emotion staged from treatment",
        "warnings": [],
    }
    again = apply_emotion_execution(
        make_characters(), planning_metadata=_planning("cta")
    )
    assert again.decision.to_dict() == payload

