"""Tests for CameraPlanner (V1.4-D).

Comprehensive test suite for the deterministic camera continuity planning
service. Tests cover empty sequences, single scenes, explicit camera
preservation, treatment-based selection, continuity tracking, repetition
detection, diversity integration, determinism, no-mutation, edge cases,
and JSON serialization.
"""

from __future__ import annotations

import json

from src.models.content_package import Motion
from src.pipeline.auto_publish_pipeline import ScenePlan, VisualScene
from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.services.camera_planner import (
    CameraDecision,
    CameraPlan,
    CameraPlanner,
    SUPPORTED_CONTINUITY_STATES,
    _resolve_scene,
    _resolve_secondary,
)
from src.services.visual_story_planner import (
    VisualStoryPlan,
    VisualStoryDecision,
    SUPPORTED_TREATMENTS,
)
from src.services.visual_diversity import (
    VisualDiversityReport,
    VisualDiversityDecision,
)
from src.services.composition_planner import (
    CompositionPlan,
    CompositionDecision,
    SUPPORTED_COMPOSITION_TYPES,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_scene(
    narration: str = "Test",
    *,
    camera_pattern: str | None = None,
    camera_spec: dict | None = None,
    primary_focus: str | None = None,
    scene_role: str | None = None,
    characters: list[dict] | None = None,
    objects: list[dict] | None = None,
    text_elements: list[dict] | None = None,
    motions: list[Motion] | None = None,
    no_visual: bool = False,
) -> ScenePlan:
    """Create a ScenePlan with optional visual configuration."""
    if no_visual:
        visual = VisualScene(camera_pattern="", primary_focus="")
        return ScenePlan(narration=narration, visual=visual)

    visual_kwargs: dict = {}
    if camera_pattern is not None:
        visual_kwargs["camera_pattern"] = camera_pattern
    if camera_spec is not None:
        visual_kwargs["camera_spec"] = camera_spec
    if primary_focus is not None:
        visual_kwargs["primary_focus"] = primary_focus
    if scene_role is not None:
        visual_kwargs["scene_role"] = scene_role
    if characters is not None:
        visual_kwargs["characters"] = characters
    if objects is not None:
        visual_kwargs["objects"] = objects
    if text_elements is not None:
        visual_kwargs["text_elements"] = text_elements
    if motions is not None:
        visual_kwargs["motions"] = motions

    visual = VisualScene(**visual_kwargs) if visual_kwargs else None
    return ScenePlan(narration=narration, visual=visual)
def _make_character(name: str = "hero") -> dict:
    """Create a simple character dict."""
    return {"name": name, "pose": "idle", "emotion": "neutral", "x": 0.5, "y": 0.5, "scale": 1.0, "color": "blue"}


def _make_object(name: str = "book", obj_type: str = "book") -> dict:
    """Create a simple object dict."""
    return {"name": name, "type": obj_type, "x": 0.5, "y": 0.5, "scale": 1.0, "rotation": 0, "opacity": 1.0}


def _make_story_plan(
    treatments: list[str],
    beat_types: list[str] | None = None,
    cameras: list[str] | None = None,
    focus_targets: list[str] | None = None,
) -> VisualStoryPlan:
    """Create a VisualStoryPlan with specified treatments."""
    decisions = []
    for i, treatment in enumerate(treatments):
        decisions.append(
            VisualStoryDecision(
                scene_index=i,
                beat_type=beat_types[i] if beat_types else "HOOK",
                focus_target=focus_targets[i] if focus_targets else "",
                treatment=treatment,
                camera_pattern=cameras[i] if cameras else "static",
                preferred_motion_types=("fade",),
                transition_type=None,
                repeated_with_previous=False,
                warnings=(),
            )
        )
    return VisualStoryPlan(decisions=tuple(decisions), warnings=())


def _make_diversity_report(
    repeated_cameras: list[bool] | None = None,
    camera_recs: list[tuple[str, ...]] | None = None,
) -> VisualDiversityReport:
    """Create a VisualDiversityReport for testing."""
    decisions = []
    for i in range(len(repeated_cameras or [False])):
        decisions.append(
            VisualDiversityDecision(
                scene_index=i,
                repeated_with_previous=repeated_cameras[i] if repeated_cameras else False,
                repeated_camera=repeated_cameras[i] if repeated_cameras else False,
                repeated_motion=False,
                repeated_treatment=False,
                repeated_focus_pattern=False,
                warnings=(),
                camera_recommendations=camera_recs[i] if camera_recs else (),
                motion_recommendations=(),
                treatment_recommendations=(),
            )
        )
    return VisualDiversityReport(decisions=tuple(decisions), warnings=())
def _make_composition_plan(
    comp_types: list[str],
) -> CompositionPlan:
    """Create a CompositionPlan for testing."""
    decisions = []
    for i, comp_type in enumerate(comp_types):
        decisions.append(
            CompositionDecision(
                scene_index=i,
                composition_type=comp_type,
                primary_region="center",
                secondary_region=None,
                text_region=None,
                subject_regions=("center",),
                recommended_scale="medium",
                recommended_alignment="center",
                repeated_with_previous=False,
                warnings=(),
            )
        )
    return CompositionPlan(decisions=tuple(decisions), warnings=())


# ---------------------------------------------------------------------------
# 1. Empty sequence
# ---------------------------------------------------------------------------


class TestEmptySequence:
    """Empty sequence produces empty plan."""

    def test_empty_list_returns_empty_plan(self) -> None:
        planner = CameraPlanner()
        plan = planner.plan([])
        assert len(plan.decisions) == 0
        assert len(plan.warnings) == 0

    def test_empty_plan_to_dict(self) -> None:
        planner = CameraPlanner()
        plan = planner.plan([])
        result = plan.to_dict()
        assert result == {"decisions": [], "warnings": []}
# ---------------------------------------------------------------------------
# 3. Explicit camera preservation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 2. Single scene
# ---------------------------------------------------------------------------


class TestSingleScene:
    """Single scene produces one decision with established continuity."""

    def test_single_scene_one_decision(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1
        assert plan.decisions[0].scene_index == 0

    def test_single_scene_continuity_established(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].continuity_from_previous == "established"

    def test_single_scene_valid_pattern(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("Hello", characters=[_make_character()])]
        plan = planner.plan(scenes)
        assert plan.decisions[0].recommended_pattern in SUPPORTED_CAMERA_PATTERNS

    def test_single_scene_no_repetition(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].repeated_with_previous is False


# ---------------------------------------------------------------------------
# 3. Explicit camera preservation
# ---------------------------------------------------------------------------
class TestExplicitCameraPreservation:
    """Explicit camera settings are always preserved."""

    def test_explicit_camera_pattern_preserved(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_pattern="slow_zoom_in")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].recommended_pattern == "slow_zoom_in"
        assert plan.decisions[0].explicit_camera_preserved is True

    def test_explicit_camera_spec_pattern_preserved(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_spec={"pattern": "pan_right"})]
        plan = planner.plan(scenes)
        assert plan.decisions[0].recommended_pattern == "pan_right"
        assert plan.decisions[0].explicit_camera_preserved is True

    def test_explicit_camera_focus_target_preserved(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene(
                "A",
                characters=[_make_character("hero")],
                camera_spec={"pattern": "focus_on_character", "focus_target": "hero"},
            )
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[0].focus_target == "hero"

    def test_explicit_camera_warning_recorded(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_pattern="static")]
        plan = planner.plan(scenes)
        assert "explicit_camera_preserved" in plan.decisions[0].warnings

    def test_camera_hold_derives_static(self) -> None:
        """'hold' is the default no-intent camera value.

        The planner sees it as non-explicit (not a directed camera choice),
        so it derives a pattern rather than reporting it as preserved.
        """
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_pattern="hold")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].recommended_pattern == "static"
        assert plan.decisions[0].explicit_camera_preserved is False
# ---------------------------------------------------------------------------
# 4. Treatment-based camera selection
# ---------------------------------------------------------------------------


class TestTreatmentBasedSelection:
    """Camera patterns derived from treatment classifications."""

    def test_problem_focus_with_character(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", characters=[_make_character("hero")])]
        story = _make_story_plan(["problem_focus"])
        plan = planner.plan(scenes, story_plan=story)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("focus_on_character", "slow_zoom_in", "static")

    def test_explain_treatment(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A")]
        story = _make_story_plan(["explain"])
        plan = planner.plan(scenes, story_plan=story)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("static", "slow_zoom_in", "pan_right")

    def test_proof_treatment_with_object(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", objects=[_make_object("book", "book")])]
        story = _make_story_plan(["proof"])
        plan = planner.plan(scenes, story_plan=story)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("focus_on_object", "slow_zoom_in", "static")

    def test_cta_treatment(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", characters=[_make_character("hero")])]
        story = _make_story_plan(["cta"])
        plan = planner.plan(scenes, story_plan=story)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("static", "slow_zoom_out", "focus_on_character")

    def test_solution_growth_treatment(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A")]
        story = _make_story_plan(["solution_growth"])
        plan = planner.plan(scenes, story_plan=story)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("slow_zoom_in", "zoom_then_pan", "static")

    def test_compare_treatment(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A")]
        story = _make_story_plan(["compare"])
        plan = planner.plan(scenes, story_plan=story)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("static", "pan_left", "pan_right")

    def test_establish_treatment(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A")]
        story = _make_story_plan(["establish"])
        plan = planner.plan(scenes, story_plan=story)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("static", "slow_zoom_in", "pan_right")


# ---------------------------------------------------------------------------
# 5. Composition-based camera selection
# ---------------------------------------------------------------------------


class TestCompositionBasedSelection:
    """Camera patterns derived from V1.4-C composition types."""

    def test_single_subject_composition(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", characters=[_make_character()])]
        comp = _make_composition_plan(["single_subject"])
        plan = planner.plan(scenes, composition_plan=comp)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("focus_on_character", "slow_zoom_in", "static")

    def test_comparison_composition(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A")]
        comp = _make_composition_plan(["comparison"])
        plan = planner.plan(scenes, composition_plan=comp)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("static", "pan_left", "pan_right")

    def test_object_led_composition(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", objects=[_make_object("book", "book")])]
        comp = _make_composition_plan(["object_led"])
        plan = planner.plan(scenes, composition_plan=comp)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("focus_on_object", "slow_zoom_in", "static")

    def test_text_led_composition(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A")]
        comp = _make_composition_plan(["text_led"])
        plan = planner.plan(scenes, composition_plan=comp)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("static", "slow_zoom_out")

    def test_treatment_overrides_composition_for_camera(self) -> None:
        """Treatment takes priority over composition type."""
        planner = CameraPlanner()
        scenes = [_make_scene("A", characters=[_make_character()])]
        story = _make_story_plan(["problem_focus"])
        comp = _make_composition_plan(["single_subject"])
        plan = planner.plan(scenes, story_plan=story, composition_plan=comp)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("focus_on_character", "slow_zoom_in", "static")
# ---------------------------------------------------------------------------
# 6. Continuity tracking
# ---------------------------------------------------------------------------


class TestContinuityTracking:
    """Continuity states are tracked between consecutive scenes."""

    def test_first_scene_established(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", characters=[_make_character()])]
        plan = planner.plan(scenes)
        assert plan.decisions[0].continuity_from_previous == "established"

    def test_same_pattern_held(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", characters=[_make_character()]),
            _make_scene("B", characters=[_make_character()]),
        ]
        plan = planner.plan(scenes)
        dec0 = plan.decisions[0]
        dec1 = plan.decisions[1]
        if dec0.recommended_pattern == dec1.recommended_pattern:
            assert dec1.continuity_from_previous == "held"
            assert dec1.repeated_with_previous is True

    def test_different_pattern_changed(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="slow_zoom_in"),
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[1].continuity_from_previous == "changed"
        assert plan.decisions[1].repeated_with_previous is False

    def test_continuity_state_valid(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="pan_left"),
            _make_scene("B", camera_pattern="pan_right"),
            _make_scene("C", camera_pattern="pan_left"),
        ]
        plan = planner.plan(scenes)
        for dec in plan.decisions:
            assert dec.continuity_from_previous in SUPPORTED_CONTINUITY_STATES

    def test_pan_reversal_detected(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="pan_left"),
            _make_scene("B", camera_pattern="pan_right"),
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[1].continuity_from_previous == "reversed"


# ---------------------------------------------------------------------------
# 7. Repetition detection
# ---------------------------------------------------------------------------


class TestRepetitionDetection:
    """Camera repetition is detected and warned about."""

    def test_repeated_camera_detected(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="static"),
        ]
        plan = planner.plan(scenes)
        dec1 = plan.decisions[1]
        assert dec1.repeated_with_previous is True
        assert "repeated_camera:static" in dec1.warnings

    def test_explicit_camera_repetition_warning(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="static"),
        ]
        plan = planner.plan(scenes)
        dec1 = plan.decisions[1]
        assert "explicit_camera_repetition" in dec1.warnings

    def test_no_repetition_with_different_cameras(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="slow_zoom_in"),
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[1].repeated_with_previous is False

    def test_camera_run_warning_on_third_repeat(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="static"),
            _make_scene("C", camera_pattern="static"),
        ]
        plan = planner.plan(scenes)
        dec2 = plan.decisions[2]
        assert any(w.startswith("camera_run:") for w in dec2.warnings)

    def test_low_camera_diversity_sequence_warning(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="static"),
            _make_scene("C", camera_pattern="static"),
        ]
        plan = planner.plan(scenes)
        assert "low_camera_diversity" in plan.warnings
# ---------------------------------------------------------------------------
# 8. Diversity integration
# ---------------------------------------------------------------------------


class TestDiversityIntegration:
    """Camera planner respects V1.4-B diversity recommendations."""

    def test_diversity_recommendation_used(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_pattern="static")]
        diversity = _make_diversity_report(
            repeated_cameras=[False],
            camera_recs=[("pan_right", "slow_zoom_in", "static")],
        )
        plan = planner.plan(scenes, diversity_report=diversity)
        dec = plan.decisions[0]
        assert dec.recommended_pattern in ("pan_right", "slow_zoom_in", "static")

    def test_diversity_repetition_triggers_alternative(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", characters=[_make_character()])]
        story = _make_story_plan(["establish"])
        diversity = _make_diversity_report(
            repeated_cameras=[True],
            camera_recs=[("pan_right", "slow_zoom_in")],
        )
        plan = planner.plan(scenes, story_plan=story, diversity_report=diversity)
        dec = plan.decisions[0]
        assert dec.recommended_pattern != "static"

    def test_diversity_rec_filtered_by_target_availability(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A")]
        diversity = _make_diversity_report(
            repeated_cameras=[True],
            camera_recs=[("focus_on_character", "focus_on_object", "pan_right")],
        )
        plan = planner.plan(scenes, diversity_report=diversity)
        dec = plan.decisions[0]
        assert dec.recommended_pattern == "pan_right"

    def test_no_diversity_report_works_standalone(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", characters=[_make_character()])]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1


# ---------------------------------------------------------------------------
# 9. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """CameraPlanner produces identical results for identical inputs."""

    def test_identical_results_on_repeat(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="slow_zoom_in"),
            _make_scene("C", camera_pattern="pan_left"),
        ]
        plan1 = planner.plan(scenes)
        plan2 = planner.plan(scenes)
        assert plan1.to_dict() == plan2.to_dict()

    def test_identical_with_story_plan(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", characters=[_make_character()]),
            _make_scene("B", characters=[_make_character()]),
        ]
        story = _make_story_plan(["problem_focus", "explain"])
        plan1 = planner.plan(scenes, story_plan=story)
        plan2 = planner.plan(scenes, story_plan=story)
        assert plan1.to_dict() == plan2.to_dict()

    def test_identical_with_all_plans(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", characters=[_make_character()]),
            _make_scene("B", characters=[_make_character()]),
            _make_scene("C"),
        ]
        story = _make_story_plan(["problem_focus", "explain", "cta"])
        diversity = _make_diversity_report(
            repeated_cameras=[False, False, False],
            camera_recs=[(), (), ()],
        )
        comp = _make_composition_plan(["single_subject", "subject_support", "text_led"])
        plan1 = planner.plan(scenes, story_plan=story, diversity_report=diversity, composition_plan=comp)
        plan2 = planner.plan(scenes, story_plan=story, diversity_report=diversity, composition_plan=comp)
        assert plan1.to_dict() == plan2.to_dict()


# ---------------------------------------------------------------------------
# 10. No mutation
# ---------------------------------------------------------------------------


class TestNoMutation:
    """CameraPlanner does not modify input objects."""

    def test_scenes_not_mutated(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", characters=[_make_character("hero")],
                        camera_spec={"pattern": "focus_on_character"}),
            _make_scene("B", characters=[_make_character("villain")]),
        ]
        spec_patterns = []
        for s in scenes:
            if s.visual and s.visual.camera_spec:
                spec_patterns.append(s.visual.camera_spec.get("pattern", ""))
            else:
                spec_patterns.append("")
        plan = planner.plan(scenes)
        for i, scene in enumerate(scenes):
            if scene.visual and scene.visual.camera_spec:
                actual = scene.visual.camera_spec.get("pattern", "")
            else:
                actual = ""
            assert actual == spec_patterns[i]

    def test_scene_index_preserved(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene(f"Scene {i}", camera_pattern="static") for i in range(5)]
        plan = planner.plan(scenes)
        for i, decision in enumerate(plan.decisions):
            assert decision.scene_index == i

    def test_focus_target_not_overwritten(self) -> None:
        planner = CameraPlanner()
        scene = _make_scene(
            "A",
            characters=[_make_character("hero")],
            camera_spec={"pattern": "focus_on_character", "focus_target": "custom_target"},
        )
        plan = planner.plan([scene])
        assert plan.decisions[0].focus_target == "custom_target"
# ---------------------------------------------------------------------------
# 11. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge cases for robustness."""

    def test_scene_without_visual(self) -> None:
        planner = CameraPlanner()
        scenes = [ScenePlan(narration="No visual")]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1

    def test_scene_with_empty_visual(self) -> None:
        planner = CameraPlanner()
        scenes = [ScenePlan(narration="Empty", visual=VisualScene())]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1

    def test_no_focus_target_when_no_subjects(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_pattern="focus_on_character")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].focus_target is None

    def test_invalid_camera_pattern_falls_back(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_spec={"pattern": "unknown_camera"})]
        plan = planner.plan(scenes)
        assert plan.decisions[0].recommended_pattern in SUPPORTED_CAMERA_PATTERNS


# ---------------------------------------------------------------------------
# 12. JSON serialization
# ---------------------------------------------------------------------------


class TestJSONSerialization:
    """to_dict produces JSON-serializable results."""

    def test_decision_to_dict(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene("A", camera_pattern="static")]
        plan = planner.plan(scenes)
        result = plan.to_dict()
        assert "decisions" in result
        assert "warnings" in result

    def test_full_serialization(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", camera_pattern="static"),
            _make_scene("B", camera_pattern="slow_zoom_in"),
            _make_scene("C", camera_pattern="pan_left"),
        ]
        plan = planner.plan(scenes)
        json_str = json.dumps(plan.to_dict())
        assert isinstance(json_str, str)

    def test_serialization_with_all_inputs(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", characters=[_make_character()]),
            _make_scene("B", characters=[_make_character()]),
        ]
        story = _make_story_plan(["problem_focus", "explain"])
        diversity = _make_diversity_report(
            repeated_cameras=[False, False],
            camera_recs=[(), ()],
        )
        comp = _make_composition_plan(["single_subject", "subject_support"])
        plan = planner.plan(scenes, story_plan=story, diversity_report=diversity, composition_plan=comp)
        json_str = json.dumps(plan.to_dict())
        data = json.loads(json_str)
        assert len(data["decisions"]) == 2


# ---------------------------------------------------------------------------
# 13. Sequence order preservation
# ---------------------------------------------------------------------------


class TestSequenceOrderPreservation:
    """Scene indices and order are preserved."""

    def test_scene_indices_in_order(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene(f"Scene {i}") for i in range(5)]
        plan = planner.plan(scenes)
        for i, decision in enumerate(plan.decisions):
            assert decision.scene_index == i

    def test_five_scenes_all_decisions_present(self) -> None:
        planner = CameraPlanner()
        scenes = [_make_scene(f"Scene {i}") for i in range(5)]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 5

    def test_focus_targets_assigned_correctly(self) -> None:
        planner = CameraPlanner()
        scenes = [
            _make_scene("A", characters=[_make_character("char_a")]),
            _make_scene("B", characters=[_make_character("char_b")]),
        ]
        plan = planner.plan(scenes)
        for dec in plan.decisions:
            if dec.focus_target:
                assert isinstance(dec.focus_target, str)


# ---------------------------------------------------------------------------
# Scene-level target resolution helpers
# (_resolve_scene / _resolve_secondary)
# ---------------------------------------------------------------------------


class TestSceneTargetResolution:
    """Focused tests for the scene-level camera target resolution helpers."""

    def test_character_target_selected_when_available(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        assert _resolve_scene(scene) == "hero"

    def test_object_target_selected_when_no_character(self) -> None:
        scene = _make_scene(objects=[_make_object("book")])
        assert _resolve_scene(scene) == "book"

    def test_scene_fallback_when_no_targetable_elements(self) -> None:
        scene = _make_scene()
        assert _resolve_scene(scene) == "scene"

    def test_secondary_character_differs_from_primary(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero"), _make_character("sidekick")]
        )
        primary = _resolve_scene(scene)
        secondary = _resolve_secondary(scene, primary)
        assert primary == "hero"
        assert secondary == "sidekick"
        assert secondary != primary

    def test_secondary_object_differs_from_primary(self) -> None:
        scene = _make_scene(objects=[_make_object("book"), _make_object("chart")])
        primary = _resolve_scene(scene)
        secondary = _resolve_secondary(scene, primary)
        assert primary == "book"
        assert secondary == "chart"
        assert secondary != primary

    def test_mixed_scene_resolves_deterministically(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        assert _resolve_scene(scene) == "hero"
        assert _resolve_secondary(scene, "hero") == "book"
        assert _resolve_scene(scene) == _resolve_scene(scene)
        assert _resolve_secondary(scene, "hero") == _resolve_secondary(scene, "hero")

    def test_empty_scene_does_not_crash(self) -> None:
        scene = _make_scene(no_visual=True)
        assert _resolve_scene(scene) == "scene"
        assert _resolve_secondary(scene, "scene") is None
        assert _resolve_secondary(scene, None) is None

    def test_invalid_targets_are_not_invented(self) -> None:
        empty = _make_scene()
        assert _resolve_scene(empty, "character_99") == "scene"
        populated = _make_scene(characters=[_make_character("hero")])
        assert _resolve_scene(populated, "ghost") == "hero"
        assert _resolve_secondary(populated, "character_99") == "hero"

    def test_repeated_calls_produce_identical_results(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero"), _make_character("sidekick")],
            objects=[_make_object("book")],
        )
        for _ in range(3):
            assert _resolve_scene(scene) == "hero"
            assert _resolve_secondary(scene, "hero") == "sidekick"

    def test_explicit_camera_intent_preserved(self) -> None:
        scene = _make_scene(
            camera_spec={"focus_target": "book"},
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        assert _resolve_scene(scene, "book") == "book"
        assert _resolve_secondary(scene, "hero") == "book"

    def test_secondary_never_invents_target(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        assert _resolve_secondary(scene, "hero") is None

    def test_secondary_none_when_primary_is_only_target(self) -> None:
        scene = _make_scene(objects=[_make_object("book")])
        assert _resolve_secondary(scene, "book") is None
