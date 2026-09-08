"""V1.4-F integration tests: feature-flagged visual planning integration.

Covers flag gating (default off), single planner execution per planning
phase, planner chaining (story -> diversity -> composition -> camera ->
attention), explicit-intent precedence, determinism, additive-only semantic
metadata, and safe handling of empty inputs.
"""
from __future__ import annotations

import copy
import inspect
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import MagicMock

import src.services.visual_beat_engine as beat_module
import src.services.visual_focus as focus_module
from src.models.content_package import Motion, Transition
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import (
    AutoPublishPipeline,
    ScenePlan,
    VideoPlan,
    VisualScene,
)
from src.services import (
    attention_planner as attention_module,
    camera_planner as camera_module,
    composition_planner as composition_module,
    visual_diversity as diversity_module,
    visual_story_planner as story_module,
)

PLANNERS = (
    (story_module.VisualStoryPlanner, "plan"),
    (diversity_module.VisualDiversityPolicy, "analyze"),
    (composition_module.CompositionPlanner, "plan"),
    (camera_module.CameraPlanner, "plan"),
    (attention_module.AttentionPlanner, "plan"),
)


def _scene(role, name, transition=None, camera_spec=None):
    return ScenePlan(
        narration=f"{role} evidence about memory",
        visual=VisualScene(
            scene_role=role,
            transition=transition,
            camera_spec=dict(camera_spec or {}),
            characters=[{"name": name, "x": 0.3, "y": 0.7}],
            objects=[{"name": f"{name}_object", "type": "brain", "x": 0.72, "y": 0.7}],
            text_elements=[{"text": role.title(), "size": "headline", "x": 0.5, "y": 0.12}],
        ),
    )


def _base_plan():
    return VideoPlan(
        title="V1.4-F Integration",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene("problem", "problem_subject"),
            _scene("solution", "solution_subject"),
        ],
    )


def _fake_render(monkeypatch):
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {
            "status": "completed",
            "scene_number": job.scene_number,
            "output_reference": f"scene_{job.scene_number}.mp4",
        }

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    return captured


def _wrap(monkeypatch, planner_cls, method_name, log):
    original = getattr(planner_cls, method_name)

    def wrapper(self, *args, **kwargs):
        log["calls"] += 1
        log["kwargs"].append(kwargs)
        result = original(self, *args, **kwargs)
        log["results"].append(result)
        return result

    monkeypatch.setattr(planner_cls, method_name, wrapper)


def _spy_logs():
    return {
        name: {"calls": 0, "kwargs": [], "results": []}
        for name in ("story", "diversity", "composition", "camera", "attention")
    }


def _wrap_all(monkeypatch, logs):
    _wrap(monkeypatch, story_module.VisualStoryPlanner, "plan", logs["story"])
    _wrap(monkeypatch, diversity_module.VisualDiversityPolicy, "analyze", logs["diversity"])
    _wrap(monkeypatch, composition_module.CompositionPlanner, "plan", logs["composition"])
    _wrap(monkeypatch, camera_module.CameraPlanner, "plan", logs["camera"])
    _wrap(monkeypatch, attention_module.AttentionPlanner, "plan", logs["attention"])


def _enable(monkeypatch, semantic=True, planner=True):
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", semantic)
    monkeypatch.setattr(pipeline_module, "VISUAL_STORY_PLANNER_ENABLED", planner)


def _segments(plan):
    return [
        {"scene_number": index + 1, "duration_seconds": 1.0}
        for index in range(len(plan.scenes))
    ]


def _run_render_scenes(monkeypatch, plan, semantic=True, planner=True):
    _enable(monkeypatch, semantic=semantic, planner=planner)
    captured = _fake_render(monkeypatch)
    pipeline = AutoPublishPipeline(output_directory="output/test-v14f")
    stage = pipeline._render_scenes(plan, _segments(plan))
    return stage, captured


def _chained_run(monkeypatch):
    logs = _spy_logs()
    _wrap_all(monkeypatch, logs)
    stage, jobs = _run_render_scenes(monkeypatch, _base_plan(), semantic=True, planner=True)
    return logs, stage, jobs


def _strip_planning(job_dict):
    """Remove the additive V1.4 metadata so enabled/disabled jobs compare equal."""
    stripped = dict(job_dict)
    description = dict(stripped.get("visual_description") or {})
    description.pop("visual_planning", None)
    stripped["visual_description"] = description
    return stripped


def _context_view(context):
    motion_result = context["motion_result"]
    transition = context["transition"]
    return {
        "beat": context["beat"].to_dict(),
        "focus": context["focus"].to_dict(),
        "motions": [m.to_dict() for m in motion_result.motions] if motion_result else None,
        "transition": transition.to_dict() if transition else None,
    }


# --- 1. Flag defaults --------------------------------------------------------


def test_v14_flag_defaults_to_false() -> None:
    assert pipeline_module.SEMANTIC_VISUALS_ENABLED is False
    assert pipeline_module.VISUAL_STORY_PLANNER_ENABLED is False


def test_v14_flag_is_independent_of_v13_flag() -> None:
    source = inspect.getsource(pipeline_module)
    assert "VISUAL_STORY_PLANNER_ENABLED = False" in source
    assert "if VISUAL_STORY_PLANNER_ENABLED:" in source


# --- 2. V1.4 does not execute when disabled -----------------------------------


def test_v14_does_not_execute_when_disabled(monkeypatch) -> None:
    _enable(monkeypatch, semantic=True, planner=False)
    _fake_render(monkeypatch)
    monkeypatch.setattr(
        AutoPublishPipeline, "_plan_visual_story", MagicMock(side_effect=AssertionError)
    )
    for planner_cls, method in PLANNERS:
        monkeypatch.setattr(planner_cls, method, MagicMock(side_effect=AssertionError))
    plan = _base_plan()
    pipeline = AutoPublishPipeline(output_directory="output/test-v14f")
    stage = pipeline._render_scenes(plan, _segments(plan))
    AutoPublishPipeline._plan_visual_story.assert_not_called()
    assert stage["status"] == "completed"
    assert "visual_planning" not in stage


# --- 3. V1.3 still works when V1.4 is disabled ---------------------------------


def test_v13_still_works_when_v14_disabled(monkeypatch) -> None:
    plan = _base_plan()
    stage, jobs = _run_render_scenes(monkeypatch, plan, semantic=True, planner=False)
    assert stage["status"] == "completed"
    assert "visual_planning" not in stage
    assert len(jobs) == 3
    for job in jobs:
        assert "semantics" in job.visual_description
        assert "qa_report" in job.visual_description
        assert "visual_planning" not in job.visual_description


# --- 4. V1.2 path unchanged when semantics are disabled -------------------------


def test_v12_path_unchanged_when_semantic_disabled(monkeypatch) -> None:
    plan = _base_plan()
    stage, jobs = _run_render_scenes(monkeypatch, plan, semantic=False, planner=False)
    assert stage["status"] == "completed"
    assert "visual_planning" not in stage
    for job in jobs:
        assert job.motions == []
        assert job.transition_to_next is None
        assert "semantics" not in (job.visual_description or {})
        assert "qa_report" not in (job.visual_description or {})
        assert "visual_planning" not in (job.visual_description or {})


# --- 5. Planners execute exactly once per planning phase ------------------------


def test_planners_execute_exactly_once_per_planning_phase(monkeypatch) -> None:
    logs = _spy_logs()
    _wrap_all(monkeypatch, logs)
    stage, _ = _run_render_scenes(monkeypatch, _base_plan(), semantic=True, planner=True)
    assert stage.get("visual_planning") is True
    for name, log in logs.items():
        assert log["calls"] == 1, name


# --- 6-10. Each plan reaches downstream planning ---------------------------------


def test_story_plan_reaches_downstream_planning(monkeypatch) -> None:
    logs, stage, jobs = _chained_run(monkeypatch)
    story_result = logs["story"]["results"][0]
    assert logs["diversity"]["kwargs"][0]["story_plan"] is story_result
    assert logs["composition"]["kwargs"][0]["story_plan"] is story_result
    assert logs["camera"]["kwargs"][0]["story_plan"] is story_result
    assert logs["attention"]["kwargs"][0]["story_plan"] is story_result
    treatments = [job.visual_description["visual_planning"]["treatment"] for job in jobs]
    assert treatments == [d.treatment for d in story_result.decisions]
    assert treatments == ["establish", "problem_focus", "solution_growth"]


def test_diversity_report_reaches_downstream_planning(monkeypatch) -> None:
    logs, stage, jobs = _chained_run(monkeypatch)
    diversity_result = logs["diversity"]["results"][0]
    assert logs["composition"]["kwargs"][0]["diversity_report"] is diversity_result
    assert logs["camera"]["kwargs"][0]["diversity_report"] is diversity_result
    assert logs["attention"]["kwargs"][0]["diversity_report"] is diversity_result
    for index, job in enumerate(jobs):
        diversity_meta = job.visual_description["visual_planning"]["diversity"]
        assert diversity_meta["scene_index"] == index


def test_composition_plan_reaches_downstream_planning(monkeypatch) -> None:
    logs, stage, jobs = _chained_run(monkeypatch)
    composition_result = logs["composition"]["results"][0]
    assert logs["camera"]["kwargs"][0]["composition_plan"] is composition_result
    assert logs["attention"]["kwargs"][0]["composition_plan"] is composition_result
    for index, job in enumerate(jobs):
        meta = job.visual_description["visual_planning"]["composition"]
        assert meta["scene_index"] == index


def test_camera_plan_reaches_downstream_planning(monkeypatch) -> None:
    logs, stage, jobs = _chained_run(monkeypatch)
    camera_result = logs["camera"]["results"][0]
    assert logs["attention"]["kwargs"][0]["camera_plan"] is camera_result
    for index, job in enumerate(jobs):
        meta = job.visual_description["visual_planning"]["camera"]
        assert meta["scene_index"] == index


def test_attention_plan_reaches_downstream_planning(monkeypatch) -> None:
    logs, stage, jobs = _chained_run(monkeypatch)
    attention_result = logs["attention"]["results"][0]
    assert stage.get("visual_planning") is True
    for index, job in enumerate(jobs):
        meta = job.visual_description["visual_planning"]["attention"]
        assert meta["scene_index"] == index
        assert meta["primary_target"] == attention_result.decisions[index].primary_target


# --- 11. Explicit motions remain unchanged --------------------------------------


def test_explicit_motions_remain_unchanged(monkeypatch) -> None:
    plan = _base_plan()
    explicit = Motion(
        type="scale",
        target="character",
        start_time=0,
        duration=1,
        parameters={"from": 1, "to": 1.1},
        target_id="problem_subject",
    )
    scene = plan.scenes[1]
    scene.visual.motions.append(explicit)
    before = copy.deepcopy(asdict(plan))
    stage_on, jobs_on = _run_render_scenes(monkeypatch, plan, semantic=True, planner=True)
    assert explicit in jobs_on[1].motions
    assert copy.deepcopy(asdict(plan)) == before
    stage_off, jobs_off = _run_render_scenes(monkeypatch, plan, semantic=True, planner=False)
    assert _strip_planning(jobs_on[1].to_dict()) == jobs_off[1].to_dict()


# --- 12. Explicit camera intent remains unchanged ---------------------------------


def test_explicit_camera_intent_remains_unchanged(monkeypatch) -> None:
    plan = VideoPlan(
        title="Camera Intent",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene(
                "problem",
                "problem_subject",
                camera_spec={"pattern": "static", "focus_target": "problem_subject"},
            ),
        ],
    )
    stage_on, jobs_on = _run_render_scenes(monkeypatch, plan, semantic=True, planner=True)
    stage_off, jobs_off = _run_render_scenes(monkeypatch, plan, semantic=True, planner=False)
    assert jobs_on[1].visual_description["camera"] == jobs_off[1].visual_description["camera"]
    assert _strip_planning(jobs_on[1].to_dict()) == jobs_off[1].to_dict()
    assert jobs_on[1].visual_description["visual_planning"]["recommended_camera"] == "static"


# --- 13. Explicit transitions remain unchanged ------------------------------------


def test_explicit_transitions_remain_unchanged(monkeypatch) -> None:
    plan = _base_plan()
    explicit = Transition(type="fade", duration=0.25)
    plan.scenes[1].visual.transition = explicit
    beats = AutoPublishPipeline._beat_inputs(plan)
    focus_results = AutoPublishPipeline._focus_results(plan, beats)
    contexts = AutoPublishPipeline._semantic_contexts(plan, beats=beats, focus_results=focus_results)
    planning = AutoPublishPipeline._plan_visual_story(plan, beats=beats, focus_results=focus_results)
    AutoPublishPipeline._merge_visual_planning(contexts, planning)
    assert contexts[1]["transition"] is None
    assert contexts[1]["visual_planning"]["recommended_transition"] is not None
    stage_on, jobs_on = _run_render_scenes(monkeypatch, plan, semantic=True, planner=True)
    stage_off, jobs_off = _run_render_scenes(monkeypatch, plan, semantic=True, planner=False)
    assert jobs_on[1].transition_to_next == explicit == jobs_off[1].transition_to_next
    assert _strip_planning(jobs_on[1].to_dict()) == jobs_off[1].to_dict()


# --- 14. V1.4 recommendations are deterministic ------------------------------------


def test_v14_recommendations_are_deterministic(monkeypatch) -> None:
    _enable(monkeypatch)
    plan = _base_plan()
    beats = AutoPublishPipeline._beat_inputs(plan)
    focus_results = AutoPublishPipeline._focus_results(plan, beats)
    first = AutoPublishPipeline._plan_visual_story(plan, beats=beats, focus_results=focus_results)
    second = AutoPublishPipeline._plan_visual_story(plan, beats=beats, focus_results=focus_results)
    assert {key: value.to_dict() for key, value in first.items()} == {
        key: value.to_dict() for key, value in second.items()
    }


# --- 15. No renderer dependency in planners ----------------------------------------


def test_no_renderer_dependency_in_planners() -> None:
    forbidden = (
        "stickman",
        "video_assembler",
        "ffmpeg",
        "piper",
        "scene_video_renderer",
        "render_stickman_job",
        "subprocess",
        "media_muxer",
    )
    for module in (
        story_module,
        diversity_module,
        composition_module,
        camera_module,
        attention_module,
    ):
        source = inspect.getsource(module)
        for token in forbidden:
            assert token not in source, (module.__name__, token)


# --- 16. No duplicate beat/focus computation ----------------------------------------


def test_no_duplicate_beat_or_focus_computation(monkeypatch) -> None:
    plan = _base_plan()
    beat_calls = []
    focus_calls = []
    original_beat = beat_module.VisualBeatEngine.detect_sequence
    original_focus = focus_module.VisualFocusResolver.resolve

    def spy_beat(self, scenes):
        beat_calls.append(len(scenes))
        return original_beat(self, scenes)

    def spy_focus(self, *args, **kwargs):
        focus_calls.append(args)
        return original_focus(self, *args, **kwargs)

    monkeypatch.setattr(beat_module.VisualBeatEngine, "detect_sequence", spy_beat)
    monkeypatch.setattr(focus_module.VisualFocusResolver, "resolve", spy_focus)

    _run_render_scenes(monkeypatch, plan, semantic=True, planner=False)
    baseline_beats, baseline_focus = list(beat_calls), len(focus_calls)

    beat_calls.clear()
    focus_calls.clear()
    _run_render_scenes(monkeypatch, plan, semantic=True, planner=True)

    assert beat_calls == baseline_beats == [len(plan.scenes)]
    assert len(focus_calls) == baseline_focus == len(plan.scenes)


# --- 17. Empty scenes remain safe ----------------------------------------------------


def test_empty_scenes_remain_safe() -> None:
    planning = AutoPublishPipeline._plan_visual_story(
        SimpleNamespace(scenes=[]), beats=[], focus_results={}
    )
    assert planning["story_plan"].decisions == ()
    assert planning["attention_plan"].decisions == ()
    AutoPublishPipeline._merge_visual_planning([], planning)

    plan = VideoPlan(title="Empty", scenes=[ScenePlan(narration="A scene", visual=VisualScene())])
    beats = AutoPublishPipeline._beat_inputs(plan)
    focus_results = AutoPublishPipeline._focus_results(plan, beats)
    contexts = AutoPublishPipeline._semantic_contexts(plan, beats=beats, focus_results=focus_results)
    planning = AutoPublishPipeline._plan_visual_story(plan, beats=beats, focus_results=focus_results)
    AutoPublishPipeline._merge_visual_planning(contexts, planning)
    assert contexts[0]["focus"].primary == ""
    assert contexts[0]["visual_planning"]["treatment"] == "establish"


# --- 18. Existing semantic metadata remains valid -------------------------------------


def test_existing_semantic_metadata_remains_valid(monkeypatch) -> None:
    _enable(monkeypatch)
    plan = _base_plan()
    beats = AutoPublishPipeline._beat_inputs(plan)
    focus_results = AutoPublishPipeline._focus_results(plan, beats)
    base_contexts = AutoPublishPipeline._semantic_contexts(
        plan, beats=beats, focus_results=focus_results
    )
    planning = AutoPublishPipeline._plan_visual_story(plan, beats=beats, focus_results=focus_results)
    merged_contexts = AutoPublishPipeline._semantic_contexts(
        plan, beats=beats, focus_results=focus_results
    )
    AutoPublishPipeline._merge_visual_planning(merged_contexts, planning)
    assert [_context_view(c) for c in merged_contexts] == [_context_view(c) for c in base_contexts]
    for context in merged_contexts:
        assert set(context) == {"beat", "focus", "motion_result", "transition", "visual_planning"}


# --- 19. Disabled and enabled paths remain distinguishable ------------------------------


def test_disabled_and_enabled_paths_remain_distinguishable(monkeypatch) -> None:
    plan = _base_plan()
    stage_on, _ = _run_render_scenes(monkeypatch, plan, semantic=True, planner=True)
    stage_mid, _ = _run_render_scenes(monkeypatch, plan, semantic=True, planner=False)
    stage_off, _ = _run_render_scenes(monkeypatch, plan, semantic=False, planner=False)
    assert stage_on.get("visual_planning") is True
    assert "visual_planning" not in stage_mid
    assert "visual_planning" not in stage_off
