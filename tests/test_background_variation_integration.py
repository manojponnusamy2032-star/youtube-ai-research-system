"""V1.6-A background variation pipeline integration tests.

Pipeline-level tests proving that:
- variation OFF preserves existing V1.2--V1.5 behavior exactly;
- variation ON fills empty environments independently of V1.3/V1.4/V1.5;
- explicit environment intent is never overwritten;
- adjacent scenes receive different backdrops;
- the layer is deterministic and never mutates plan inputs.
"""
from __future__ import annotations

import copy
import json

import src.services.background_variation as bgv_module
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import (
    AutoPublishPipeline,
    ScenePlan,
    VideoPlan,
    VisualScene,
)
from src.services.scene_composition import SUPPORTED_ENVIRONMENTS


def _scene(role, name, environment=None):
    return ScenePlan(
        narration=f"{role} evidence about memory",
        visual=VisualScene(
            scene_role=role,
            characters=[{"name": name, "x": 0.3, "y": 0.7}],
            objects=[{"name": f"{name}_object", "type": "brain", "x": 0.72, "y": 0.7}],
            text_elements=[{"text": role.title(), "size": "headline", "x": 0.5, "y": 0.12}],
            environment=dict(environment or {}),
        ),
    )


def _base_plan(explicit_environment_index=None):
    scenes = [
        _scene("hook", "hook_subject"),
        _scene("problem", "problem_subject"),
        _scene("solution", "solution_subject"),
    ]
    if explicit_environment_index is not None:
        scenes[explicit_environment_index] = _scene(
            "problem",
            "problem_subject",
            environment={"type": "study_desk", "ground_y": 0.78},
        )
    return VideoPlan(title="V1.6 Integration", scenes=scenes)


def _segments(plan):
    return [
        {"scene_number": index + 1, "duration_seconds": 1.0}
        for index in range(len(plan.scenes))
    ]


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


def _run_render_scenes(monkeypatch, plan, variation=False, semantic=False, planner=False):
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", semantic)
    monkeypatch.setattr(pipeline_module, "VISUAL_STORY_PLANNER_ENABLED", planner)
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", variation)
    captured = _fake_render(monkeypatch)
    pipeline = AutoPublishPipeline(output_directory="output/test-v16")
    stage = pipeline._render_scenes(plan, _segments(plan))
    return stage, captured


# ---------------------------------------------------------------------------
# 1. Variation OFF preserves existing V1.2--V1.5 behavior
# ---------------------------------------------------------------------------


def test_variation_off_preserves_existing_behavior(monkeypatch) -> None:
    plan = _base_plan()
    stage, jobs = _run_render_scenes(monkeypatch, plan, variation=False)
    assert stage["status"] == "completed"
    assert "background_variation" not in stage
    for job in jobs:
        vd = job.visual_description or {}
        assert vd.get("environment", {}) == {}
        assert "background_variation" not in vd


# ---------------------------------------------------------------------------
# 2. Variation ON fills empty environments
# ---------------------------------------------------------------------------


def test_variation_on_fills_empty_environments(monkeypatch) -> None:
    plan = _base_plan()
    stage, jobs = _run_render_scenes(monkeypatch, plan, variation=True)
    assert stage.get("background_variation") is True
    for job in jobs:
        vd = job.visual_description or {}
        environment = vd.get("environment") or {}
        assert environment.get("type") in SUPPORTED_ENVIRONMENTS
        assert "background_variation" in vd
        assert vd["background_variation"]["filled"] is True


# ---------------------------------------------------------------------------
# 3. Independent of V1.3/V1.4/V1.5
# ---------------------------------------------------------------------------


def test_variation_independent_of_semantic_and_planner(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs = _run_render_scenes(
        monkeypatch, plan, variation=True, semantic=True, planner=True
    )
    for job in jobs:
        vd = job.visual_description or {}
        assert (vd.get("environment") or {}).get("type") in SUPPORTED_ENVIRONMENTS


# ---------------------------------------------------------------------------
# 4. Explicit environment intent never overwritten
# ---------------------------------------------------------------------------


def test_explicit_environment_never_overwritten(monkeypatch) -> None:
    plan = _base_plan(explicit_environment_index=1)
    _, jobs = _run_render_scenes(monkeypatch, plan, variation=True)
    explicit_env = (jobs[1].visual_description or {}).get("environment") or {}
    assert explicit_env == {"type": "study_desk", "ground_y": 0.78}
    decision = (jobs[1].visual_description or {})["background_variation"]
    assert decision["skipped"] is True
    assert "explicit_environment_preserved" in decision["warnings"]
    for other in (jobs[0], jobs[2]):
        other_env = (other.visual_description or {}).get("environment") or {}
        assert other_env.get("type") in SUPPORTED_ENVIRONMENTS


# ---------------------------------------------------------------------------
# 5. Adjacent scenes differ
# ---------------------------------------------------------------------------


def test_adjacent_backdrops_differ(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs = _run_render_scenes(monkeypatch, plan, variation=True)
    types = [(job.visual_description or {})["environment"]["type"] for job in jobs]
    for previous, current in zip(types, types[1:]):
        assert previous != current


# ---------------------------------------------------------------------------
# 6. Deterministic repeated execution
# ---------------------------------------------------------------------------


def test_deterministic_repeated_execution(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs_first = _run_render_scenes(monkeypatch, plan, variation=True)
    _, jobs_second = _run_render_scenes(monkeypatch, plan, variation=True)
    assert [j.to_dict() for j in jobs_first] == [j.to_dict() for j in jobs_second]


# ---------------------------------------------------------------------------
# 7. Plan inputs never mutated; decisions JSON-serializable
# ---------------------------------------------------------------------------


def test_plan_inputs_never_mutated(monkeypatch) -> None:
    plan = _base_plan()
    plan_before = copy.deepcopy(plan)
    _, jobs = _run_render_scenes(monkeypatch, plan, variation=True)
    for scene, before in zip(plan.scenes, plan_before.scenes):
        assert scene.visual.environment == before.visual.environment
        assert scene.visual.characters == before.visual.characters
    for job in jobs:
        decision = (job.visual_description or {}).get("background_variation")
        if decision:
            json.dumps(decision, sort_keys=True)