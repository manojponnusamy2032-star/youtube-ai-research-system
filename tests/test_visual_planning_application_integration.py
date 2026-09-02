"""V1.5 visual planning application layer integration tests.

Pipeline-level tests proving that:
- application OFF preserves V1.4-F advisory-only behavior byte-for-byte;
- application ON converts safe V1.4 recommendations into staging inputs;
- V1.4 OFF + application ON behaves exactly like the existing pipeline;
- explicit scene intent is preserved;
- no invented targets ever reach staging;
- the layer is deterministic and never mutates planner inputs.
"""
from __future__ import annotations

import copy
import json

import src.services.visual_planning_application as app_module
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import (
    AutoPublishPipeline,
    ScenePlan,
    VideoPlan,
    VisualScene,
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
        title="V1.5 Integration",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene("problem", "problem_subject"),
            _scene("solution", "solution_subject"),
        ],
    )


def _explicit_plan():
    """Plan whose middle scene carries explicit camera intent."""
    return VideoPlan(
        title="V1.5 Explicit",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene(
                "problem",
                "problem_subject",
                camera_spec={"pattern": "slow_zoom_in", "focus_target": "problem_subject"},
            ),
            _scene("solution", "solution_subject"),
        ],
    )


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


def _enable(monkeypatch, semantic=True, planner=True, application=True):
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", semantic)
    monkeypatch.setattr(pipeline_module, "VISUAL_STORY_PLANNER_ENABLED", planner)
    monkeypatch.setattr(app_module, "VISUAL_PLANNING_APPLICATION_ENABLED", application)


def _run_render_scenes(monkeypatch, plan, semantic=True, planner=True, application=True):
    _enable(monkeypatch, semantic=semantic, planner=planner, application=application)
    captured = _fake_render(monkeypatch)
    pipeline = AutoPublishPipeline(output_directory="output/test-v15")
    stage = pipeline._render_scenes(plan, _segments(plan))
    return stage, captured


def _strip_planning(job_dict):
    """Remove the additive V1.4/V1.5 metadata so enabled/disabled jobs compare."""
    stripped = dict(job_dict)
    description = dict(stripped.get("visual_description") or {})
    description.pop("visual_planning", None)
    description.pop("visual_planning_application", None)
    stripped["visual_description"] = description
    return stripped


def _scene_element_names(job):
    vd = job.visual_description or {}
    chars = {c.get("name") for c in vd.get("characters", []) if isinstance(c, dict)}
    objs = {o.get("name") for o in vd.get("objects", []) if isinstance(o, dict)}
    return chars | objs


# ---------------------------------------------------------------------------
# 1. Application OFF == V1.4-F advisory-only (byte-equivalent jobs)
# ---------------------------------------------------------------------------


def test_application_off_matches_v14_advisory_only(monkeypatch) -> None:
    plan = _base_plan()
    # V1.4-F baseline: planner ON, application OFF.
    stage_base, jobs_base = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=False
    )
    # Application OFF again -> identical jobs (deterministic, no-op layer).
    stage_off, jobs_off = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=False
    )
    assert stage_base.get("visual_planning") is True
    assert "visual_planning_application" not in stage_base
    assert [j.to_dict() for j in jobs_base] == [j.to_dict() for j in jobs_off]
    for job in jobs_base:
        vd = job.visual_description or {}
        assert "visual_planning" in vd
        assert "visual_planning_application" not in vd


# ---------------------------------------------------------------------------
# 2. Application ON actually changes staging inputs
# ---------------------------------------------------------------------------


def test_application_on_changes_staging_inputs(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs_base = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=False
    )
    stage_app, jobs_app = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=True
    )
    assert stage_app.get("visual_planning_application") is True
    # At least one scene's staged camera differs from the advisory-only run.
    diffs = [
        i
        for i, (jb, ja) in enumerate(zip(jobs_base, jobs_app))
        if (jb.visual_description or {}).get("camera")
        != (ja.visual_description or {}).get("camera")
    ]
    assert diffs, "application ON should modify at least one staged camera"
    for i in diffs:
        decision = (jobs_app[i].visual_description or {}).get("visual_planning_application") or {}
        assert decision.get("camera_changed") is True


# ---------------------------------------------------------------------------
# 3. V1.4 OFF + application ON behaves exactly like the existing pipeline
# ---------------------------------------------------------------------------


def test_v14_off_application_on_is_existing_pipeline(monkeypatch) -> None:
    plan = _base_plan()
    stage_off, jobs_off = _run_render_scenes(
        monkeypatch, plan, semantic=False, planner=False, application=True
    )
    stage_plain, jobs_plain = _run_render_scenes(
        monkeypatch, plan, semantic=False, planner=False, application=False
    )
    assert "visual_planning" not in stage_off
    assert "visual_planning_application" not in stage_off
    assert [j.to_dict() for j in jobs_off] == [j.to_dict() for j in jobs_plain]
    for job in jobs_off:
        vd = job.visual_description or {}
        assert "visual_planning" not in vd
        assert "visual_planning_application" not in vd


# ---------------------------------------------------------------------------
# 4. Explicit camera intent preserved when application ON
# ---------------------------------------------------------------------------


def test_explicit_camera_intent_preserved(monkeypatch) -> None:
    plan = _explicit_plan()
    _, jobs_base = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=False
    )
    _, jobs_app = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=True
    )
    # Scene 2 (index 1) has explicit camera_spec slow_zoom_in.
    base_cam = (jobs_base[1].visual_description or {}).get("camera") or {}
    app_cam = (jobs_app[1].visual_description or {}).get("camera") or {}
    assert base_cam.get("pattern") == "slow_zoom_in"
    assert app_cam.get("pattern") == "slow_zoom_in"
    assert app_cam == base_cam
    decision = (jobs_app[1].visual_description or {}).get("visual_planning_application") or {}
    assert decision.get("camera_changed") is False
    assert any("explicit camera preserved" in w for w in decision.get("warnings", []))


# ---------------------------------------------------------------------------
# 5. No invented targets reach staging
# ---------------------------------------------------------------------------


def test_no_invented_targets(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=True
    )
    for job in jobs:
        vd = job.visual_description or {}
        camera = vd.get("camera") or {}
        focus = camera.get("focus_target")
        if focus:
            assert focus in _scene_element_names(job), f"invented target: {focus}"


# ---------------------------------------------------------------------------
# 6. Deterministic repeated execution
# ---------------------------------------------------------------------------


def test_deterministic_repeated_execution(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs_first = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=True
    )
    _, jobs_second = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=True
    )
    assert [j.to_dict() for j in jobs_first] == [j.to_dict() for j in jobs_second]


# ---------------------------------------------------------------------------
# 7. Planner inputs never mutated
# ---------------------------------------------------------------------------


def test_planner_inputs_never_mutated(monkeypatch) -> None:
    plan = _base_plan()
    plan_before = copy.deepcopy(plan)
    _, jobs = _run_render_scenes(
        monkeypatch, plan, semantic=True, planner=True, application=True
    )
    assert plan.scenes[0].visual.camera_spec == plan_before.scenes[0].visual.camera_spec
    assert plan.scenes[0].visual.characters == plan_before.scenes[0].visual.characters
    # Applied decisions are JSON-serializable.
    for job in jobs:
        decision = (job.visual_description or {}).get("visual_planning_application")
        if decision:
            json.dumps(decision, sort_keys=True)
