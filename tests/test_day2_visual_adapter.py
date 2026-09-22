"""Tests for the Day-2 Visual Adapter."""
from __future__ import annotations
import pytest
from src.adapters.visual.yairs import RealVisualPlannerAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan


def _make_script(**overrides):
    defaults = {
        "topic": "AI Learning", "title": "My AI Title", "hook": "Test hook",
        "sections": [
            ScriptSection(heading="Intro", narration="Welcome to this video about AI learning strategies.", duration_seconds=10),
            ScriptSection(heading="Main Point", narration="Here is the main content of the video.", duration_seconds=15),
            ScriptSection(heading="Conclusion", narration="Thanks for watching this video.", duration_seconds=8),
        ],
        "call_to_action": "Subscribe", "total_duration_seconds": 33,
        "intro": "Welcome", "section_payloads": [{"h": "Intro"}], "scene_payloads": [{"s": 1}],
        "estimated_duration_minutes": 5,
    }
    defaults.update(overrides)
    return ScriptPackage(**defaults)


def test_returns_visual_plan():
    result = RealVisualPlannerAgent().run(_make_script())
    assert isinstance(result, VisualPlan)


def test_topic_preserved():
    result = RealVisualPlannerAgent().run(_make_script())
    assert result.topic == "AI Learning"


def test_title_preserved():
    result = RealVisualPlannerAgent().run(_make_script())
    assert result.title == "My AI Title"


def test_scene_count():
    result = RealVisualPlannerAgent().run(_make_script())
    assert len(result.scenes) == 3


def test_scene_count_matches_sections():
    script = _make_script(sections=[
        ScriptSection(heading="S1", narration="N1", duration_seconds=5),
        ScriptSection(heading="S2", narration="N2", duration_seconds=10),
    ])
    result = RealVisualPlannerAgent().run(script)
    assert len(result.scenes) == 2


def test_scene_numbering_ordered():
    result = RealVisualPlannerAgent().run(_make_script())
    numbers = [s.scene_number for s in result.scenes]
    assert numbers == [1, 2, 3]


def test_scene_durations_positive():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.duration_seconds > 0 for s in result.scenes)


def test_scene_durations_match_sections():
    result = RealVisualPlannerAgent().run(_make_script())
    assert result.scenes[0].duration_seconds == 10
    assert result.scenes[1].duration_seconds == 15
    assert result.scenes[2].duration_seconds == 8


def test_narration_preserved():
    result = RealVisualPlannerAgent().run(_make_script())
    assert result.scenes[0].narration == "Welcome to this video about AI learning strategies."
    assert result.scenes[1].narration == "Here is the main content of the video."


def test_render_type_valid():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.render_type == "stickman_animation" for s in result.scenes)


def test_visual_prompt_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.visual_prompt for s in result.scenes)


def test_animation_instructions_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.animation_instructions for s in result.scenes)


def test_camera_instructions_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.camera_instructions for s in result.scenes)


def test_motions_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(len(s.motions) > 0 for s in result.scenes)


def test_transitions_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.transition_to_next is not None for s in result.scenes)


def test_last_scene_transition_is_fade():
    result = RealVisualPlannerAgent().run(_make_script())
    assert result.scenes[-1].transition_to_next["type"] == "fade_to_black"


def test_audio_request_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.audio_request is not None for s in result.scenes)
    assert all(s.audio_request["narration_text"] for s in result.scenes)


def test_visual_description_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(s.visual_description for s in result.scenes)


def test_render_job_plan_populated():
    result = RealVisualPlannerAgent().run(_make_script())
    assert result.render_job_plan["total_jobs"] == 3
    assert len(result.render_job_plan["jobs"]) == 3


def test_render_job_plan_has_job_ids():
    result = RealVisualPlannerAgent().run(_make_script())
    assert all(j["job_id"] for j in result.render_job_plan["jobs"])


def test_render_job_plan_has_scene_numbers():
    result = RealVisualPlannerAgent().run(_make_script())
    assert [j["scene_number"] for j in result.render_job_plan["jobs"]] == [1, 2, 3]


def test_total_duration_consistent():
    result = RealVisualPlannerAgent().run(_make_script())
    assert result.total_duration_seconds == 33
    assert result.render_job_plan["total_duration_seconds"] == 33


def test_empty_sections_raises():
    agent = RealVisualPlannerAgent()
    with pytest.raises(PipelineStageError):
        agent.run(_make_script(sections=[]))


def test_scene_count_greater_than_zero():
    result = RealVisualPlannerAgent().run(_make_script())
    assert len(result.scenes) > 0
