"""Day-4 tests (part 1): VisualBeatPlanner — StoryBeats -> VisualBeats.
"""
from __future__ import annotations

from src.orchestration.schemas.story_beat import StoryBeat, StoryBeatPlan
from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.services.visual_beat_planner import VisualBeatPlanner


def _beat(i, beat_type="EXPLANATION", emphasis="medium", duration=10,
          heading="Heading", narration="Some narration.", importance=0.6):
    return StoryBeat(
        beat_id=f"beat-{i:02d}",
        beat_type=beat_type,
        narration=narration,
        heading=heading,
        key_message=heading,
        importance=importance,
        emphasis=emphasis,
        duration_seconds=duration,
        scene_count=1,
        subject="",
        story_arc="development",
    )


def _story_plan():
    return StoryBeatPlan(
        topic="AI Learning",
        title="My AI Title",
        beats=[
            _beat(1, "HOOK", "high", 10, "Intro", "Welcome hook.", 0.95),
            _beat(2, "PROBLEM", "high", 12, "Main Point", "The problem text.", 0.9),
            _beat(3, "CTA", "medium", 8, "Outro", "Thanks for watching.", 0.6),
        ],
        total_duration_seconds=30,
        warnings=[],
    )


def test_plan_produces_one_beat_per_story_beat():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert len(plan.beats) == 3


def test_scene_numbering_ordered():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert [b.scene_number for b in plan.beats] == [1, 2, 3]


def test_story_beat_linkage():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert plan.beats[0].story_beat_id == "beat-01"
    assert plan.beats[1].story_beat_id == "beat-02"


def test_scene_purposes_populated():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert all(b.scene_purpose for b in plan.beats)


def test_camera_patterns_in_supported_vocabulary():
    plan = VisualBeatPlanner().plan(_story_plan())
    for beat in plan.beats:
        assert beat.camera_pattern in SUPPORTED_CAMERA_PATTERNS


def test_narration_preserved():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert plan.beats[0].narration_text == "Welcome hook."
    assert plan.beats[1].narration_text == "The problem text."


def test_emphasis_score_matches_story_importance():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert plan.beats[0].emphasis_score == 0.95
    assert plan.beats[1].emphasis_score == 0.9


def test_emphasis_labels_preserved():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert plan.beats[0].emphasis_label == "high"
    assert plan.beats[2].emphasis_label == "medium"


def test_high_emphasis_has_active_camera():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert plan.beats[0].camera_pattern != "static"


def test_last_transition_is_fade_to_black():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert plan.beats[-1].transition_type == "fade_to_black"


def test_all_transitions_populated():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert all(b.transition_type for b in plan.beats)


def test_total_duration_preserved():
    plan = VisualBeatPlanner().plan(_story_plan())
    total = sum(b.duration_seconds for b in plan.beats)
    assert abs(total - 30) <= len(plan.beats)


def test_all_durations_positive():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert all(b.duration_seconds >= 3 for b in plan.beats)


def test_anti_static_state_changes_non_empty():
    plan = VisualBeatPlanner().plan(_story_plan())
    for beat in plan.beats[1:]:
        assert len(beat.state_changed) > 0, (
            f"Scene {beat.scene_number}: no visual state change recorded"
        )


def test_state_progression_matches_beats():
    plan = VisualBeatPlanner().plan(_story_plan())
    assert len(plan.state_progression) == len(plan.beats)
    for changes, beat in zip(plan.state_progression, plan.beats):
        assert changes == beat.state_changed


def test_empty_story_plan_returns_empty_visual_plan():
    empty = StoryBeatPlan(topic="t", title="T", beats=[],
                          total_duration_seconds=0, warnings=[])
    plan = VisualBeatPlanner().plan(empty)
    assert plan.beats == []
    assert plan.total_duration_seconds == 0
    assert plan.warnings


def test_identical_adjacent_beats_forced_to_change():
    sb = StoryBeatPlan(
        topic="t", title="T",
        beats=[
            _beat(1, "EXPLANATION", "medium", 10, "A", "Explanation here."),
            _beat(2, "EXPLANATION", "medium", 10, "B", "More explanation."),
            _beat(3, "EXPLANATION", "medium", 10, "C", "Even more explanation."),
        ],
        total_duration_seconds=30,
        warnings=[],
    )
    plan = VisualBeatPlanner().plan(sb)
    for beat in plan.beats[1:]:
        assert len(beat.state_changed) > 0


def test_problem_beat_gets_frustrated_emotion():
    sb = StoryBeatPlan(
        topic="t", title="T",
        beats=[_beat(1, "PROBLEM", "high", 10, "P", "A serious problem.")],
        total_duration_seconds=10,
        warnings=[],
    )
    plan = VisualBeatPlanner().plan(sb)
    assert plan.beats[0].character_emotion == "frustrated"
