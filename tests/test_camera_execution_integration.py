"""V1.6-D pipeline integration tests.

Verifies that the camera execution layer is wired into ``_render_scenes`` so
that: (a) with the feature flag OFF the render job spec and stage result are
unchanged, and (b) with the feature flag ON valid camera decisions reach the
renderer as an executable ``camera`` spec plus observability metadata, while
coexisting with the earlier V1.6 layers (A/B/C).
"""

from __future__ import annotations

import src.services.background_variation as bg_module
import src.services.camera_execution as camera_module
import src.services.character_variation as char_module
import src.services.motion_variation as motion_module
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene


def _plan():
    return VideoPlan(
        title="Camera execution integration",
        scenes=[
            ScenePlan(
                narration="A hook scene",
                visual=VisualScene(
                    scene_role="hook",
                    primary_focus="character",
                    characters=[{"name": "student"}],
                    objects=[{"name": "desk", "type": "desk", "x": 0.6, "y": 0.8}],
                    text_elements=[{"text": "HOOK", "size": "headline", "y": 0.12}],
                ),
            ),
            ScenePlan(
                narration="The explanation",
                visual=VisualScene(
                    scene_role="explanation",
                    primary_focus="object",
                    characters=[{"name": "student"}],
                    objects=[{"name": "graph", "type": "graph", "x": 0.6, "y": 0.8}],
                    text_elements=[{"text": "FACTS", "size": "headline", "y": 0.12}],
                ),
            ),
        ],
    )


def _run(monkeypatch, *, camera=False, background=False, character=False, motion=False):
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": job.scene_number, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", False)
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", camera)
    monkeypatch.setattr(bg_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", background)
    monkeypatch.setattr(char_module, "VISUAL_CHARACTER_VARIATION_ENABLED", character)
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", motion)
    stage = AutoPublishPipeline(output_directory="output/test-v16d")._render_scenes(
        _plan(),
        [
            {"scene_number": 1, "duration_seconds": 2.0},
            {"scene_number": 2, "duration_seconds": 2.0},
        ],
    )
    return stage, captured


# ---------------------------------------------------------------------------
# 1. Feature flag OFF preserves existing pipeline behavior
# ---------------------------------------------------------------------------


def test_pipeline_flag_off_has_no_camera_execution(monkeypatch):
    stage, jobs = _run(monkeypatch)
    description = jobs[0].visual_description or {}
    assert "camera_execution" not in description
    assert "camera_execution" not in stage
    # No declared camera pattern was injected (renderer keeps its default).
    assert description.get("camera") in (None, {})


def test_pipeline_flag_off_vs_on_pattern_preserved(monkeypatch):
    plan = _plan()
    plan.scenes[0].visual.camera_spec = {"pattern": "pan_left", "focus_target": "student"}
    plan.scenes[1].visual.camera_spec = {"pattern": "static"}
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": job.scene_number, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", False)
    pipeline = AutoPublishPipeline(output_directory="output/test-v16d")
    pipeline._render_scenes(
        plan,
        [
            {"scene_number": 1, "duration_seconds": 2.0},
            {"scene_number": 2, "duration_seconds": 2.0},
        ],
    )
    assert captured[0].visual_description["camera"]["pattern"] == "pan_left"
    assert captured[1].visual_description["camera"]["pattern"] == "static"


# ---------------------------------------------------------------------------
# 2. Flag ON executes valid camera decisions through the pipeline
# ---------------------------------------------------------------------------


def test_pipeline_flag_on_executes_camera_decision(monkeypatch):
    stage, jobs = _run(monkeypatch, camera=True)
    description = jobs[0].visual_description or {}
    assert "camera" in description
    assert description["camera"]["pattern"] in {"slow_zoom_in", "static"}
    assert "camera_execution" in description
    assert stage["camera_execution"] is True
    executed = description["camera_execution"]
    assert executed["changed"] is True
    assert executed["pattern"] == description["camera"]["pattern"]


def test_pipeline_v16d_coexists_with_v16abc(monkeypatch):
    stage, jobs = _run(
        monkeypatch, camera=True, background=True, character=True, motion=True
    )
    description = jobs[0].visual_description or {}
    assert stage["camera_execution"] is True
    assert stage["background_variation"] is True
    assert stage["character_variation"] is True
    assert stage["motion_variation"] is True
    assert description["background_variation"]["filled"] is True
    assert description["character_variation"]["changed"] is True
    assert description["motion_variation"]["changed"] is True
    assert "camera" in description
    assert description["camera"]["pattern"] in {
        "static",
        "slow_zoom_in",
        "slow_zoom_out",
        "pan_left",
        "pan_right",
        "focus_on_character",
    }


def test_pipeline_explicit_camera_spec_preserved_when_on(monkeypatch):
    plan = _plan()
    plan.scenes[0].visual.camera_spec = {"pattern": "slow_zoom_in", "focus_target": "student"}
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": job.scene_number, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", True)
    pipeline = AutoPublishPipeline(output_directory="output/test-v16d")
    pipeline._render_scenes(
        plan,
        [
            {"scene_number": 1, "duration_seconds": 2.0},
            {"scene_number": 2, "duration_seconds": 2.0},
        ],
    )
    cam = captured[0].visual_description["camera"]
    assert cam["pattern"] == "slow_zoom_in"
    assert cam.get("focus_target") in (None, "student")
