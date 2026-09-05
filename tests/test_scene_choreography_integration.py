"""V1.6-E pipeline integration tests.

Verifies that the scene choreography layer is wired into ``_render_scenes`` /
``_render_visual_scene`` so that: (a) with the feature flag OFF the render job
spec and stage result are unchanged, and (b) with the flag ON deterministic
cast-delta entrances, non-cut exits, and append-only observability metadata
reach the RenderJobSpec while coexisting with the earlier V1.6 layers
(A/B/C/D).
"""

from __future__ import annotations

import src.services.background_variation as bg_module
import src.services.camera_execution as camera_module
import src.services.character_variation as char_module
import src.services.motion_variation as motion_module
import src.services.scene_choreography as choreo_module
from src.models.content_package import Motion, Transition
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene


def _plan():
    """Two-scene plan: scene 2 introduces a second character."""
    return VideoPlan(
        title="Choreography integration",
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
                    characters=[{"name": "hero"}, {"name": "new"}],
                ),
            ),
        ],
    )


def _run(monkeypatch, *, choreography=False, background=False, character=False,
         motion=False, camera=False, plan=None):
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {"status": "completed", "scene_number": job.scene_number, "output_reference": "scene.mp4"}

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", False)
    monkeypatch.setattr(choreo_module, "VISUAL_CHOREOGRAPHY_ENABLED", choreography)
    monkeypatch.setattr(bg_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", background)
    monkeypatch.setattr(char_module, "VISUAL_CHARACTER_VARIATION_ENABLED", character)
    monkeypatch.setattr(motion_module, "VISUAL_MOTION_VARIATION_ENABLED", motion)
    monkeypatch.setattr(camera_module, "VISUAL_CAMERA_EXECUTION_ENABLED", camera)
    stage = AutoPublishPipeline(output_directory="output/test-v16e")._render_scenes(
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


def test_pipeline_flag_off_has_no_choreography(monkeypatch):
    stage, jobs = _run(monkeypatch)
    for job in jobs:
        description = job.visual_description or {}
        assert "choreography" not in description
        assert not [m for m in job.motions if m.label.startswith("v1.6-e:")]
    assert "choreography" not in stage


# ---------------------------------------------------------------------------
# 2. Flag ON: deterministic cast-delta entrances via threaded continuity
# ---------------------------------------------------------------------------


def test_pipeline_flag_on_enters_for_introduced_characters(monkeypatch):
    stage, jobs = _run(monkeypatch, choreography=True)
    # Scene 1 is a deliberate cold open: hero enters.
    scene1_enters = [m for m in jobs[0].motions if m.label == "v1.6-e:enter"]
    assert [m.target_id for m in scene1_enters] == ["hero"]
    # Scene 2 threads scene 1's cast: only the genuinely new character enters.
    scene2_enters = [m for m in jobs[1].motions if m.label == "v1.6-e:enter"]
    assert [m.target_id for m in scene2_enters] == ["new"]
    # Existing motions were not reordered: appended entries come last.
    assert jobs[1].motions[-1].label == "v1.6-e:enter"
    # Observability metadata: description, record, and stage.
    description = jobs[0].visual_description or {}
    assert description["choreography"]["changed"] is True
    assert description["choreography"]["scene_index"] == 0
    assert stage["choreography"] is True


def test_pipeline_departure_exit_on_non_cut_transition(monkeypatch):
    plan = _plan()
    plan.scenes[0].visual.characters = [{"name": "hero"}, {"name": "guest"}]
    plan.scenes[0].visual.transition = Transition(type="crossfade", duration=0.5)
    _, jobs = _run(monkeypatch, choreography=True, plan=plan)
    exits = [m for m in jobs[0].motions if m.label == "v1.6-e:exit"]
    assert [m.target_id for m in exits] == ["guest"]
    assert exits[0].type == "exit"


def test_pipeline_no_exit_on_cut_transition(monkeypatch):
    plan = _plan()
    plan.scenes[0].visual.characters = [{"name": "hero"}, {"name": "guest"}]
    plan.scenes[0].visual.transition = Transition(type="cut", duration=0.0)
    _, jobs = _run(monkeypatch, choreography=True, plan=plan)
    assert not [m for m in jobs[0].motions if m.label == "v1.6-e:exit"]


# ---------------------------------------------------------------------------
# 3. Explicit motions remain authoritative (conflict guard + preservation)
# ---------------------------------------------------------------------------


def test_pipeline_explicit_motion_blocks_enter_and_is_preserved(monkeypatch):
    plan = _plan()
    explicit = Motion(
        type="move",
        target="character",
        target_id="new",
        start_time=0.0,
        duration=1.0,
        easing="ease_in_out",
        parameters={"from": {"x": 0.2, "y": 0.75}, "to": {"x": 0.6, "y": 0.75}},
        label="authored",
    )
    plan.scenes[1].visual.motions = [explicit]
    _, jobs = _run(monkeypatch, choreography=True, plan=plan)
    scene2 = jobs[1].motions
    # The lead-in window is occupied by the authored move: no enter appended.
    assert not [m for m in scene2 if m.label == "v1.6-e:enter"]
    # The explicit motion is preserved verbatim, first in list order.
    assert scene2[0] is explicit
    assert scene2[0].start_time == 0.0 and scene2[0].duration == 1.0


# ---------------------------------------------------------------------------
# 4. Coexistence with V1.6-A/B/C/D
# ---------------------------------------------------------------------------


def test_pipeline_v16e_coexists_with_v16abcd(monkeypatch):
    stage, jobs = _run(
        monkeypatch,
        choreography=True,
        background=True,
        character=True,
        motion=True,
        camera=True,
    )
    assert stage["choreography"] is True
    assert stage["background_variation"] is True
    assert stage["character_variation"] is True
    assert stage["motion_variation"] is True
    assert stage["camera_execution"] is True
    description = jobs[0].visual_description or {}
    for key in ("choreography", "background_variation", "character_variation",
                "motion_variation", "camera_execution"):
        assert key in description
    # The V1.6-D camera spec is preserved verbatim by V1.6-E.
    camera_spec = description["camera"]
    assert camera_spec and camera_spec.get("pattern")


def test_pipeline_choreography_metadata_shape(monkeypatch):
    _, jobs = _run(monkeypatch, choreography=True)
    payload = jobs[1].visual_description["choreography"]
    assert payload["scene_index"] == 1
    assert payload["introduced"] == ["character:new"]
    assert payload["actions"][0]["kind"] == "enter"
    assert payload["actions"][0]["motion_type"] == "enter"
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["reason"], str)