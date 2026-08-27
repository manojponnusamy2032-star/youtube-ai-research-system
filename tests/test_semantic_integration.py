from __future__ import annotations

import copy
from dataclasses import asdict
from unittest.mock import MagicMock, patch

from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene
from src.models.content_package import Transition
from src.services.scene_video_renderer import SHORTS_FORMAT


class _Renderer:
    pass


def _plan(explicit_transition: Transition | None = None) -> VideoPlan:
    return VideoPlan(
        title="Integration",
        scenes=[
            ScenePlan(
                narration="The problem is studying longer.",
                visual=VisualScene(
                    scene_role="problem",
                    characters=[{"name": "student", "x": 0.35, "y": 0.7}],
                    objects=[{"name": "desk", "type": "desk", "x": 0.75, "y": 0.7}],
                    text_elements=[{"text": "Problem", "size": "headline", "x": 0.5, "y": 0.12}],
                ),
            ),
            ScenePlan(
                narration="The solution improves memory.",
                visual=VisualScene(
                    scene_role="solution",
                    transition=explicit_transition,
                    characters=[{"name": "student", "x": 0.35, "y": 0.7}],
                    objects=[{"name": "brain", "type": "brain", "x": 0.75, "y": 0.7}],
                    text_elements=[{"text": "Solution", "size": "headline", "x": 0.5, "y": 0.12}],
                ),
            ),
        ],
    )


def _capture_job(monkeypatch, scene: ScenePlan, enabled: bool) -> object:
    captured: list[object] = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": 1, "output_reference": "scene.mp4"}

    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", enabled)
    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    pipeline = AutoPublishPipeline(output_directory="output/test-integration")
    pipeline._render_visual_scene(
        scene=scene,
        segment={"audio_reference": "audio.wav"},
        scene_number=1,
        duration=3.4,
        video_format=SHORTS_FORMAT,
        stickman_renderer=_Renderer(),
        semantic_context=None if not enabled else pipeline._semantic_contexts(VideoPlan(title="x", scenes=[scene]))[0],
    )
    return captured[0]


def test_feature_flag_off_preserves_v12_handoff(monkeypatch) -> None:
    scene = _plan().scenes[0]
    job = _capture_job(monkeypatch, scene, enabled=False)
    assert job.motions == []
    assert "semantics" not in (job.visual_description or {})
    assert "qa_report" not in (job.visual_description or {})


def test_feature_flag_off_does_not_compute_semantics(monkeypatch) -> None:
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", False)
    monkeypatch.setattr(AutoPublishPipeline, "_semantic_contexts", MagicMock(side_effect=AssertionError))
    pipeline = AutoPublishPipeline(output_directory="output/test-integration")
    pipeline._render_scenes(_plan(), [{"scene_number": 1, "duration_seconds": 1.0}, {"scene_number": 2, "duration_seconds": 1.0}])
    AutoPublishPipeline._semantic_contexts.assert_not_called()


def test_feature_flag_on_adds_semantics_and_motions(monkeypatch) -> None:
    job = _capture_job(monkeypatch, _plan().scenes[0], enabled=True)
    assert job.motions
    assert {motion.type for motion in job.motions} >= {"fade", "scale"}
    assert "semantics" in job.visual_description
    assert job.visual_description["semantics"]["beat"]["type"] == "PROBLEM"


def test_transition_is_injected_only_when_absent(monkeypatch) -> None:
    plan = _plan()
    contexts = AutoPublishPipeline._semantic_contexts(plan)
    assert contexts[0]["transition"].type == "slide_up"

    explicit = Transition(type="fade", duration=0.25)
    explicit_plan = _plan(explicit)
    explicit_contexts = AutoPublishPipeline._semantic_contexts(explicit_plan)
    assert explicit_contexts[1]["transition"] is None


def test_explicit_transition_is_preserved_in_render_job(monkeypatch) -> None:
    explicit = Transition(type="fade", duration=0.25)
    job = _capture_job(monkeypatch, _plan(explicit).scenes[1], enabled=True)
    assert job.transition_to_next == explicit


def test_qa_report_is_attached(monkeypatch) -> None:
    job = _capture_job(monkeypatch, _plan().scenes[0], enabled=True)
    report = job.visual_description["qa_report"]
    assert report["scene"] == "scene_001"
    assert isinstance(report["checks"], list)
    assert isinstance(report["passed"], bool)


def test_semantic_context_is_deterministic() -> None:
    plan = _plan()
    first = AutoPublishPipeline._semantic_contexts(plan)
    second = AutoPublishPipeline._semantic_contexts(plan)
    assert [item["beat"].to_dict() for item in first] == [item["beat"].to_dict() for item in second]
    assert [item["transition"].to_dict() if item["transition"] else None for item in first] == [item["transition"].to_dict() if item["transition"] else None for item in second]


def test_semantic_context_does_not_mutate_plan() -> None:
    plan = _plan()
    before = copy.deepcopy(asdict(plan))
    AutoPublishPipeline._semantic_contexts(plan)
    assert asdict(plan) == before


def test_empty_semantics_are_safe() -> None:
    plan = VideoPlan(title="Empty", scenes=[ScenePlan(narration="A scene", visual=VisualScene())])
    context = AutoPublishPipeline._semantic_contexts(plan)[0]
    assert context["motion_result"].motions == []
    assert context["focus"].primary == ""


def test_renderer_module_is_not_modified_by_integration() -> None:
    assert pipeline_module.StickmanRenderer.__module__ == "src.services.stickman_renderer"
