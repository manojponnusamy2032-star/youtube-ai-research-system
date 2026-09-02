"""V1.6-B character variation pipeline integration tests.

Pipeline-level tests proving that:
- variation OFF preserves existing V1.2--V1.6-A behavior exactly;
- variation ON varies only default-authored character intent fields;
- explicit character intent survives the full staging path;
- V1.4 focus decisions are respected (never contradicted);
- V1.6-A background variation and V1.6-B coexist;
- the layer is deterministic and never mutates plan inputs.
"""
from __future__ import annotations

import copy
import json

import src.services.background_variation as bgv_module
import src.services.character_variation as char_var_module
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import (
    AutoPublishPipeline,
    ScenePlan,
    VideoPlan,
    VisualScene,
)
from src.services.character_variation import (
    PRIMARY_SCALE,
    SUPPORTING_SCALE,
)
from src.services.scene_composition import SUPPORTED_ENVIRONMENTS


def _scene(role, name, characters=None):
    return ScenePlan(
        narration=f"{role} evidence about memory",
        visual=VisualScene(
            scene_role=role,
            characters=list(characters if characters is not None else [{"name": name, "x": 0.35, "y": 0.75}]),
            objects=[{"name": f"{name}_object", "type": "brain", "x": 0.72, "y": 0.7}],
            text_elements=[{"text": role.title(), "size": "headline", "x": 0.5, "y": 0.12}],
        ),
    )


def _base_plan():
    """Plan where characters omit pose/scale (real-plan convention)."""
    return VideoPlan(
        title="V1.6-B Integration",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene(
                "solution",
                "solution_subject",
                characters=[
                    {"name": "guide", "x": 0.3, "y": 0.75},
                    {"name": "friend", "x": 0.7, "y": 0.78},
                ],
            ),
            _scene("cta", "cta_subject"),
        ],
    )


def _explicit_plan():
    """Plan whose middle scene carries explicit pose, scale, and position."""
    return VideoPlan(
        title="V1.6-B Explicit",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene(
                "solution",
                "solution_subject",
                characters=[
                    {"name": "guide", "pose": "idle", "scale": 1.3, "x": 0.25, "y": 0.76},
                ],
            ),
            _scene("cta", "cta_subject"),
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


def _run_render_scenes(monkeypatch, plan, variation=False, background=False, semantic=False, planner=False):
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", semantic)
    monkeypatch.setattr(pipeline_module, "VISUAL_STORY_PLANNER_ENABLED", planner)
    monkeypatch.setattr(bgv_module, "VISUAL_BACKGROUND_VARIATION_ENABLED", background)
    monkeypatch.setattr(char_var_module, "VISUAL_CHARACTER_VARIATION_ENABLED", variation)
    captured = _fake_render(monkeypatch)
    pipeline = AutoPublishPipeline(output_directory="output/test-v16b")
    stage = pipeline._render_scenes(plan, _segments(plan))
    return stage, captured


# ---------------------------------------------------------------------------
# 1. Variation OFF preserves existing behavior
# ---------------------------------------------------------------------------


def test_variation_off_preserves_existing_behavior(monkeypatch) -> None:
    plan = _base_plan()
    stage, jobs = _run_render_scenes(monkeypatch, plan, variation=False)
    assert stage["status"] == "completed"
    assert "character_variation" not in stage
    for job in jobs:
        vd = job.visual_description or {}
        # Staging never introduces poses; V1.6-B OFF must not either.
        for character in vd.get("characters") or []:
            assert "pose" not in character
        assert "character_variation" not in vd


# ---------------------------------------------------------------------------
# 2. Variation ON varies default-authored characters
# ---------------------------------------------------------------------------


def test_variation_on_varies_default_characters(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs_off = _run_render_scenes(monkeypatch, plan, variation=False)
    stage, jobs = _run_render_scenes(monkeypatch, plan, variation=True)
    assert stage.get("character_variation") is True
    # Hook scene: role pose assigned where OFF had none.
    off_hook = ((jobs_off[0].visual_description or {}).get("characters") or [{}])[0]
    hook_chars = (jobs[0].visual_description or {}).get("characters") or []
    assert off_hook.get("pose") is None
    assert hook_chars and hook_chars[0].get("pose") == "surprised"
    # Multi-character scene: primary/supporting scales after V1.2 staging
    # (staging multiplies staged scale by 1.25; V1.6-B assigned 1.1/0.85).
    solution_chars = (jobs[1].visual_description or {}).get("characters") or []
    scales = {c["name"]: c.get("scale") for c in solution_chars}
    assert set(scales.values()) == {
        PRIMARY_SCALE * 1.25,
        SUPPORTING_SCALE * 1.25,
    }
    for job in jobs:
        decision = (job.visual_description or {}).get("character_variation")
        assert decision is not None
        assert decision["changed"] is True


# ---------------------------------------------------------------------------
# 3. Explicit character intent preserved through the pipeline
# ---------------------------------------------------------------------------


def test_explicit_character_intent_preserved(monkeypatch) -> None:
    plan = _explicit_plan()
    _, jobs_off = _run_render_scenes(monkeypatch, plan, variation=False)
    _, jobs_on = _run_render_scenes(monkeypatch, plan, variation=True)
    # Staged characters must be identical with variation ON vs OFF: the
    # explicit pose/scale/x flow through untouched (V1.2 staging applies its
    # usual transforms in both runs).
    off_chars = (jobs_off[1].visual_description or {}).get("characters") or []
    on_chars = (jobs_on[1].visual_description or {}).get("characters") or []
    assert on_chars == off_chars
    assert on_chars[0]["pose"] == "idle"
    assert on_chars[0]["scale"] == 1.3 * 1.25
    assert on_chars[0]["x"] == 0.25
    decision = (jobs_on[1].visual_description or {})["character_variation"]
    assert decision["changed"] is False
    assert decision["pose_variations"] == ()
    assert decision["scale_variations"] == ()
    assert decision["position_variations"] == ()


# ---------------------------------------------------------------------------
# 4. V1.4 focus decisions respected
# ---------------------------------------------------------------------------


def test_focus_character_respected_with_planning(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs = _run_render_scenes(
        monkeypatch, plan, variation=True, semantic=True, planner=True
    )
    for job in jobs:
        vd = job.visual_description or {}
        decision = vd.get("character_variation")
        if not decision:
            continue
        planning_meta = vd.get("visual_planning") or {}
        attention = planning_meta.get("attention") or {}
        primary = (attention.get("primary_target") or "").strip().lower()
        if primary and decision.get("focus_character"):
            assert decision["focus_character"] == primary
            # When V1.6-B assigned the focus character's scale (multi-character
            # scene), it must be the primary scale (V1.2 staging then x1.25).
            if primary in decision.get("scale_variations", ()):
                staged = {c["name"]: c for c in vd.get("characters") or []}
                assert staged[primary]["scale"] == PRIMARY_SCALE * 1.25
        # Focus never contradicted: variation only added absent keys.
        # Exclude keys that V1.2 presentation staging intentionally modifies
        # (scale *1.25, x clamp, y offset) -- those are not V1.6-B changes.
        V12_STAGED_KEYS = {"scale", "x", "y"}
        for original, staged in zip(
            _scene_characters(plan, job.scene_number), vd.get("characters") or []
        ):
            for key in original:
                if key in V12_STAGED_KEYS:
                    continue
                assert staged.get(key) == original[key], (
                    f"V1.6-B modified explicit '{key}': "
                    f"{original[key]} -> {staged.get(key)}"
                )


def _scene_characters(plan, scene_number):
    return plan.scenes[scene_number - 1].visual.characters


# ---------------------------------------------------------------------------
# 5. V1.6-A compatibility
# ---------------------------------------------------------------------------


def test_v16a_and_v16b_coexist(monkeypatch) -> None:
    plan = _base_plan()
    stage, jobs = _run_render_scenes(
        monkeypatch, plan, variation=True, background=True
    )
    assert stage.get("background_variation") is True
    assert stage.get("character_variation") is True
    for job in jobs:
        vd = job.visual_description or {}
        assert (vd.get("environment") or {}).get("type") in SUPPORTED_ENVIRONMENTS
        decision = vd.get("character_variation")
        if decision is not None:
            assert decision["changed"] is True


def test_background_variation_unaffected_when_character_variation_off(monkeypatch) -> None:
    plan = _base_plan()
    stage, jobs = _run_render_scenes(
        monkeypatch, plan, variation=False, background=True
    )
    assert stage.get("background_variation") is True
    assert "character_variation" not in stage
    for job in jobs:
        vd = job.visual_description or {}
        assert (vd.get("environment") or {}).get("type") in SUPPORTED_ENVIRONMENTS
        for character in vd.get("characters") or []:
            assert "pose" not in character


# ---------------------------------------------------------------------------
# 6. Immutability + determinism
# ---------------------------------------------------------------------------


def test_plan_inputs_never_mutated(monkeypatch) -> None:
    plan = _base_plan()
    plan_before = copy.deepcopy(plan)
    _, jobs = _run_render_scenes(
        monkeypatch, plan, variation=True, background=True
    )
    for scene, before in zip(plan.scenes, plan_before.scenes):
        assert scene.visual.characters == before.visual.characters
        assert scene.visual.objects == before.visual.objects
        assert scene.visual.environment == before.visual.environment
    for job in jobs:
        decision = (job.visual_description or {}).get("character_variation")
        if decision:
            json.dumps(decision, sort_keys=True)


def test_deterministic_repeated_execution(monkeypatch) -> None:
    plan = _base_plan()
    _, jobs_first = _run_render_scenes(
        monkeypatch, plan, variation=True, background=True
    )
    _, jobs_second = _run_render_scenes(
        monkeypatch, plan, variation=True, background=True
    )
    assert [j.to_dict() for j in jobs_first] == [j.to_dict() for j in jobs_second]