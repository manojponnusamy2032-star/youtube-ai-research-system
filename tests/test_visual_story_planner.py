"""Tests for VisualStoryPlanner (V1.4-A advisory layer)."""

from __future__ import annotations

from src.models.content_package import Motion, Transition, SUPPORTED_MOTION_TYPES, SUPPORTED_TRANSITION_TYPES
from src.pipeline.auto_publish_pipeline import ScenePlan, VisualScene
from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.services.visual_story_planner import VisualStoryPlanner, VisualStoryDecision, VisualStoryPlan


class TestSingleSceneOneDecision:
    """Single scene produces exactly one VisualStoryDecision."""

    def test_single_scene_returns_one_decision(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [ScenePlan(narration="Hello world")]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1
        assert plan.decisions[0].scene_index == 0


class TestMultiSceneOrdering:
    """Multi-scene input preserves ordering and produces one decision per scene."""

    def test_three_scenes_ordered_decisions(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [
            ScenePlan(narration="First"),
            ScenePlan(narration="Second"),
            ScenePlan(narration="Third"),
        ]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 3
        for i, decision in enumerate(plan.decisions):
            assert decision.scene_index == i


class TestDeterministicOutput:
    """Identical inputs always produce identical outputs."""

    def test_same_input_twice_yields_same_plan(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [
            ScenePlan(narration="Hook", visual=VisualScene(scene_role="hook")),
            ScenePlan(narration="Problem", visual=VisualScene(scene_role="problem")),
            ScenePlan(narration="Solution", visual=VisualScene(scene_role="solution")),
        ]
        plan1 = planner.plan(scenes)
        plan2 = planner.plan(scenes)
        assert plan1.to_dict() == plan2.to_dict()


class TestNoMutation:
    """Planner never mutates input ScenePlan or VisualScene objects."""

    def test_scene_plan_unchanged_after_plan(self) -> None:
        planner = VisualStoryPlanner()
        original_scenes = [
            ScenePlan(narration="Test", visual=VisualScene(scene_role="hook", primary_focus="character"))
        ]
        original_visual = original_scenes[0].visual
        original_role = original_visual.scene_role
        original_focus = original_visual.primary_focus

        planner.plan(original_scenes)

class TestEmptySceneSafeFallback:
    """Empty or minimal scenes produce safe fallback decisions without errors."""

    def test_empty_scene_list_returns_empty_plan(self) -> None:
        planner = VisualStoryPlanner()
        plan = planner.plan([])
        assert len(plan.decisions) == 0
        assert len(plan.warnings) == 0

    def test_scene_without_visual_uses_fallback(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="No visual here")
        plan = planner.plan([scene])
        assert len(plan.decisions) == 1
        decision = plan.decisions[0]
        assert decision.treatment in {"establish", "problem_focus", "compare", "explain", "proof", "solution_growth", "cta"}
        assert decision.beat_type in {"HOOK", "PROBLEM", "CONTRAST", "EXPLANATION", "EXAMPLE", "SOLUTION", "CTA", "EXPLANATION"}

    def test_scene_with_empty_visual_scene(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="Empty visual", visual=VisualScene())
        plan = planner.plan([scene])
        assert len(plan.decisions) == 1


class TestExplicitCameraIntentPreservation:
    """Explicit camera patterns in input are preserved when valid."""

    def test_explicit_camera_pattern_preserved(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(
            narration="Test",
            visual=VisualScene(scene_role="hook", camera_spec={"pattern": "slow_zoom_in"})
        )
        plan = planner.plan([scene])
        assert plan.decisions[0].camera_pattern == "slow_zoom_in"

    def test_explicit_legacy_camera_normalized(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(
            narration="Test",
            visual=VisualScene(camera_pattern="zoom_in")
        )
class TestExplicitMotionPreservation:
    """Explicit motion types in input are preserved when valid."""

    def test_explicit_motion_types_preserved(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(
            narration="Test",
            visual=VisualScene(
                scene_role="problem",
                motions=[Motion(type="fade", target="character", start_time=0, duration=1, parameters={"from": 1, "to": 0})]
            )
        )
        plan = planner.plan([scene])
        assert "fade" in plan.decisions[0].preferred_motion_types

    def test_duplicate_motions_deduplicated(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(
            narration="Test",
            visual=VisualScene(
                motions=[
                    Motion(type="fade", target="character", start_time=0, duration=1, parameters={"from": 1, "to": 0}),
                    Motion(type="fade", target="object", start_time=0.5, duration=1, parameters={"from": 1, "to": 0}),
                ]
            )
        )
        plan = planner.plan([scene])
        assert plan.decisions[0].preferred_motion_types.count("fade") == 1


class TestExplicitTransitionPreservation:
    """Explicit transitions in input are preserved when valid."""

    def test_explicit_transition_preserved(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(
            narration="Test",
            visual=VisualScene(transition=Transition(type="crossfade", duration=0.5))
        )
        plan = planner.plan([scene])
        assert plan.decisions[0].transition_type == "crossfade"


class TestSupportedVocabularyOnly:
    """Output only uses supported camera/motion/transition vocabulary."""

    def test_camera_pattern_in_supported_vocabulary(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [ScenePlan(narration=f"Scene {i}") for i in range(5)]
        plan = planner.plan(scenes)
        for decision in plan.decisions:
            assert decision.camera_pattern in SUPPORTED_CAMERA_PATTERNS

    def test_motion_types_in_supported_vocabulary(self) -> None:
        planner = VisualStoryPlanner()
class TestAdjacentRepetitionDetection:
    """Adjacent repeated treatments/cameras/motions/focus are flagged."""

    def test_repeated_treatment_flagged(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [
            ScenePlan(narration="Hook 1", visual=VisualScene(scene_role="hook")),
            ScenePlan(narration="Hook 2", visual=VisualScene(scene_role="hook")),
        ]
        plan = planner.plan(scenes)
        assert any("repeated treatment" in w.lower() for w in plan.decisions[1].warnings)
        assert plan.decisions[1].repeated_with_previous is True

    def test_repeated_camera_flagged(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [
            ScenePlan(narration="Scene 1", visual=VisualScene(camera_spec={"pattern": "static"})),
            ScenePlan(narration="Scene 2", visual=VisualScene(camera_spec={"pattern": "static"})),
        ]
        plan = planner.plan(scenes)
        assert any("repeated camera" in w.lower() for w in plan.decisions[1].warnings)

    def test_same_focus_target_flagged(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [
            ScenePlan(narration="Scene 1", visual=VisualScene(primary_focus="character")),
            ScenePlan(narration="Scene 2", visual=VisualScene(primary_focus="character")),
        ]
        plan = planner.plan(scenes)
        assert any("same focus target" in w.lower() for w in plan.decisions[1].warnings)


class TestSerializableToDict:
    """VisualStoryPlan and VisualStoryDecision have serializable to_dict()."""

    def test_decision_to_dict_returns_dict(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="Test")
        plan = planner.plan([scene])
        decision_dict = plan.decisions[0].to_dict()
        assert isinstance(decision_dict, dict)
        assert "scene_index" in decision_dict
        assert "beat_type" in decision_dict
        assert "treatment" in decision_dict
        assert "camera_pattern" in decision_dict
        assert "preferred_motion_types" in decision_dict
        assert "transition_type" in decision_dict
        assert "repeated_with_previous" in decision_dict
        assert "warnings" in decision_dict

    def test_plan_to_dict_returns_dict(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [ScenePlan(narration="Test") for _ in range(3)]
        plan = planner.plan(scenes)
        plan_dict = plan.to_dict()
        assert isinstance(plan_dict, dict)
        assert "decisions" in plan_dict
        assert "warnings" in plan_dict
        assert len(plan_dict["decisions"]) == 3

    def test_to_dict_output_json_serializable(self) -> None:
        import json
        planner = VisualStoryPlanner()
        scenes = [ScenePlan(narration="Test", visual=VisualScene(scene_role="hook"))]
        plan = planner.plan(scenes)
        json_str = json.dumps(plan.to_dict())
        assert isinstance(json_str, str)


class TestImmutableDecisionObjects:
    """VisualStoryDecision and VisualStoryPlan are frozen/immutable."""

    def test_decision_is_frozen(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="Test")
        plan = planner.plan([scene])
        decision = plan.decisions[0]

        try:
            decision.scene_index = 999
            assert False, "Expected FrozenInstanceError"
        except Exception as e:
            assert "frozen" in str(type(e)).lower() or "frozen" in str(e).lower()

    def test_plan_is_frozen(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="Test")
        plan = planner.plan([scene])

        try:
            plan.decisions = ()
            assert False, "Expected FrozenInstanceError"
        except Exception as e:
            assert "frozen" in str(type(e)).lower() or "frozen" in str(e).lower()

    def test_warnings_tuple_immutable(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="Test")
        plan = planner.plan([scene])
        decision = plan.decisions[0]

        assert isinstance(decision.warnings, tuple)
        assert isinstance(plan.warnings, tuple)
        scenes = [ScenePlan(narration=f"Scene {i}") for i in range(5)]
        plan = planner.plan(scenes)
        for decision in plan.decisions:
            for motion in decision.preferred_motion_types:
                assert motion in SUPPORTED_MOTION_TYPES

    def test_transition_type_in_supported_vocabulary_or_none(self) -> None:
        planner = VisualStoryPlanner()
        scenes = [ScenePlan(narration=f"Scene {i}") for i in range(5)]
        plan = planner.plan(scenes)
        for decision in plan.decisions:
            if decision.transition_type is not None:
                assert decision.transition_type in SUPPORTED_TRANSITION_TYPES


class TestNoInventedFocusTargets:
    """Planner never invents focus targets; empty focus stays empty."""

    def test_empty_focus_remains_empty(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="Test", visual=VisualScene(primary_focus=""))
        plan = planner.plan([scene])
        assert plan.decisions[0].focus_target == ""

    def test_missing_focus_yields_empty_with_warning(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(narration="Test", visual=VisualScene())
        plan = planner.plan([scene])
        assert plan.decisions[0].focus_target == ""
        assert any("missing focus" in w.lower() for w in plan.decisions[0].warnings)

    def test_invalid_camera_falls_back_to_treatment_default(self) -> None:
        planner = VisualStoryPlanner()
        scene = ScenePlan(
            narration="Test",
            visual=VisualScene(camera_pattern="invalid_camera_xyz")
        )
        plan = planner.plan([scene])
        assert plan.decisions[0].camera_pattern in SUPPORTED_CAMERA_PATTERNS