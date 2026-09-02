"""V1.6-A background variation service unit tests.

Proves that the layer is:
- deterministic (identical inputs -> identical outputs);
- flag-gated (OFF by default, no-op when OFF);
- explicit-intent preserving (non-empty environment never overwritten);
- vocabulary-safe (only SUPPORTED_ENVIRONMENTS values, renderer-safe keys);
- adjacency-guaranteed (no two consecutive scenes share a backdrop).
"""
from __future__ import annotations

import copy
import json

import src.services.background_variation as bgv_module
from src.services.background_variation import (
    BackgroundVariationDecision,
    BackgroundVariationReport,
    apply_background_variation,
    apply_background_variation_sequence,
    build_environment,
    resolve_environment_type,
)
from src.services.scene_composition import SUPPORTED_ENVIRONMENTS


def _base_description(environment=None):
    desc = {
        "characters": [{"name": "student", "pose": "talk", "x": 0.3, "y": 0.7}],
        "objects": [{"name": "brain", "type": "brain", "x": 0.7, "y": 0.5}],
        "environment": dict(environment if environment is not None else {}),
        "text_elements": [{"text": "Hook", "size": "headline", "x": 0.5, "y": 0.12}],
        "camera": {},
    }
    return desc


# ---------------------------------------------------------------------------
# 1. Flag defaults and OFF behavior
# ---------------------------------------------------------------------------


def test_feature_flag_defaults_off() -> None:
    assert bgv_module.VISUAL_BACKGROUND_VARIATION_ENABLED is False


def test_apply_flag_off_returns_description_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", False)
    desc = _base_description()
    before = copy.deepcopy(desc)
    new_desc, decision = apply_background_variation(desc, scene_index=2, total_scenes=5)
    assert new_desc == before
    assert new_desc["environment"] == {}
    assert decision.skipped is True
    assert decision.changed is False
    assert decision.assigned_type is None
    assert "flag OFF" in decision.reason


# ---------------------------------------------------------------------------
# 2. Filling empty environments
# ---------------------------------------------------------------------------


def test_apply_flag_on_fills_empty_environment(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    new_desc, decision = apply_background_variation(
        _base_description(), scene_index=0, total_scenes=3
    )
    environment = new_desc["environment"]
    assert set(environment) == {
        "type", "background_color", "ground_color", "ground_y", "accent_color",
    }
    assert environment["type"] in SUPPORTED_ENVIRONMENTS
    assert decision.filled is True
    assert decision.changed is True
    assert decision.assigned_type == environment["type"]


def test_missing_environment_key_treated_as_empty(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    desc = _base_description()
    desc.pop("environment")
    new_desc, decision = apply_background_variation(desc, scene_index=1, total_scenes=3)
    assert "type" in new_desc["environment"]
    assert decision.filled is True


# ---------------------------------------------------------------------------
# 3. Explicit intent preservation
# ---------------------------------------------------------------------------


def test_explicit_environment_preserved(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    explicit = {"type": "study_desk", "ground_y": 0.78}
    desc = _base_description(environment=explicit)
    before = copy.deepcopy(desc)
    new_desc, decision = apply_background_variation(desc, scene_index=1, total_scenes=3)
    assert new_desc == before
    assert decision.skipped is True
    assert decision.changed is False
    assert "explicit_environment_preserved" in decision.warnings
    assert decision.original_environment == explicit


# ---------------------------------------------------------------------------
# 4. Vocabulary safety
# ---------------------------------------------------------------------------


def test_candidates_are_supported_and_exclude_default() -> None:
    assert set(bgv_module.VARIATION_CANDIDATES) <= SUPPORTED_ENVIRONMENTS
    assert "default" not in bgv_module.VARIATION_CANDIDATES


def test_assigned_types_always_supported(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    for index in range(24):
        new_desc, _ = apply_background_variation(
            _base_description(), scene_index=index, total_scenes=24
        )
        assert new_desc["environment"]["type"] in SUPPORTED_ENVIRONMENTS


# ---------------------------------------------------------------------------
# 5. Adjacency guarantee
# ---------------------------------------------------------------------------


def test_adjacent_scenes_never_share_backdrop() -> None:
    for total in (2, 3, 5, 7, 12, 31):
        types = [resolve_environment_type(index, total) for index in range(total)]
        for previous, current in zip(types, types[1:]):
            assert previous != current, (total, types)


# ---------------------------------------------------------------------------
# 6. Determinism
# ---------------------------------------------------------------------------


def test_determinism_identical_inputs(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    desc = _base_description()
    first_desc, first_decision = apply_background_variation(desc, scene_index=4, total_scenes=9)
    second_desc, second_decision = apply_background_variation(
        copy.deepcopy(desc), scene_index=4, total_scenes=9
    )
    assert first_desc == second_desc
    assert first_decision == second_decision
    assert build_environment(4, 9) == build_environment(4, 9)


def test_adjacent_applied_scenes_differ(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    types = []
    for index in range(8):
        new_desc, decision = apply_background_variation(
            _base_description(), scene_index=index, total_scenes=8
        )
        types.append(new_desc["environment"]["type"])
        if index > 0:
            assert decision.previous_type is not None
    for previous, current in zip(types, types[1:]):
        assert previous != current


# ---------------------------------------------------------------------------
# 7. Renderer-safe values
# ---------------------------------------------------------------------------


def test_environment_values_are_renderer_safe(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    for index in range(12):
        environment = build_environment(index, 12)
        for key in ("background_color", "ground_color", "accent_color"):
            value = environment[key]
            assert isinstance(value, list) and len(value) == 3
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in value)
        assert 0.5 <= float(environment["ground_y"]) <= 0.95


# ---------------------------------------------------------------------------
# 8. Sequence-level entry point
# ---------------------------------------------------------------------------


def test_sequence_applies_and_counts(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    descriptions = [
        _base_description(),
        _base_description(environment={"type": "classroom"}),
        _base_description(),
        _base_description(),
    ]
    new_descs, report = apply_background_variation_sequence(descriptions)
    assert report.enabled is True
    assert report.applied_count == 3
    assert report.skipped_count == 1
    assert len(report.decisions) == 4
    # The explicit classroom scene is untouched; the others are assigned.
    assert new_descs[1]["environment"] == {"type": "classroom"}
    filled_types = [d.assigned_type for d in report.decisions if d.filled]
    assert len(filled_types) == 3


def test_sequence_flag_off_noop(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", False)
    descriptions = [_base_description(), _base_description()]
    new_descs, report = apply_background_variation_sequence(descriptions)
    assert new_descs == descriptions
    assert report.enabled is False
    assert report.applied_count == 0
    assert report.skipped_count == 2


# ---------------------------------------------------------------------------
# 9. Inputs never mutated; observability serializable
# ---------------------------------------------------------------------------


def test_input_description_never_mutated(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    desc = _base_description()
    before = copy.deepcopy(desc)
    apply_background_variation(desc, scene_index=3, total_scenes=6)
    assert desc == before


def test_decision_and_report_are_json_serializable(monkeypatch) -> None:
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", True)
    _, decision = apply_background_variation(_base_description(), scene_index=0, total_scenes=2)
    json.dumps(decision.to_dict(), sort_keys=True)
    _descs, report = apply_background_variation_sequence(
        [_base_description(), _base_description()]
    )
    json.dumps(report.to_dict(), sort_keys=True)
    assert isinstance(decision, BackgroundVariationDecision)
    assert isinstance(report, BackgroundVariationReport)