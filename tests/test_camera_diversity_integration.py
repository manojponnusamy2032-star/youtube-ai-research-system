"""V1.6-G pipeline integration tests."""

from __future__ import annotations

import src.services.background_variation as bg_module
import src.services.camera_diversity as camera_div_module
import src.services.camera_execution as camera_module
import src.services.character_variation as char_module
import src.services.emotion_execution as emotion_module
import src.services.motion_variation as motion_module
import src.services.scene_choreography as choreo_module
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene


def _plan():
    roles = ["hook", "problem", "contrast", "explanation", "example", "solution", "cta"]
    scenes = []
    for role in roles:
        scenes.append(
            ScenePlan(
                narration=f"{role} narration",
                visual=VisualScene(
                    scene_role=role,
                    primary_focus="character",
                    characters=[{"name": "protagonist"}],
                ),
            )
        )
    return VideoPlan(title="Camera diversity integration", scenes=scenes)


def _run(monkeypatch, *, diversity=False, camera=False, choreography=False,
         background=False, character=False, motion=False, emotion=False, plan=None):
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": job.scene_number, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", False)
    monkeypatch.setattr(camera_div_module, "VISUAL_CAMERA_DIVERSITY_ENABLED", diversity)
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", camera)
    monkeypatch.setattr(choreo_module, "VISUAL_CHOREOGRAPHY_ENABLED", choreography)
    monkeypatch.setattr(bg_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", background)
    monkeypatch.setattr(char_module, "VISUAL_CHARACTER_VARIATION_ENABLED", character)
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", motion)
    monkeypatch.setattr(emotion_module, "VISUAL_EMOTION_EXECUTION_ENABLED", emotion)
    stage = AutoPublishPipeline(output_directory="output/test-v16g")._render_scenes(
        plan if plan is not None else _plan(),
        [{"scene_number": i + 1, "duration_seconds": 2.0} for i in range(7)],
    )
    return stage, captured


def test_pipeline_flag_off_has_no_camera_diversity(monkeypatch):
    stage, jobs = _run(monkeypatch)
    for job in jobs:
        description = job.visual_description or {}
        assert "camera_diversity" not in description
    assert "camera_diversity" not in stage


def test_pipeline_g4_sanitizes_placeholder_focus(monkeypatch):
    plan = _plan()
    plan.scenes[6].visual.text_elements = [{"text": "KEEP GOING", "size": "headline", "y": 0.12}]
    stage, jobs = _run(monkeypatch, diversity=True, camera=True, plan=plan)
    cta_camera = (jobs[6].visual_description or {}).get("camera", {})
    focus = str(cta_camera.get("focus_target") or "").strip().lower()
    # G4 clears a placeholder focus_target to empty so choreography never
    # invents a fake character target.
    assert focus == ""
    assert stage["camera_diversity"] is True


def test_pipeline_g1_diversity_metadata_present(monkeypatch):
    stage, jobs = _run(monkeypatch, diversity=True, camera=True)
    description = jobs[0].visual_description or {}
    assert "camera_diversity" in description
    assert stage["camera_diversity"] is True
    payload = description["camera_diversity"]
    assert "pattern" in payload
    assert "changed" in payload
    assert "reason" in payload


def test_pipeline_v16g_coexists_with_v16abcdef(monkeypatch):
    stage, jobs = _run(
        monkeypatch,
        diversity=True,
        camera=True,
        choreography=True,
        background=True,
        character=True,
        motion=True,
        emotion=True,
    )
    assert stage["camera_diversity"] is True
    assert stage["camera_execution"] is True
    assert stage["choreography"] is True
    assert stage["emotion_execution"] is True
    description = jobs[0].visual_description or {}
    assert "camera_diversity" in description
    assert "camera_execution" in description
    assert "choreography" in description


def test_sanitize_planning_camera_focus_placeholder():
    meta = {
        "camera": {"recommended_pattern": "focus_on_character", "focus_target": "character"},
        "attention": {"primary_target": "hero", "target_kind": "character"},
    }
    result = AutoPublishPipeline._sanitize_planning_camera_focus(meta)
    assert result["camera"]["focus_target"] == ""
    assert result["attention"]["primary_target"] == "hero"


def test_sanitize_planning_camera_focus_real_target_preserved():
    meta = {"camera": {"recommended_pattern": "focus_on_character", "focus_target": "hero"}}
    result = AutoPublishPipeline._sanitize_planning_camera_focus(meta)
    assert result["camera"]["focus_target"] == "hero"


def test_sanitize_planning_camera_focus_non_dict():
    assert AutoPublishPipeline._sanitize_planning_camera_focus(None) is None
    assert AutoPublishPipeline._sanitize_planning_camera_focus({}) == {}