"""Focused unit tests for the V1.6-E scene choreography layer.

Verifies that ``src.services.scene_choreography`` deterministically
coordinates cast-delta entrances, non-cut exits, attention-aware emphasis,
and transition-aware settling onto the existing motion list, while staying
strictly append-only (existing motions are never mutated, retimed, or
reordered) and safe on invalid input.
"""

from __future__ import annotations

import copy
import json

import pytest

import src.services.scene_choreography as choreo
from src.models.content_package import Motion


def make_desc():
    """A small structured scene: one character left-of-center, one object right."""
    return {
        "characters": [{"name": "Hero", "x": 0.3, "y": 0.75}],
        "objects": [{"name": "Ball", "x": 0.7, "y": 0.8}],
    }


def hero_only_desc():
    """A single-character scene for exact-single-enter assertions."""
    return {"characters": [{"name": "Hero", "x": 0.3, "y": 0.75}], "objects": []}


def ball_only_desc():
    """A single-object scene for exact-single-enter assertions."""
    return {"characters": [], "objects": [{"name": "Ball", "x": 0.7, "y": 0.8}]}


def _motion(mtype="move", target="character", target_id="hero", start=0.0,
            duration=1.0, label="explicit", **params):
    return Motion(
        type=mtype,
        target=target,
        target_id=target_id,
        start_time=start,
        duration=duration,
        easing="ease_in_out",
        parameters=params or {"from": {"x": 0.2, "y": 0.75}, "to": {"x": 0.4, "y": 0.75}},
        label=label,
    )


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(choreo, "VISUAL_CHOREOGRAPHY_ENABLED", True)


# ---------------------------------------------------------------------------
# 1. Feature flag OFF preserves existing behavior
# ---------------------------------------------------------------------------


def test_flag_defaults_off():
    import importlib

    module = importlib.import_module("src.services.scene_choreography")
    importlib.reload(module)
    assert module.VISUAL_CHOREOGRAPHY_ENABLED is False


def test_off_returns_original_motions_unchanged():
    desc = make_desc()
    motions = [_motion()]
    result = choreo.apply_scene_choreography(
        motions, visual_description=desc, duration=4.0
    )
    assert result.motions == tuple(motions)
    assert result.motions[0] is motions[0]
    assert result.decision.skipped is True
    assert result.decision.changed is False
    assert "disabled" in result.decision.reason


def test_off_and_on_never_mutate_visual_description(enabled):
    desc = make_desc()
    snapshot = copy.deepcopy(desc)
    choreo.apply_scene_choreography(
        [_motion()], visual_description=desc, previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), duration=4.0,
    )
    assert desc == snapshot


def test_off_sequence_returns_same_list_objects():
    lists = [[_motion()], []]
    descs = [make_desc(), make_desc()]
    out, report = choreo.apply_scene_choreography_sequence(lists, descs)
    assert out[0] is lists[0]
    assert out[1] is lists[1]
    assert report.enabled is False
    assert report.applied_count == 0


# ---------------------------------------------------------------------------
# 2. Determinism
# ---------------------------------------------------------------------------


def test_deterministic_per_scene_repeat(enabled):
    desc = make_desc()
    kwargs = dict(
        visual_description=desc,
        previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}),
        scene_index=0,
        duration=4.0,
        planning_metadata={"attention": {"primary_target": "Hero",
                                         "target_kind": "character"}},
        camera={"pattern": "focus_on_character", "focus_target": "Hero"},
        transition_to_next={"type": "crossfade", "duration": 0.5},
    )
    first = choreo.apply_scene_choreography([_motion()], **kwargs)
    second = choreo.apply_scene_choreography([_motion()], **kwargs)
    assert first.decision.to_dict() == second.decision.to_dict()
    assert [m.to_dict() for m in first.motions] == [m.to_dict() for m in second.motions]


def test_deterministic_sequence_repeat(enabled):
    descs = [make_desc(), make_desc()]
    kwargs = dict(
        visual_descriptions=descs,
        durations=[4.0, 4.0],
        transitions_to_next=[{"type": "crossfade"}, None],
    )
    out1, report1 = choreo.apply_scene_choreography_sequence([[], []], **kwargs)
    out2, report2 = choreo.apply_scene_choreography_sequence([[], []], **kwargs)
    assert [[m.to_dict() for m in lst] for lst in out1] == [
        [m.to_dict() for m in lst] for lst in out2
    ]
    assert report1.to_dict() == report2.to_dict()


# --- marker: entrances ---

# ---------------------------------------------------------------------------
# 3. Cast-delta entrances
# ---------------------------------------------------------------------------


def test_enter_appended_for_introduced_character(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=hero_only_desc(), previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
    )
    enters = [m for m in result.motions if m.label == "v1.6-e:enter"]
    assert len(enters) == 1
    assert enters[0].type == "enter"
    assert enters[0].target == "character"
    assert enters[0].target_id == "hero"
    assert enters[0].parameters["direction"] == "left"


def test_enter_direction_follows_authored_x(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=ball_only_desc(), previous_cast=frozenset(),
        next_cast=frozenset({("object", "ball")}), scene_index=0, duration=4.0,
    )
    enters = [m for m in result.motions if m.label == "v1.6-e:enter"]
    assert enters and enters[0].parameters["direction"] == "right"


def test_enter_direction_falls_back_to_camera_focus_side(enabled):
    desc = {
        "characters": [{"name": "Hero", "x": 0.35, "y": 0.75}],
        "objects": [{"name": "Ball", "x": 0.75, "y": 0.8}],
    }
    result = choreo.apply_scene_choreography(
        [], visual_description=desc, previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
        camera={"pattern": "focus_on_object", "focus_target": "Ball"},
    )
    enters = [m for m in result.motions if m.label == "v1.6-e:enter"]
    # focus is on the right-side object -> enter from the left default side
    assert enters and enters[0].parameters["direction"] == "left"


def test_no_enter_when_element_already_in_previous_cast(enabled):
    full_cast = frozenset({("character", "hero"), ("object", "ball")})
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(),
        previous_cast=full_cast,
        next_cast=full_cast, scene_index=1, duration=4.0,
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:enter"]


def test_enter_skipped_when_lead_in_window_conflicts(enabled):
    existing = [_motion(mtype="move", start=0.0, duration=1.0)]
    result = choreo.apply_scene_choreography(
        existing, visual_description=hero_only_desc(), previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:enter"]
    assert any("enter_conflict" in w for w in result.decision.warnings)


def test_no_enter_scheduled_for_first_scene_without_context(enabled):
    # previous_cast=None means no reliable continuity info: stay conservative.
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), previous_cast=None,
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:enter"]
    assert result.decision.skipped is True


# ---------------------------------------------------------------------------
# 4. Cast-delta exits (non-cut transitions only)
# ---------------------------------------------------------------------------


def test_exit_appended_for_departing_element_on_non_cut(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(),
        previous_cast=frozenset({("character", "hero"), ("object", "ball")}),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
        transition_to_next={"type": "crossfade", "duration": 0.5},
    )
    exits = [m for m in result.motions if m.label == "v1.6-e:exit"]
    assert len(exits) == 1
    assert exits[0].type == "exit"
    assert exits[0].target_id == "ball"
    assert exits[0].start_time + exits[0].duration <= 4.0 + 1e-6


def test_no_exit_for_departing_element_on_cut(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(),
        previous_cast=frozenset({("character", "hero"), ("object", "ball")}),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
        transition_to_next={"type": "cut"},
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:exit"]


def test_no_exit_when_no_transition_to_next(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(),
        previous_cast=frozenset({("object", "ball")}),
        next_cast=frozenset(), scene_index=0, duration=4.0,
        transition_to_next=None,
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:exit"]


def test_exit_skipped_when_tail_window_conflicts(enabled):
    existing = [_motion(mtype="move", target="object", target_id="ball",
                        start=3.3, duration=0.7)]
    result = choreo.apply_scene_choreography(
        existing, visual_description=make_desc(),
        previous_cast=frozenset({("character", "hero"), ("object", "ball")}),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
        transition_to_next={"type": "crossfade"},
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:exit"]
    assert any("exit_conflict" in w for w in result.decision.warnings)


# ---------------------------------------------------------------------------
# 5. Attention-aware emphasis
# ---------------------------------------------------------------------------


def test_emphasis_appended_for_free_attention_target(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), scene_index=0, duration=4.0,
        planning_metadata={"attention": {"primary_target": "Hero",
                                         "target_kind": "character"}},
    )
    emph = [m for m in result.motions if m.label == "v1.6-e:emphasis"]
    assert len(emph) == 1
    assert emph[0].type == "scale"
    assert emph[0].target_id == "hero"
    assert emph[0].duration <= 1.0
    assert result.decision.emphasis_target == "character:hero"


def test_emphasis_skipped_when_target_has_motion_in_window(enabled):
    existing = [_motion(mtype="scale", start=2.0, duration=1.0)]
    result = choreo.apply_scene_choreography(
        existing, visual_description=make_desc(), scene_index=0, duration=4.0,
        planning_metadata={"attention": {"primary_target": "Hero",
                                         "target_kind": "character"}},
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:emphasis"]
    assert any("emphasis_conflict" in w for w in result.decision.warnings)


def test_emphasis_uses_camera_focus_when_no_attention_metadata(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), scene_index=0, duration=4.0,
        camera={"pattern": "focus_on_object", "focus_target": "Ball"},
    )
    emph = [m for m in result.motions if m.label == "v1.6-e:emphasis"]
    assert emph and emph[0].target_id == "ball"


def test_no_emphasis_without_any_target_metadata(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), scene_index=0, duration=4.0,
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:emphasis"]
    assert result.decision.emphasis_target is None


def test_emphasis_skipped_for_target_outside_cast(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), scene_index=0, duration=4.0,
        planning_metadata={"attention": {"primary_target": "Ghost",
                                         "target_kind": "character"}},
    )
    assert not [m for m in result.motions if m.label == "v1.6-e:emphasis"]
    assert any("emphasis_target_not_in_cast" in w for w in result.decision.warnings)


def test_explicit_motions_are_never_retimed_or_reordered(enabled):
    existing = [
        _motion(mtype="move", start=1.0, duration=1.0, label="explicit-a"),
        _motion(mtype="fade", target="object", target_id="ball",
                start=2.0, duration=0.5, label="explicit-b"),
    ]
    snapshot = copy.deepcopy([m.to_dict() for m in existing])
    result = choreo.apply_scene_choreography(
        existing, visual_description=make_desc(), scene_index=0, duration=4.0,
        planning_metadata={"attention": {"primary_target": "Hero",
                                         "target_kind": "character"}},
    )
    kept = [m for m in result.motions if not m.label.startswith("v1.6-e:")]
    assert [m.to_dict() for m in kept] == snapshot
    assert kept[0] is existing[0] and kept[1] is existing[1]
    for m in result.motions:
        if m.label.startswith("v1.6-e:"):
            assert m not in existing


# ---------------------------------------------------------------------------
# 6. Timeline bounds, validation, and safety
# ---------------------------------------------------------------------------


def test_all_generated_motions_validate_against_scene_duration(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=3.0,
        planning_metadata={"attention": {"primary_target": "Hero",
                                         "target_kind": "character"}},
        transition_to_next={"type": "crossfade"},
    )
    for motion in result.motions:
        motion.validate(3.0)  # raises ValueError on violation
        assert 0.0 <= motion.start_time
        assert motion.start_time + motion.duration <= 3.0 + 1e-6
        assert motion.duration > 0.0


def test_generated_motions_carry_v16e_label_prefix(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
    )
    fresh = [m for m in result.motions if m.label not in ("",)]
    assert fresh and all(m.label.startswith("v1.6-e:") for m in fresh)


def test_short_scene_does_not_schedule_choreography(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=make_desc(), previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=0.5,
        transition_to_next={"type": "crossfade"},
    )
    assert result.decision.skipped is True
    assert not [m for m in result.motions if m.label.startswith("v1.6-e:")]


def test_invalid_duration_safely_skips(enabled):
    for bad in (0.0, -2.0, float("nan"), float("inf"), "abc", None):
        result = choreo.apply_scene_choreography(
            [], visual_description=make_desc(), scene_index=0, duration=bad,
        )
        assert result.decision.skipped is True
        assert result.motions == ()


def test_malformed_visual_description_safely_skips(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description={"characters": "not-a-list"},
        scene_index=0, duration=4.0,
    )
    assert isinstance(result.motions, tuple)
    assert result.decision.skipped is True


def test_motion_list_with_non_motion_entries_is_tolerated(enabled):
    result = choreo.apply_scene_choreography(
        ["garbage", None], visual_description=make_desc(), scene_index=0,
        duration=4.0,
    )
    assert not any(isinstance(m, Motion) and m.label.startswith("v1.6-e:")
                   for m in result.motions)
    assert result.decision.skipped is True


# ---------------------------------------------------------------------------
# 7. Scene shapes (single / multi / char+object / empty)
# ---------------------------------------------------------------------------


def test_single_character_scene(enabled):
    desc = {"characters": [{"name": "Solo", "x": 0.5, "y": 0.75}], "objects": []}
    result = choreo.apply_scene_choreography(
        [], visual_description=desc, previous_cast=frozenset(),
        next_cast=frozenset({("character", "solo")}), scene_index=0, duration=4.0,
    )
    enters = [m for m in result.motions if m.label == "v1.6-e:enter"]
    assert len(enters) == 1 and enters[0].target_id == "solo"


def test_multi_character_scene_schedules_all_introductions(enabled):
    desc = {"characters": [
        {"name": "Ana", "x": 0.25, "y": 0.75},
        {"name": "Ben", "x": 0.75, "y": 0.75},
    ], "objects": []}
    result = choreo.apply_scene_choreography(
        [], visual_description=desc, previous_cast=frozenset(),
        next_cast=frozenset({("character", "ana"), ("character", "ben")}),
        scene_index=0, duration=5.0,
    )
    enters = [m for m in result.motions if m.label == "v1.6-e:enter"]
    assert {m.target_id for m in enters} == {"ana", "ben"}
    for m in enters:
        m.validate(5.0)


def test_character_plus_object_scene(enabled):
    desc = make_desc()
    result = choreo.apply_scene_choreography(
        [], visual_description=desc, previous_cast=frozenset({("character", "hero")}),
        next_cast=frozenset({("character", "hero"), ("object", "ball")}),
        scene_index=1, duration=4.0,
        planning_metadata={"attention": {"primary_target": "Ball",
                                         "target_kind": "object"}},
    )
    enters = [m for m in result.motions if m.label == "v1.6-e:enter"]
    assert [m.target_id for m in enters] == ["ball"]
    emph = [m for m in result.motions if m.label == "v1.6-e:emphasis"]
    assert emph and emph[0].target_id == "ball"


def test_empty_scene_safely_skips(enabled):
    desc = {"characters": [], "objects": []}
    result = choreo.apply_scene_choreography(
        [], visual_description=desc, scene_index=0, duration=4.0,
        planning_metadata={"attention": {"primary_target": "Hero",
                                         "target_kind": "character"}},
    )
    assert result.decision.skipped is True
    assert not [m for m in result.motions if m.label.startswith("v1.6-e:")]


def test_text_only_scene_safely_skips(enabled):
    desc = {"characters": [], "objects": [], "text_elements": [{"text": "HI"}]}
    result = choreo.apply_scene_choreography(
        [], visual_description=desc, scene_index=0, duration=4.0,
    )
    assert result.decision.skipped is True


# --- marker: settling ---

# ---------------------------------------------------------------------------
# 8. Transition-aware settling and continuity
# ---------------------------------------------------------------------------


def test_settling_reports_unsettled_tail_motion_on_non_cut(enabled):
    existing = [_motion(mtype="move", start=3.5, duration=0.4)]
    result = choreo.apply_scene_choreography(
        existing, visual_description=make_desc(),
        previous_cast=frozenset({("character", "hero")}),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
        transition_to_next={"type": "crossfade"},
    )
    assert result.decision.transition_non_cut is True
    assert result.decision.transition_safe is False
    assert any("unsettled_tail_motion" in w for w in result.decision.warnings)


def test_settling_safe_when_tail_is_static_on_non_cut(enabled):
    existing = [_motion(mtype="move", start=0.5, duration=1.0)]
    result = choreo.apply_scene_choreography(
        existing, visual_description=make_desc(),
        previous_cast=frozenset({("character", "hero")}),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
        transition_to_next={"type": "crossfade"},
    )
    assert result.decision.transition_non_cut is True
    assert result.decision.transition_safe is True


def test_settling_not_evaluated_on_cut(enabled):
    existing = [_motion(mtype="move", start=3.5, duration=0.4)]
    result = choreo.apply_scene_choreography(
        existing, visual_description=make_desc(),
        previous_cast=frozenset({("character", "hero")}),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
        transition_to_next={"type": "cut"},
    )
    assert result.decision.transition_non_cut is False
    assert result.decision.transition_safe is True
    assert not any("unsettled" in w for w in result.decision.warnings)


def test_sequence_threads_previous_cast_across_scenes(enabled):
    descs = [
        {"characters": [{"name": "Hero", "x": 0.3, "y": 0.75}], "objects": []},
        {"characters": [
            {"name": "Hero", "x": 0.3, "y": 0.75},
            {"name": "New", "x": 0.7, "y": 0.75},
        ], "objects": []},
    ]
    out, report = choreo.apply_scene_choreography_sequence(
        [[], []], descs, durations=[4.0, 4.0],
        transitions_to_next=[{"type": "crossfade"}, None],
    )
    # Scene 0: Hero introduced from empty previous cast.
    scene0_enters = [m for m in out[0] if m.label == "v1.6-e:enter"]
    assert [m.target_id for m in scene0_enters] == ["hero"]
    # Scene 1: only New enters (Hero retained via threaded cast).
    scene1_enters = [m for m in out[1] if m.label == "v1.6-e:enter"]
    assert [m.target_id for m in scene1_enters] == ["new"]
    assert report.applied_count == 2


def test_sequence_reports_departures_with_transition_awareness(enabled):
    descs = [
        {"characters": [
            {"name": "Hero", "x": 0.3, "y": 0.75},
            {"name": "Guest", "x": 0.7, "y": 0.75},
        ], "objects": []},
        {"characters": [{"name": "Hero", "x": 0.3, "y": 0.75}], "objects": []},
    ]
    out, _ = choreo.apply_scene_choreography_sequence(
        [[], []], descs, durations=[4.0, 4.0],
        transitions_to_next=[{"type": "crossfade"}, None],
    )
    exits = [m for m in out[0] if m.label == "v1.6-e:exit"]
    assert [m.target_id for m in exits] == ["guest"]


def test_sequence_length_mismatch_safely_returns_unchanged(enabled):
    out, report = choreo.apply_scene_choreography_sequence(
        [[_motion()]], [make_desc(), make_desc()]
    )
    assert isinstance(out[0], list)
    assert report.applied_count == 0
    assert all(d.skipped for d in report.decisions)


# ---------------------------------------------------------------------------
# 9. Decision / report serialization and metadata shape
# ---------------------------------------------------------------------------


def test_decision_and_report_serialization(enabled):
    result = choreo.apply_scene_choreography(
        [], visual_description=hero_only_desc(), previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=2, duration=4.0,
    )
    payload = json.loads(json.dumps(result.decision.to_dict()))
    assert payload["scene_index"] == 2
    assert payload["introduced"] == ["character:hero"]
    assert payload["actions"][0]["kind"] == "enter"
    _, report = choreo.apply_scene_choreography_sequence(
        [[], []], [make_desc(), make_desc()], durations=[4.0, 4.0]
    )
    report_payload = json.loads(json.dumps(report.to_dict()))
    assert report_payload["applied_count"] == report.applied_count
    assert isinstance(report_payload["summary"], str)


def test_apply_never_writes_choreography_metadata(enabled):
    # V1.6-E is pure: the pipeline owns visual_description["choreography"].
    desc = make_desc()
    choreo.apply_scene_choreography(
        [], visual_description=desc, previous_cast=frozenset(),
        next_cast=frozenset({("character", "hero")}), scene_index=0, duration=4.0,
    )
    assert "choreography" not in desc
    assert "camera" not in desc  # read-only for camera context
