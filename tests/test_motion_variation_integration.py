from __future__ import annotations

import src.services.background_variation as bg_module
import src.services.character_variation as char_module
import src.services.motion_variation as motion_module
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene


def _plan():
    return VideoPlan(
        title="Motion variation",
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
            )
        ],
    )


def _run(monkeypatch, *, motion=False, background=False, character=False):
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": job.scene_number, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", False)
    monkeypatch.setattr(bg_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", background)
    monkeypatch.setattr(char_module, "VISUAL_CHARACTER_VARIATION_ENABLED", character)
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", motion)
    stage = AutoPublishPipeline(output_directory="output/test-v16c")._render_scenes(
        _plan(), [{"scene_number": 1, "duration_seconds": 1.0}]
    )
    return stage, captured[0]


def test_pipeline_flag_off_has_no_motion_metadata(monkeypatch):
    stage, job = _run(monkeypatch)
    assert "motion_variation" not in (job.visual_description or {})
    assert "motion_variation" not in stage


def test_pipeline_v16c_coexists_with_v16a_and_v16b(monkeypatch):
    stage, job = _run(monkeypatch, motion=True, background=True, character=True)
    description = job.visual_description or {}
    assert stage["background_variation"] is True
    assert stage["character_variation"] is True
    assert stage["motion_variation"] is True
    assert description["background_variation"]["changed"] is True
    assert description["character_variation"]["changed"] is True
    assert description["motion_variation"]["changed"] is True
    assert job.motions[-1].label.startswith("v1.6-c:")


def test_pipeline_preserves_explicit_scene_motion(monkeypatch):
    plan = _plan()
    from src.models.content_package import Motion
    plan.scenes[0].visual.motions = [
        Motion(type="scale", target="character", target_id="student", start_time=0, duration=0.5, parameters={"from": 1, "to": 1.3})
    ]
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": 1, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", True)
    pipeline = AutoPublishPipeline(output_directory="output/test-v16c")
    pipeline._render_scenes(plan, [{"scene_number": 1, "duration_seconds": 1.0}])
    assert len(captured[0].motions) == 1
    assert captured[0].motions[0].type == "scale"
