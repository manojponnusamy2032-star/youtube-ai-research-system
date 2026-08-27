"""Tests for the Visual Quality v1 composition layer and renderer upgrades.

Unit tests (no FFmpeg): composition models, motion-state integration,
camera patterns, effects, text, named-character routing.
Integration tests (FFmpeg-marked): VisualScene -> scene MP4 end to end.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.models.content_package import Motion, RenderConfig, RenderJobSpec, Transition
from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, ScenePlan, VideoPlan, VisualScene
from src.services.scene_composition import (
    SAFE_MARGIN_RATIO,
    CameraSpec,
    CharacterSpec,
    EffectSpec,
    EnvironmentSpec,
    ObjectSpec,
    SceneComposition,
    TextSpec,
    resolve_text_placement,
)
from src.services.stickman_renderer import StickmanRenderer, render_stickman_job


W, H = 540, 960


def _ffmpeg_available() -> bool:
    from src.services.ffmpeg_renderer import FFmpegRenderer
    return FFmpegRenderer().is_available()


def _renderer() -> StickmanRenderer:
    return StickmanRenderer(execute_enabled=False)


# ---------------------------------------------------------------------------
# Composition models
# ---------------------------------------------------------------------------


class TestCompositionModels:
    def test_character_spec_normalizes_pose_and_emotion(self) -> None:
        spec = CharacterSpec(name="  student ", pose="TALK", emotion="FOCUSED")
        assert spec.name == "student"
        assert spec.pose == "talk"
        assert spec.emotion == "focused"

    def test_character_spec_clamps_coordinates(self) -> None:
        spec = CharacterSpec(x=1.7, y=-0.4, scale=99)
        assert spec.x == 1.0
        assert spec.y == 0.0
        assert spec.scale == 3.0

    def test_emotion_tints_change_effective_color(self) -> None:
        neutral = CharacterSpec(emotion="neutral")
        frustrated = CharacterSpec(emotion="frustrated")
        happy = CharacterSpec(emotion="happy")
        assert frustrated.effective_color != neutral.effective_color
        assert happy.effective_color != frustrated.effective_color

    def test_object_spec_defaults(self) -> None:
        obj = ObjectSpec(type="clock", x=0.8, y=0.2)
        assert obj.visible is True
        assert obj.opacity == 1.0
        assert obj.name == "object"

    def test_environment_spec_unknown_type_falls_back(self) -> None:
        env = EnvironmentSpec(type="holodeck")
        assert env.type == "default"

    def test_text_spec_size_factor_ordering(self) -> None:
        small = TextSpec(text="a", size="small")
        headline = TextSpec(text="a", size="headline")
        assert headline.scale_factor > small.scale_factor

    def test_text_opacity_fade_in_out(self) -> None:
        spec = TextSpec(text="hi", fade_in=1.0, fade_out=1.0, appear_at=0.5)
        assert spec.effective_opacity(0.0, 10) == 0.0
        assert 0.0 < spec.effective_opacity(0.9, 10) < 1.0
        assert spec.effective_opacity(5.0, 10) == pytest.approx(spec.opacity)
        late = spec.effective_opacity(9.75, 10)
        assert 0.0 < late < 1.0

    def test_effect_active_window(self) -> None:
        fx = EffectSpec(type="highlight", target="clock", start=1.0, duration=1.0)
        assert not fx.is_active(0.5)
        assert fx.is_active(1.5)
        assert not fx.is_active(2.5)
        assert fx.progress(1.0) == pytest.approx(0.0)
        assert fx.progress(2.0) == pytest.approx(1.0)

    def test_camera_pattern_validation(self) -> None:
        cam = CameraSpec(pattern="warp_speed")
        assert cam.pattern == "static"

    def test_scene_composition_round_trip(self) -> None:
        comp = SceneComposition(
            environment=EnvironmentSpec(type="study_desk"),
            characters=[CharacterSpec(name="student", pose="talk")],
            objects=[ObjectSpec(name="clock", type="clock")],
            text_elements=[TextSpec(text="hello", size="large")],
            effects=[EffectSpec(type="highlight", target="clock")],
            camera=CameraSpec(pattern="slow_zoom_in"),
        )
        back = SceneComposition.from_visual_description(comp.to_dict())
        assert back.environment is not None and back.environment.type == "study_desk"
        assert back.characters[0].name == "student"
        assert back.objects[0].type == "clock"
        assert back.text_elements[0].text == "hello"
        assert back.effects[0].target == "clock"
        assert back.camera is not None and back.camera.pattern == "slow_zoom_in"

    def test_safe_margin_constant_is_mobile_safe(self) -> None:
        assert 0.04 <= SAFE_MARGIN_RATIO <= 0.12


# ---------------------------------------------------------------------------
# Multi-character rendering
# ---------------------------------------------------------------------------


class TestMultiCharacterRendering:
    def test_two_characters_get_distinct_positions(self) -> None:
        r = _renderer()
        comp = SceneComposition(
            characters=[
                CharacterSpec(name="a", x=0.3, y=0.75),
                CharacterSpec(name="b", x=0.7, y=0.78),
            ]
        )
        st = r._evaluate_motion_state([], 1.0, 4.0, W, H, "idle", composition=comp)
        r._resolve_named_characters(st, 1.0, 4.0, W, H)
        pa = st["named_characters"]["a"]["pose"]
        pb = st["named_characters"]["b"]["pose"]
        assert pa.stickman_x < pb.stickman_x
        assert abs(pa.stickman_x - int(0.3 * W)) <= 2

    def test_character_scale_affects_size(self) -> None:
        r = _renderer()
        big = CharacterSpec(name="big", scale=1.6, x=0.3)
        small = CharacterSpec(name="small", scale=0.6, x=0.7)
        st = r._evaluate_motion_state(
            [], 1.0, 4.0, W, H, "idle",
            composition=SceneComposition(characters=[big, small]),
        )
        r._resolve_named_characters(st, 1.0, 4.0, W, H)
        assert (
            st["named_characters"]["big"]["pose"].head_radius
            > st["named_characters"]["small"]["pose"].head_radius
        )

    def test_foreground_larger_than_background(self) -> None:
        fg = CharacterSpec(name="fg", y=0.85, scale=1.25)
        bg = CharacterSpec(name="bg", y=0.55, scale=0.65)
        r = _renderer()
        st = r._evaluate_motion_state(
            [], 1.0, 4.0, W, H, "idle",
            composition=SceneComposition(characters=[fg, bg]),
        )
        r._resolve_named_characters(st, 1.0, 4.0, W, H)
        assert (
            st["named_characters"]["fg"]["pose"].head_radius
            > st["named_characters"]["bg"]["pose"].head_radius
        )

    def test_all_poses_resolve_for_named_characters(self) -> None:
        r = _renderer()
        poses = ["idle", "walk", "run", "point", "wave", "jump", "talk", "surprised"]
        chars = [
            CharacterSpec(name=f"c{i}", pose=p, x=0.15 + i * 0.09)
            for i, p in enumerate(poses)
        ]
        st = r._evaluate_motion_state(
            [], 0.7, 3.0, W, H, "idle",
            composition=SceneComposition(characters=chars),
        )
        r._resolve_named_characters(st, 0.7, 3.0, W, H)
        for i in range(len(poses)):
            assert st["named_characters"][f"c{i}"]["pose"] is not None

    def test_invisible_character_stays_hidden(self) -> None:
        r = _renderer()
        ghost = CharacterSpec(name="ghost", visible=False, x=0.5)
        st = r._evaluate_motion_state(
            [], 1.0, 4.0, W, H, "idle",
            composition=SceneComposition(characters=[ghost]),
        )
        r._resolve_named_characters(st, 1.0, 4.0, W, H)
        cs = st["named_characters"]["ghost"]
        data = r._generate_frame(
            W, H, 1.0, 4.0, 30, 120,
            r._compute_pose("idle", 1.0, 4.0, W, H),
            job={}, motion_state=st,
        )
        assert len(data) == W * H * 3 and cs["visible"] is False


# ---------------------------------------------------------------------------
# Emotions, motion routing, objects
# ---------------------------------------------------------------------------


class TestEmotionRendering:
    @pytest.mark.parametrize(
        "emotion", ["neutral", "happy", "frustrated", "focused", "surprised"]
    )
    def test_emotions_produce_expected_colors(self, emotion: str) -> None:
        r = _renderer()
        st = r._evaluate_motion_state(
            [], 1.0, 4.0, W, H, "idle",
            composition=SceneComposition(
                characters=[CharacterSpec(name="c", emotion=emotion)]
            ),
        )
        r._resolve_named_characters(st, 1.0, 4.0, W, H)
        color = st["named_characters"]["c"]["pose"].color
        expected = CharacterSpec(emotion=emotion).effective_color
        assert color == expected

    def test_sad_posture_differs_from_neutral(self) -> None:
        r = _renderer()
        sad = r._compute_pose("idle", 0.5, 2.0, 320, 240, emotion="sad")
        neutral = r._compute_pose("idle", 0.5, 2.0, 320, 240)
        assert sad.head_y > neutral.head_y


class TestNamedMotionRouting:
    def test_move_targets_named_character_not_primary(self) -> None:
        r = _renderer()
        m = Motion(
            type="move", target="character", target_id="bob",
            start_time=0.0, duration=2.0,
            parameters={"from": {"x": 0.8, "y": 0.78}, "to": {"x": 0.6, "y": 0.78}},
        )
        st = r._evaluate_motion_state(
            [m], 2.0, 4.0, W, H, "idle",
            composition=SceneComposition(
                characters=[CharacterSpec(name="alice"), CharacterSpec(name="bob")]
            ),
        )
        assert st["named_characters"]["bob"]["x"] == int(0.6 * W)
        assert st["named_characters"]["alice"]["x"] is None

    def test_unnamed_character_motion_still_drives_primary(self) -> None:
        r = _renderer()
        m = Motion(
            type="move", target="character",
            start_time=0.0, duration=1.0,
            parameters={"from": {"x": 0.2, "y": 0.75}, "to": {"x": 0.4, "y": 0.75}},
        )
        st = r._evaluate_motion_state([m], 1.0, 2.0, W, H, "walk")
        assert st["character_x"] == pytest.approx(0.4 * W)


def test_multi_scene_visual_plan_uses_structured_fields_and_preserves_transition(monkeypatch, tmp_path) -> None:
    captured: list[dict[str, object]] = []

    def fake_render(self: StickmanRenderer, request):
        captured.append(request.job)
        return {
            "job_id": request.job["job_id"],
            "status": "completed",
            "scene_number": request.job["scene_number"],
            "output_reference": f"/tmp/{request.job['job_id']}.mp4",
            "duration_seconds": request.job["duration_seconds"],
        }

    monkeypatch.setattr(StickmanRenderer, "render", fake_render)

    pipeline = AutoPublishPipeline(output_directory=str(tmp_path / "publish"))
    plan = VideoPlan(
        title="Structured Multi-Scene Demo",
        scenes=[
            ScenePlan(
                narration="First scene",
                visual=VisualScene(
                    visual_prompt="legacy prompt",
                    animation_instructions="legacy walk",
                    camera_instructions="legacy pan",
                    camera_pattern="pan",
                    character_action="talk",
                    motions=[
                        Motion(
                            type="move",
                            target="character",
                            target_id="alice",
                            start_time=0.0,
                            duration=2.0,
                            parameters={"from": {"x": 0.15, "y": 0.75}, "to": {"x": 0.45, "y": 0.75}},
                        )
                    ],
                    characters=[
                        {"name": "alice", "pose": "talk", "emotion": "focused", "x": 0.25, "y": 0.75, "scale": 1.0},
                        {"name": "bob", "pose": "idle", "emotion": "neutral", "x": 0.7, "y": 0.78, "scale": 0.9},
                    ],
                    objects=[{"name": "clock", "type": "clock", "x": 0.8, "y": 0.2, "scale": 1.0, "rotation": 0.0, "opacity": 1.0}],
                    text_elements=[{"text": "Key insight", "x": 0.5, "y": 0.15, "size": "large", "color": (255, 255, 255), "opacity": 1.0, "style": "bold"}],
                    visual_effects=[{"type": "highlight", "target": "clock", "start": 0.5, "duration": 1.0, "parameters": {"color": (255, 230, 120)}}],
                    camera_spec={"pattern": "focus_on_character", "focus_target": "alice", "duration": 2.0, "easing": "ease_in_out"},
                    transition=Transition(type="slide_left", duration=0.5),
                ),
            ),
            ScenePlan(
                narration="Second scene",
                visual=VisualScene(
                    visual_prompt="legacy prompt",
                    animation_instructions="legacy wave",
                    camera_instructions="legacy zoom",
                    camera_pattern="zoom_in",
                    character_action="wave",
                    motions=[
                        Motion(
                            type="zoom",
                            target="camera",
                            start_time=0.0,
                            duration=2.0,
                            parameters={"from": 1.0, "to": 1.15},
                        )
                    ],
                    characters=[{"name": "alice", "pose": "wave", "emotion": "happy", "x": 0.35, "y": 0.75, "scale": 1.1}],
                    objects=[{"name": "notebook", "type": "notebook", "x": 0.35, "y": 0.65, "scale": 1.0}],
                    text_elements=[{"text": "Next step", "x": 0.5, "y": 0.88, "size": "normal", "color": (255, 255, 255), "opacity": 1.0}],
                    visual_effects=[{"type": "pulse", "target": "alice", "start": 0.2, "duration": 1.2, "parameters": {"color": (100, 220, 255)}}],
                    camera_spec={"pattern": "slow_zoom_in", "duration": 2.0},
                    transition=Transition(type="fade", duration=0.35),
                ),
            ),
        ],
    )

    segments = [
        {"scene_number": 1, "audio_reference": "/tmp/a1.wav", "duration_seconds": 2.0},
        {"scene_number": 2, "audio_reference": "/tmp/a2.wav", "duration_seconds": 2.0},
    ]

    result = pipeline._render_scenes(plan, segments)

    assert result["status"] == "completed"
    assert result["render_outputs"][0]["transition_to_next"]["type"] == "slide_left"
    assert result["render_outputs"][1]["transition_to_next"]["type"] == "fade"
    assert captured[0]["camera_instructions"] == ""
    assert captured[0]["animation_instructions"] == ""
    assert any(m["target"] == "camera" for m in captured[0]["motions"]) is False
    assert captured[0]["visual_description"]["characters"][0]["name"] == "alice"
    assert captured[0]["visual_description"]["characters"][0]["scale"] > 1.0
    assert captured[0]["visual_description"]["characters"][0]["y"] < 0.75
    assert captured[0]["visual_description"]["text_elements"][0]["fade_out"] == 0.5
    assert captured[0]["visual_description"]["camera"]["pattern"] == "focus_on_character"


class TestObjectState:
    def test_typed_objects_seed_pixel_positions(self) -> None:
        r = _renderer()
        objs = [
            ObjectSpec(name="desk", type="desk", x=0.5, y=0.72),
            ObjectSpec(name="lamp", type="light_bulb", x=0.85, y=0.45),
        ]
        st = r._evaluate_motion_state(
            [], 0.0, 4.0, W, H, "idle",
            composition=SceneComposition(objects=objs),
        )
        assert st["typed_objects"]["desk"]["x"] == int(0.5 * W)
        assert st["typed_objects"]["lamp"]["y"] == int(0.45 * H)

    def test_object_move_fade_rotate_motions_apply(self) -> None:
        r = _renderer()
        motions = [
            Motion(type="move", target="object", target_id="clock",
                   start_time=0.0, duration=1.0,
                   parameters={"from": {"x": 0.1, "y": 0.2}, "to": {"x": 0.5, "y": 0.2}}),
            Motion(type="fade", target="object", target_id="clock",
                   start_time=0.0, duration=1.0,
                   parameters={"from": 0.0, "to": 1.0}),
            Motion(type="rotate", target="object", target_id="clock",
                   start_time=0.0, duration=1.0,
                   parameters={"from": 0.0, "to": 90.0}),
        ]
        st = r._evaluate_motion_state(
            motions, 1.0, 4.0, W, H, "idle",
            composition=SceneComposition(
                objects=[ObjectSpec(name="clock", type="clock")]
            ),
        )
        ob = st["typed_objects"]["clock"]
        assert ob["x"] == pytest.approx(0.5 * W)
        assert ob["opacity"] == pytest.approx(1.0)
        assert ob["rotation"] == pytest.approx(90.0)

    def test_object_exit_moves_offscreen(self) -> None:
        r = _renderer()
        m = Motion(type="exit", target="object", target_id="doc",
                   start_time=0.0, duration=1.0, parameters={"direction": "right"})
        st = r._evaluate_motion_state(
            [m], 1.0, 2.0, W, H, "idle",
            composition=SceneComposition(
                objects=[ObjectSpec(name="doc", type="document")]
            ),
        )
        assert st["typed_objects"]["doc"]["x"] >= W


# ---------------------------------------------------------------------------
# Camera patterns
# ---------------------------------------------------------------------------


class TestCameraPatterns:
    @pytest.mark.parametrize(
        "pattern,expect_zoom_up",
        [("slow_zoom_in", True), ("slow_zoom_out", False)],
    )
    def test_zoom_direction(self, pattern: str, expect_zoom_up: bool) -> None:
        r = _renderer()
        st = r._evaluate_motion_state(
            [], 3.5, 4.0, W, H, "idle",
            composition=SceneComposition(camera=CameraSpec(pattern=pattern)),
        )
        if expect_zoom_up:
            assert st["camera_zoom"] > 1.05
        else:
            assert st["camera_zoom"] < 1.1

    def test_pan_left_moves_viewport_left(self) -> None:
        r = _renderer()
        st = r._evaluate_motion_state(
            [], 3.5, 4.0, W, H, "idle",
            composition=SceneComposition(camera=CameraSpec(pattern="pan_left")),
        )
        assert st["camera_pan_x"] < 0

    def test_focus_on_object_centers_target(self) -> None:
        r = _renderer()
        clock = ObjectSpec(name="clock", type="clock", x=0.85, y=0.25)
        st = r._evaluate_motion_state(
            [], 4.0, 4.0, W, H, "idle",
            composition=SceneComposition(
                objects=[clock],
                camera=CameraSpec(pattern="focus_on_object", focus_target="clock"),
            ),
        )
        zoom = st["camera_zoom"]
        assert zoom > 1.2
        tx = (int(0.85 * W) - W / 2) * zoom + W / 2 + st["camera_pan_x"]
        assert abs(tx - W / 2) < 30

    def test_focus_on_character_uses_resolved_position(self) -> None:
        r = _renderer()
        hero = CharacterSpec(name="hero", x=0.2, y=0.75)
        st = r._evaluate_motion_state(
            [], 4.0, 4.0, W, H, "idle",
            composition=SceneComposition(
                characters=[hero],
                camera=CameraSpec(pattern="focus_on_character",
                                  focus_target="hero"),
            ),
        )
        assert st["camera_zoom"] > 1.25
        tx = (int(0.2 * W) - W / 2) * st["camera_zoom"] + W / 2 + st["camera_pan_x"]
        assert abs(tx - W / 2) < 30

    def test_structured_camera_yields_to_explicit_motion(self) -> None:
        r = _renderer()
        m = Motion(type="zoom", target="camera", start_time=0.0, duration=4.0,
                   parameters={"from": 1.0, "to": 2.0})
        st = r._evaluate_motion_state(
            [m], 4.0, 4.0, W, H, "idle",
            composition=SceneComposition(camera=CameraSpec(pattern="slow_zoom_in")),
        )
        assert st["camera_zoom"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Effects and text state
# ---------------------------------------------------------------------------


class TestEffectState:
    def _frame(self, r: StickmanRenderer, comp: SceneComposition, t: float):
        st = r._evaluate_motion_state([], t, 4.0, W, H, "idle", composition=comp)
        return r._generate_frame(
            W, H, t, 4.0, int(t * 30), 120,
            r._compute_pose("idle", t, 4.0, W, H),
            job={}, motion_state=st,
        )

    def test_highlight_effect_renders_in_window(self) -> None:
        r = _renderer()
        comp = SceneComposition(
            objects=[ObjectSpec(name="clock", type="clock", x=0.8, y=0.3)],
            effects=[EffectSpec(type="highlight", target="clock",
                                start=0.5, duration=1.5)],
        )
        assert len(self._frame(r, comp, 1.0)) == W * H * 3

    def test_inactive_effect_is_crash_free(self) -> None:
        r = _renderer()
        comp = SceneComposition(
            effects=[EffectSpec(type="spotlight", target="scene",
                                start=3.0, duration=1.0)],
        )
        assert len(self._frame(r, comp, 0.5)) == W * H * 3

    @pytest.mark.parametrize("etype", ["glow", "circle_highlight", "pulse"])
    def test_effect_variants_render(self, etype: str) -> None:
        r = _renderer()
        comp = SceneComposition(
            characters=[CharacterSpec(name="c")],
            effects=[EffectSpec(type=etype, target="c", start=0.0, duration=2.0)],
        )
        assert len(self._frame(r, comp, 1.0)) == W * H * 3


class TestTextState:
    def test_long_text_stays_inside_safe_width(self) -> None:
        r = _renderer()
        long_text = TextSpec(
            text=("An extremely long caption line meant to wrap across "
                  "multiple rows inside the mobile safe area"),
            size="normal", max_width=0.84,
        )
        st = r._evaluate_motion_state(
            [], 1.0, 4.0, W, H, "idle",
            composition=SceneComposition(text_elements=[long_text]),
        )
        data = r._generate_frame(
            W, H, 1.0, 4.0, 30, 120,
            r._compute_pose("idle", 1.0, 4.0, W, H),
            job={}, motion_state=st,
        )
        assert len(data) == W * H * 3
        margin = int(W * SAFE_MARGIN_RATIO)
        assert margin > 0 and margin < W // 4

    def test_headline_and_supporting_text_render(self) -> None:
        r = _renderer()
        comp = SceneComposition(text_elements=[
            TextSpec(text="Big idea", size="headline", y=0.12),
            TextSpec(text="supporting detail", size="small", y=0.94),
        ])
        st = r._evaluate_motion_state([], 0.5, 3.0, W, H, "idle", composition=comp)
        data = r._generate_frame(
            W, H, 0.5, 3.0, 15, 90,
            r._compute_pose("talk", 0.5, 3.0, W, H),
            job={}, motion_state=st,
        )
        assert len(data) == W * H * 3

    def test_appear_at_delays_visibility(self) -> None:
        spec = TextSpec(text="late", appear_at=2.0, fade_in=0.5)
        assert spec.effective_opacity(1.0, 4.0) == 0.0
        assert spec.effective_opacity(3.0, 4.0) > 0.5


# ---------------------------------------------------------------------------
# Schema / pipeline plumbing
# ---------------------------------------------------------------------------


class TestVisualSceneSchema:
    def test_new_fields_default_empty(self) -> None:
        plan = VideoPlan.from_dict({"title": "t",
                                    "scenes": [{"narration": "n"}]})
        visual = plan.scenes[0].visual
        assert visual is not None
        assert visual.characters == []
        assert visual.objects == []
        assert visual.environment == {}
        assert visual.text_elements == []
        assert visual.visual_effects == []
        assert visual.camera_spec == {}

    def test_composition_fields_parse_from_json(self) -> None:
        plan = VideoPlan.from_dict({
            "title": "t",
            "scenes": [{
                "narration": "n",
                "visual": {
                    "characters": [{"name": "student", "pose": "talk",
                                    "emotion": "focused", "x": 0.4}],
                    "objects": [{"name": "clock", "type": "clock", "x": 0.8}],
                    "environment": {"type": "study_desk"},
                    "text_elements": [{"text": "Focus", "size": "headline"}],
                    "visual_effects": [{"type": "highlight", "target": "clock"}],
                    "camera_spec": {"pattern": "focus_on_object",
                                    "focus_target": "clock"},
                },
            }],
        })
        v = plan.scenes[0].visual
        assert v.characters[0]["name"] == "student"
        assert v.objects[0]["type"] == "clock"
        assert v.environment["type"] == "study_desk"
        assert v.text_elements[0]["text"] == "Focus"
        assert v.visual_effects[0]["target"] == "clock"
        assert v.camera_spec["pattern"] == "focus_on_object"

    def test_has_visual_intent_true_for_composition(self) -> None:
        plan = VideoPlan.from_dict({
            "title": "t",
            "scenes": [{
                "narration": "n",
                "visual": {"objects": [{"name": "book", "type": "book"}]},
            }],
        })
        assert plan.scenes[0].visual.has_visual_intent() is True

    def test_legacy_scene_without_visual_still_works(self) -> None:
        scene = ScenePlan(narration="plain")
        assert scene.visual.has_visual_intent() is False


# ---------------------------------------------------------------------------
# Integration: full render path (requires FFmpeg)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(not _ffmpeg_available(), reason="FFmpeg is not available")
class TestEndToEndCompositionRender:
    def _config(self, tmpdir: str) -> RenderConfig:
        return RenderConfig(
            width=270, height=480, fps=10,
            video_format="mp4", video_codec="libx264", audio_format="aac",
            output_directory=tmpdir,
            filename_template="vq_{job_id}.mp4",
        )

    def _job(self, job_id: str, duration: int, visual_desc: dict) -> RenderJobSpec:
        return RenderJobSpec(
            job_id=job_id, scene_number=1, duration_seconds=duration,
            render_type="stickman_animation",
            character_ids=[], asset_ids=[],
            visual_prompt="composed quality scene",
            animation_instructions="talk",
            camera_instructions="static",
            audio_requirements="", motions=[], transition_to_next=None,
            audio_request=None,
            visual_description=visual_desc,
        )

    def test_multi_character_scene_renders_valid_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = {
                "environment": {"type": "study_desk"},
                "characters": [
                    {"name": "student", "pose": "point", "emotion": "focused",
                     "x": 0.35, "y": 0.75},
                    {"name": "friend", "pose": "surprised", "emotion": "surprised",
                     "x": 0.7, "y": 0.78, "scale": 0.8},
                ],
                "objects": [
                    {"name": "desk", "type": "desk", "x": 0.5, "y": 0.86},
                    {"name": "books", "type": "stack_of_books",
                     "x": 0.16, "y": 0.74},
                    {"name": "clock", "type": "clock", "x": 0.82, "y": 0.22},
                ],
                "text_elements": [
                    {"text": "Time flies when focus dies", "size": "headline",
                     "y": 0.14},
                ],
                "effects": [
                    {"type": "highlight", "target": "clock",
                     "start": 1.0, "duration": 1.5},
                ],
                "camera": {"pattern": "focus_on_character",
                           "focus_target": "student", "duration": 2.5},
            }
            result = render_stickman_job(self._job("vq-multi", 3, desc),
                                         self._config(tmpdir))
            assert result["status"] == "completed", result.get("error")
            out = Path(result["output_reference"])
            assert out.exists() and out.stat().st_size > 1000

    def test_environment_and_text_scene_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            desc = {
                "environment": {"type": "bedroom"},
                "characters": [
                    {"name": "sleeper", "pose": "idle", "emotion": "sad",
                     "x": 0.5, "y": 0.8},
                ],
                "text_elements": [
                    {"text": "Tomorrow you will restart.", "size": "large",
                     "y": 0.88, "fade_in": 0.4},
                ],
                "camera": {"pattern": "slow_zoom_in", "duration": 2.0},
            }
            result = render_stickman_job(self._job("vq-env", 2, desc),
                                         self._config(tmpdir))
            assert result["status"] == "completed", result.get("error")

    def test_legacy_job_without_description_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy = RenderJobSpec(
                job_id="legacy", scene_number=1, duration_seconds=1,
                render_type="stickman_animation",
                character_ids=[], asset_ids=[],
                visual_prompt="A stickman walking across the screen",
                animation_instructions="Walk cycle",
                camera_instructions="Static",
                audio_requirements="", motions=[], transition_to_next=None,
                audio_request=None, visual_description=None,
            )
            result = render_stickman_job(legacy, self._config(tmpdir))
            assert result["status"] == "completed"






