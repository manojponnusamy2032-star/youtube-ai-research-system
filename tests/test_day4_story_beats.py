"""Day-4 tests: StoryBeatPlanner — ScriptPackage -> typed story beats.

Covers: beat typing per beat vocabulary, importance/emphasis scoring,
duration allocation preserving the script total, story-arc assignment,
key-message extraction, and graceful handling of empty scripts.
"""
from __future__ import annotations

import pytest

from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.story_beat import SUPPORTED_BEAT_TYPES
from src.services.story_beat_planner import StoryBeatPlanner


def _make_script(**overrides):
    defaults = {
        "topic": "AI Learning",
        "title": "My AI Title",
        "hook": "Test hook",
        "sections": [
            ScriptSection(
                heading="Intro",
                narration="Welcome to this video about AI learning strategies.",
                duration_seconds=10,
            ),
            ScriptSection(
                heading="Main Point",
                narration="Here is the main content of the video.",
                duration_seconds=15,
            ),
            ScriptSection(
                heading="Conclusion",
                narration="Thanks for watching this video.",
                duration_seconds=8,
            ),
        ],
        "call_to_action": "Subscribe",
        "total_duration_seconds": 33,
        "intro": "Welcome",
        "section_payloads": [{"h": "Intro"}],
        "scene_payloads": [{"s": 1}],
        "estimated_duration_minutes": 5,
    }
    defaults.update(overrides)
    return ScriptPackage(**defaults)


def test_plan_returns_one_beat_per_section():
    plan = StoryBeatPlanner().plan(_make_script())
    assert len(plan.beats) == 3


def test_beat_ids_unique_and_ordered():
    plan = StoryBeatPlanner().plan(_make_script())
    ids = [b.beat_id for b in plan.beats]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_beat_types_in_supported_vocabulary():
    plan = StoryBeatPlanner().plan(_make_script())
    for beat in plan.beats:
        assert beat.beat_type in SUPPORTED_BEAT_TYPES


def test_hook_content_detected_as_hook():
    script = _make_script(sections=[
        ScriptSection(
            heading="Hook",
            narration="Did you know most people quit before they succeed?",
            duration_seconds=10,
        ),
        ScriptSection(
            heading="Body",
            narration="Here we explain the underlying mechanism in detail.",
            duration_seconds=15,
        ),
    ], total_duration_seconds=25)
    plan = StoryBeatPlanner().plan(script)
    assert plan.beats[0].beat_type == "HOOK"


def test_cta_content_detected_as_cta():
    script = _make_script(sections=[
        ScriptSection(
            heading="Body",
            narration="Here we explain the underlying mechanism in detail.",
            duration_seconds=15,
        ),
        ScriptSection(
            heading="Outro",
            narration="Subscribe to the channel and start today.",
            duration_seconds=10,
        ),
    ], total_duration_seconds=25)
    plan = StoryBeatPlanner().plan(script)
    assert plan.beats[-1].beat_type == "CTA"


def test_importance_scores_in_range():
    plan = StoryBeatPlanner().plan(_make_script())
    for beat in plan.beats:
        assert 0.0 <= beat.importance <= 1.0


def test_emphasis_labels_valid():
    plan = StoryBeatPlanner().plan(_make_script())
    for beat in plan.beats:
        assert beat.emphasis in ("low", "medium", "high")


def test_hook_gets_higher_importance_than_explanation():
    script = _make_script(sections=[
        ScriptSection(
            heading="Hook",
            narration="Did you know the truth about learning?",
            duration_seconds=10,
        ),
        ScriptSection(
            heading="Filler",
            narration="The details are as follows.",
            duration_seconds=10,
        ),
    ], total_duration_seconds=20)
    plan = StoryBeatPlanner().plan(script)
    hook = next(b for b in plan.beats if b.beat_type == "HOOK")
    other = next(b for b in plan.beats if b.beat_type != "HOOK")
    assert hook.importance >= other.importance


def test_duration_allocation_preserves_total():
    plan = StoryBeatPlanner().plan(_make_script())
    assert sum(b.duration_seconds for b in plan.beats) == 33
    assert plan.total_duration_seconds == 33


def test_all_durations_positive():
    plan = StoryBeatPlanner().plan(_make_script())
    assert all(b.duration_seconds >= 3 for b in plan.beats)


def test_key_messages_populated():
    plan = StoryBeatPlanner().plan(_make_script())
    assert all(b.key_message for b in plan.beats)


def test_narration_preserved():
    plan = StoryBeatPlanner().plan(_make_script())
    assert plan.beats[0].narration == "Welcome to this video about AI learning strategies."


def test_story_arc_assignment():
    plan = StoryBeatPlanner().plan(_make_script())
    assert plan.beats[0].story_arc == "opening"
    assert plan.beats[-1].story_arc == "resolution"
    assert all(b.story_arc in ("opening", "development", "resolution") for b in plan.beats)


def test_topic_and_title_preserved():
    plan = StoryBeatPlanner().plan(_make_script())
    assert plan.topic == "AI Learning"
    assert plan.title == "My AI Title"


def test_empty_script_returns_empty_plan():
    plan = StoryBeatPlanner().plan(_make_script(sections=[], total_duration_seconds=0))
    assert plan.beats == []
    assert plan.total_duration_seconds == 0
    assert plan.warnings


def test_scene_counts_positive():
    plan = StoryBeatPlanner().plan(_make_script())
    assert all(b.scene_count >= 1 for b in plan.beats)


def test_partial_verb_does_not_match_cta_keyword():
    """'followed' must never match the CTA keyword 'follow' (word-boundary fix)."""
    script = _make_script(sections=[
        ScriptSection(
            heading="Plateau",
            narration="Skill growth is a staircase of long plateaus followed by sudden jumps.",
            duration_seconds=12,
        ),
    ], total_duration_seconds=12)
    plan = StoryBeatPlanner().plan(script)
    assert plan.beats[0].beat_type != "CTA"


def test_contrast_keyword_not_matched_inside_word():
    """'button' must not match the CONTRAST keyword 'but'."""
    script = _make_script(sections=[
        ScriptSection(
            heading="Hmm",
            narration="Press the big red button and the system will respond.",
            duration_seconds=12,
        ),
    ], total_duration_seconds=12)
    plan = StoryBeatPlanner().plan(script)
    assert plan.beats[0].beat_type != "CONTRAST"
