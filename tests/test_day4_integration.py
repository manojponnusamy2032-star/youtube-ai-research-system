"""Day-4 tests: IntelligentVisualPlannerAgent (integration).

Covers: ScriptPackage -> StoryBeats -> VisualBeats -> VisualPlan,
scene structure compatible with the renderer contract, consecutive
scene visual variety (anti-static), and factory/CLI wiring.
"""
from __future__ import annotations

import pytest

from src.orchestration.agents.visual.intelligent import (
    IntelligentVisualPlannerAgent,
)
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.visual import VisualPlan
from src.orchestration.schemas.story_beat import SUPPORTED_BEAT_TYPES
from src.services.story_beat_planner import StoryBeatPlanner
from src.services.visual_beat_planner import VisualBeatPlanner


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
    }
    defaults.update(overrides)
    return ScriptPackage(**defaults)


def test_returns_visual_plan():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert isinstance(result, VisualPlan)


def test_topic_preserved():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert result.topic == "AI Learning"


def test_title_preserved():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert result.title == "My AI Title"


def test_scenes_non_empty():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert len(result.scenes) > 0


def test_scene_numbering_ordered():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    numbers = [s.scene_number for s in result.scenes]
    assert numbers == list(range(1, len(numbers) + 1))


def test_scene_durations_positive():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.duration_seconds > 0 for s in result.scenes)


def test_render_type_valid():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.render_type == "stickman_animation" for s in result.scenes)


def test_visual_prompt_populated():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.visual_prompt for s in result.scenes)


def test_animation_instructions_populated():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.animation_instructions for s in result.scenes)


def test_camera_instructions_populated():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.camera_instructions for s in result.scenes)


def test_motions_populated():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(len(s.motions) > 0 for s in result.scenes)


def test_transitions_populated():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.transition_to_next is not None for s in result.scenes)


def test_last_scene_transition_is_fade():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert result.scenes[-1].transition_to_next["type"] == "fade_to_black"


def test_audio_request_populated():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.audio_request is not None for s in result.scenes)
    assert all(s.audio_request["narration_text"] for s in result.scenes)


def test_visual_description_populated():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert all(s.visual_description for s in result.scenes)


def test_render_job_plan_structure():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert result.render_job_plan["total_jobs"] == len(result.scenes)
    assert len(result.render_job_plan["jobs"]) == len(result.scenes)
    assert all(j["job_id"] for j in result.render_job_plan["jobs"])
    assert [j["scene_number"] for j in result.render_job_plan["jobs"]] == list(
        range(1, len(result.scenes) + 1)
    )


def test_total_duration_consistent():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert result.total_duration_seconds == result.render_job_plan[
        "total_duration_seconds"]
    assert result.total_duration_seconds == sum(
        s.duration_seconds for s in result.scenes)


def test_consecutive_scenes_differ_visually():
    result = IntelligentVisualPlannerAgent().run(_make_script())
    assert len(result.scenes) >= 2
    for prev, curr in zip(result.scenes, result.scenes[1:]):
        differs = (
            prev.camera_instructions != curr.camera_instructions
            or prev.character_action != curr.character_action
            or prev.visual_prompt != curr.visual_prompt
        )
        assert differs, f"Scenes {prev.scene_number} and {curr.scene_number} identical"


def test_factory_intelligent_mode(tmp_path):
    from src.orchestration.agents.factory import build_stage_agents
    agents = build_stage_agents(mode="intelligent")
    assert "visual_plan" in agents
    assert isinstance(
        agents["visual_plan"], IntelligentVisualPlannerAgent)


def test_day4_vocabulary_covers_required_beats():
    required = {"HOOK", "PROBLEM", "EXPLANATION", "EXAMPLE", "CONTRAST",
                "INSIGHT", "ACTION", "CONCLUSION"}
    assert required <= set(SUPPORTED_BEAT_TYPES)


def test_meaningful_beats_receive_dedicated_visual_treatment():
    script = _make_script(sections=[
        ScriptSection(
            heading="Problem",
            narration="The problem is that focus drops after ten minutes of study.",
            duration_seconds=12,
        ),
        ScriptSection(
            heading="Insight",
            narration="Your brain is not failing. Your method is. The real issue is feedback.",
            duration_seconds=14,
        ),
        ScriptSection(
            heading="Next step",
            narration="Build a system: one focused 25-minute session with tight feedback today.",
            duration_seconds=12,
        ),
    ], total_duration_seconds=38)
    story = StoryBeatPlanner().plan(script)
    assert len(story.beats) == 3
    visual = VisualBeatPlanner().plan(story)
    assert len(visual.beats) >= 3
    assert all(b.scene_purpose for b in visual.beats)
    assert all(len(b.state_changed) > 0 for b in visual.beats[1:])


def test_anti_static_no_long_identical_run():
    script = _make_script(sections=[
        ScriptSection(heading=f"S{i}", narration=f"Explanation part {i} about study.",
                      duration_seconds=10)
        for i in range(1, 5)
    ], total_duration_seconds=40)
    result = IntelligentVisualPlannerAgent().run(script)
    assert len(result.scenes) >= 4
    run = 1
    worst = 1
    for prev, curr in zip(result.scenes, result.scenes[1:]):
        same = (
            prev.camera_instructions == curr.camera_instructions
            and prev.character_action == curr.character_action
            and (prev.visual_description.get("environment", {}).get("type")
                 == curr.visual_description.get("environment", {}).get("type"))
        )
        if same:
            run += 1
            worst = max(worst, run)
        else:
            run = 1
    assert worst <= 2, f"static run of {worst} consecutive identical scenes"


def test_story_pipeline_end_to_end_types():
    script = _make_script()
    story = StoryBeatPlanner().plan(script)
    visual = VisualBeatPlanner().plan(story)
    result = IntelligentVisualPlannerAgent().run(script)
    assert len(story.beats) == len(script.sections)
    assert len(visual.beats) == len(result.scenes)
    assert sum(s.duration_seconds for s in result.scenes) == result.total_duration_seconds
