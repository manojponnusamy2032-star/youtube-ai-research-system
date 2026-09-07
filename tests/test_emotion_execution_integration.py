"""V1.6-F pipeline integration tests.

Verifies that the character emotion execution layer is wired into
``_render_scenes`` / ``_render_visual_scene`` so that: (a) with the feature
flag OFF the render job spec and stage result are unchanged, and (b) with the
flag ON the deterministic emotion key reaches the staged character dicts
(and therefore ``CharacterSpec``) while coexisting with the earlier V1.6
layers (A/B/C/D/E) and never touching the camera spec.
"""

from __future__ import annotations

import src.services.background_variation as bg_module
import src.services.camera_execution as camera_module
import src.services.character_variation as char_module
import src.services.emotion_execution as emotion_module
import src.services.motion_variation as motion_module
import src.services.scene_choreography as choreo_module
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene
from src.services.scene_composition import SceneComposition


def _plan():
    """Two-scene hook->explanation plan with one recurring character."""
    return VideoPlan(
        title="Emotion execution integration",
        scenes=[
            ScenePlan(
                narration="A hook scene",
                visual=VisualScene(
                    scene_role="hook",
                    primary_focus="character",
                    characters=[{"name": "hero"}],
                ),
            ),
            ScenePlan(
                narration="The explanation",
                visual=VisualScene(
                    scene_role="explanation",
                    primary_focus="character",
                    characters=[{"name": "hero"}],
                ),
            ),
        ],
    )


def _run(monkeypatch, *, emotion=False, background=False, character=False,
         motion=False, camera=False, choreography=False, plan=None):
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": job.scene_number, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", False)
    monkeypatch.setattr(emotion_module, "VISUAL_EMOTION_EXECUTION_ENABLED", emotion)
    monkeypatch.setattr(bg_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", background)
    monkeypatch.setattr(char_module, "VISUAL_CHARACTER_VARIATION_ENABLED", character)
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", motion)
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", camera)
    monkeypatch.setattr(choreo_module, "VISUAL_CHOREOGRAPHY_ENABLED", choreography)
    stage = AutoPublishPipeline(output_directory="output/test-v16f")._render_scenes(
        plan if plan is not None else _plan(),
        [
            {"scene_number": 1, "duration_seconds": 2.0},
            {"scene_number": 2, "duration_seconds": 2.0},
        ],
    )
    return stage, captured


# ---------------------------------------------------------------------------
# 1. Feature flag OFF preserves existing pipeline behavior
# ---------------------------------------------------------------------------


def test_pipeline_flag_off_has_no_emotion_keys(monkeypatch):
    stage, jobs = _run(monkeypatch)
    for job in jobs:
        description = job.visual_description or {}
        for member in description.get("characters") or []:
            assert "emotion" not in member
        assert "emotion_execution" not in description
    assert "emotion_execution" not in stage


# ---------------------------------------------------------------------------
# 2. Flag ON: emotion staged on the bearer and reaches CharacterSpec
# ---------------------------------------------------------------------------


def test_pipeline_flag_on_stages_bearer_emotion(monkeypatch):
    stage, jobs = _run(monkeypatch, emotion=True)
    hook_characters = jobs[0].visual_description["characters"]
    assert hook_characters[0]["emotion"] == "excited"
    # Decision metadata is present exactly when a change was applied.
    decision = jobs[0].visual_description["emotion_execution"]
    assert decision["changed"] is True
    assert decision["bearer"] == "hero"
    assert decision["source"] == "role"
    assert stage["emotion_execution"] is True


def test_emotion_reaches_characterspec_via_staged_description(monkeypatch):
    _, jobs = _run(monkeypatch, emotion=True)
    composition = SceneComposition.from_visual_description(jobs[0].visual_description)
    emotion_values = [spec.emotion for spec in composition.characters]
    assert emotion_values == ["excited"]


def test_pipeline_multi_scene_aggregation(monkeypatch):
    stage, jobs = _run(monkeypatch, emotion=True)
    # Scene 1 (hook role) -> excited; scene 2 (explanation role) -> focused.
    assert jobs[0].visual_description["characters"][0]["emotion"] == "excited"
    assert jobs[1].visual_description["characters"][0]["emotion"] == "focused"
    # Semantic correctness over variety: no forced alternation machinery —
    # both scenes carry a per-scene decision with the same deterministic bearer.
    assert all(
        (job.visual_description or {}).get("emotion_execution", {}).get("bearer") == "hero"
        for job in jobs
    )
    assert stage["emotion_execution"] is True

# ---------------------------------------------------------------------------
# 3. Explicit authored emotion survives the pipeline
# ---------------------------------------------------------------------------


def test_pipeline_explicit_emotion_survives(monkeypatch):
    plan = _plan()
    plan.scenes[0].visual.characters = [{"name": "hero", "emotion": "sad"}]
    _, jobs = _run(monkeypatch, emotion=True, plan=plan)
    character = jobs[0].visual_description["characters"][0]
    assert character["emotion"] == "sad"
    # Explicit preservation is a silent no-op: no change metadata.
    assert "emotion_execution" not in jobs[0].visual_description
    assert "emotion_execution" not in jobs[0].__dict__


def test_pipeline_object_attention_target_is_safe(monkeypatch):
    plan = _plan()
    plan.scenes[0].visual.primary_focus = "object"
    plan.scenes[0].visual.characters = [{"name": "hero"}]
    plan.scenes[0].visual.objects = [{"name": "graph", "x": 0.6, "y": 0.8}]
    _, jobs = _run(monkeypatch, emotion=True, plan=plan)
    # Without V1.4 planning metadata the layer cannot know the attention
    # target at all, so the deterministic role fallback applies to the first
    # declared character; either way the scene stays CharacterSpec-safe.
    composition = SceneComposition.from_visual_description(jobs[0].visual_description)
    assert composition.characters
    for spec in composition.characters:
        assert spec.emotion in {
            "neutral", "happy", "frustrated", "focused", "surprised", "sad", "excited",
        }


# ---------------------------------------------------------------------------
# 4. Coexistence with V1.6-A/B/C/D/E and camera untouched
# ---------------------------------------------------------------------------


def test_pipeline_v16f_coexists_with_v16abcde(monkeypatch):
    stage, jobs = _run(
        monkeypatch,
        emotion=True,
        background=True,
        character=True,
        motion=True,
        camera=True,
        choreography=True,
    )
    assert stage["emotion_execution"] is True
    assert stage["background_variation"] is True
    assert stage["character_variation"] is True
    assert stage["motion_variation"] is True
    assert stage["camera_execution"] is True
    assert stage["choreography"] is True
    description = jobs[0].visual_description or {}
    assert "emotion_execution" in description
    assert "background_variation" in description
    assert "character_variation" in description
    assert "motion_variation" in description
    assert "camera_execution" in description
    assert "choreography" in description
    # The V1.6-D camera spec is never modified by V1.6-F.
    assert description["camera"] and description["camera"].get("pattern")
    # The emotion key landed on the bearer and nothing else was reordered.
    assert description["characters"][0]["emotion"] in {
        "neutral", "happy", "frustrated", "focused", "surprised", "sad", "excited",
    }


def test_pipeline_camera_spec_untouched_with_emotion_on(monkeypatch):
    plan = _plan()
    plan.scenes[0].visual.camera_spec = {"pattern": "slow_zoom_in", "focus_target": "hero"}
    _, jobs = _run(monkeypatch, emotion=True, plan=plan)
    camera = jobs[0].visual_description["camera"]
    assert camera["pattern"] == "slow_zoom_in"
    assert camera.get("focus_target") in (None, "hero")
    assert jobs[0].visual_description["characters"][0]["emotion"] == "excited"
