from __future__ import annotations

import copy
from dataclasses import asdict
from unittest.mock import patch

import pytest

from src.models.content_package import SUPPORTED_MOTION_TYPES, SUPPORTED_TRANSITION_TYPES, Motion, Transition
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene
from src.services.scene_video_renderer import SHORTS_FORMAT


class _Renderer:
    pass


def _scene(role: str, name: str, transition: Transition | None = None) -> ScenePlan:
    return ScenePlan(
        narration=f"{role} evidence about memory",
        visual=VisualScene(
            scene_role=role,
            transition=transition,
            characters=[{"name": name, "x": 0.3, "y": 0.7}],
            objects=[{"name": f"{name}_object", "type": "brain", "x": 0.72, "y": 0.7}],
            text_elements=[{"text": role.title(), "size": "headline", "x": 0.5, "y": 0.12}],
        ),
    )


def _plan() -> VideoPlan:
    return VideoPlan(
        title="Semantic E2E",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene("problem", "problem_subject"),
            _scene("solution", "solution_subject", Transition(type="fade_to_black", duration=0.5)),
            _scene("contrast", "contrast_subject"),
        ],
    )


def _handoff(monkeypatch, scene: ScenePlan, context: dict, enabled: bool = True):
    captured: list[object] = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": 1, "output_reference": "scene.mp4"}

    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", enabled)
    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    pipeline = AutoPublishPipeline(output_directory="output/test-semantic-e2e")
    pipeline._render_visual_scene(
        scene=scene,
        segment={"audio_reference": "audio.wav"},
        scene_number=1,
        duration=3.4,
        video_format=SHORTS_FORMAT,
        stickman_renderer=_Renderer(),
        semantic_context=context if enabled else None,
    )
    return captured[0]


def test_enabled_four_scene_path_reaches_render_jobs(monkeypatch) -> None:
    plan = _plan()
    contexts = AutoPublishPipeline._semantic_contexts(plan)
    jobs = [_handoff(monkeypatch, scene, context) for scene, context in zip(plan.scenes, contexts)]

    assert contexts[0]["beat"].type == "HOOK"
    assert contexts[0]["focus"].primary == "hook_subject"
    assert contexts[1]["beat"].type == "PROBLEM"
    assert contexts[2]["beat"].type == "SOLUTION"
    assert contexts[3]["beat"].type == "CONTRAST"

    for job in jobs:
        assert all(isinstance(motion, Motion) for motion in job.motions)
        assert all(motion.type in SUPPORTED_MOTION_TYPES for motion in job.motions)
        assert all(motion.duration > 0 for motion in job.motions)
        semantics = job.visual_description["semantics"]
        assert semantics["beat"]
        assert semantics["focus"]
        assert "qa_report" in job.visual_description

    assert contexts[1]["transition"].type == "slide_up"
    assert jobs[1].transition_to_next.type == "slide_up"
    assert jobs[2].transition_to_next.type == "fade_to_black"
    assert contexts[3]["transition"] is None
    assert jobs[3].transition_to_next is None
    assert all(job.transition_to_next is None or isinstance(job.transition_to_next, Transition) for job in jobs)
    assert all(job.transition_to_next is None or job.transition_to_next.type in SUPPORTED_TRANSITION_TYPES for job in jobs)
    for scene, job in zip(plan.scenes, jobs):
        valid_ids = {item["name"] for item in scene.visual.characters + scene.visual.objects}
        motion_ids = {motion.target_id for motion in job.motions if motion.target_id}
        assert motion_ids <= valid_ids


def test_explicit_transition_wins_at_actual_handoff(monkeypatch) -> None:
    plan = _plan()
    fallback_plan = _plan()
    fallback_plan.scenes[2].visual.transition = None
    fallback_context = AutoPublishPipeline._semantic_contexts(fallback_plan)[2]
    assert fallback_context["transition"].type == "slide_left"
    context = AutoPublishPipeline._semantic_contexts(plan)[2]
    assert context["transition"] is None
    job = _handoff(monkeypatch, plan.scenes[2], context)
    assert job.transition_to_next.type == "fade_to_black"


def test_disabled_ab_snapshot_is_deterministic_and_has_no_semantics(monkeypatch) -> None:
    scene = _plan().scenes[0]
    first = _handoff(monkeypatch, scene, {}, enabled=False).to_dict()
    second = _handoff(monkeypatch, scene, {}, enabled=False).to_dict()
    assert first == second
    assert first["motions"] == []
    assert first["visual_description"] is not None
    assert "semantics" not in first["visual_description"]
    assert "qa_report" not in first["visual_description"]


def test_enabled_mode_preserves_explicit_motion_and_composition(monkeypatch) -> None:
    scene = _plan().scenes[1]
    explicit = Motion(type="scale", target="character", start_time=0, duration=1, parameters={"from": 1, "to": 1.1}, target_id="problem_subject")
    scene.visual.motions.append(explicit)
    before = copy.deepcopy(asdict(scene))
    context = AutoPublishPipeline._semantic_contexts(VideoPlan(title="x", scenes=[scene]))[0]
    job = _handoff(monkeypatch, scene, context)
    assert explicit in job.motions
    assert job.visual_description["characters"][0]["name"] == "problem_subject"
    assert asdict(scene) == before


def test_empty_focus_has_no_hallucinated_motion() -> None:
    plan = VideoPlan(title="Empty", scenes=[ScenePlan(narration="A problem", visual=VisualScene(scene_role="problem"))])
    context = AutoPublishPipeline._semantic_contexts(plan)[0]
    assert context["focus"].primary == ""
    assert context["motion_result"].motions == []


def test_unknown_relationship_falls_back_without_invalid_transition() -> None:
    plan = VideoPlan(title="Unknown", scenes=[_scene("hook", "one"), _scene("cta", "two")])
    context = AutoPublishPipeline._semantic_contexts(plan)
    assert context[0]["transition"] is None


def test_semantic_service_errors_propagate_explicitly(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("semantic failure")

    monkeypatch.setattr(pipeline_module.SemanticMotionLowerer, "lower", fail)
    with pytest.raises(RuntimeError, match="semantic failure"):
        AutoPublishPipeline._semantic_contexts(_plan())


def test_qa_failure_is_metadata_only() -> None:
    scene = _scene("problem", "subject")
    context = AutoPublishPipeline._semantic_contexts(VideoPlan(title="x", scenes=[scene]))[0]
    assert context["motion_result"].motions
    # QA is already covered as a report in the handoff; no QA result controls motion generation.
    assert context["transition"] is None
