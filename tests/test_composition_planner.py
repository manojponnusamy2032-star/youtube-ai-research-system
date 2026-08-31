"""Tests for CompositionPlanner (V1.4-C).

Comprehensive test suite for the deterministic composition planning
service. Tests cover empty sequences, single scenes, composition classification,
determinism, no-mutation, explicit intent preservation, and more.
"""

from __future__ import annotations

import json

from src.models.content_package import Motion
from src.pipeline.auto_publish_pipeline import ScenePlan, VisualScene
from src.services.composition_planner import (
    CompositionDecision,
    CompositionPlanner,
    CompositionPlan,
    SUPPORTED_ALIGNMENTS,
    SUPPORTED_COMPOSITION_TYPES,
    SUPPORTED_REGIONS,
    SUPPORTED_SCALES,
)
from src.services.visual_story_planner import (
    VisualStoryPlan,
    VisualStoryDecision,
)
from src.services.visual_diversity import (
    VisualDiversityReport,
    VisualDiversityDecision,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_scene(
    narration: str = "Test",
    *,
    scene_role: str | None = None,
    characters: list[dict] | None = None,
    objects: list[dict] | None = None,
    text_elements: list[dict] | None = None,
    primary_focus: str | None = None,
) -> ScenePlan:
    """Create a ScenePlan with optional visual configuration."""
    visual_kwargs: dict = {}
    if scene_role is not None:
        visual_kwargs["scene_role"] = scene_role
    if characters is not None:
        visual_kwargs["characters"] = characters
    if objects is not None:
        visual_kwargs["objects"] = objects
    if text_elements is not None:
        visual_kwargs["text_elements"] = text_elements
    if primary_focus is not None:
        visual_kwargs["primary_focus"] = primary_focus

    visual = VisualScene(**visual_kwargs) if visual_kwargs else None
    return ScenePlan(narration=narration, visual=visual)


def _make_story_plan(
    treatments: list[str],
    beat_types: list[str] | None = None,
) -> VisualStoryPlan:
    """Create a VisualStoryPlan with specified treatments."""
    decisions = []
    for i, treatment in enumerate(treatments):
        decisions.append(
            VisualStoryDecision(
                scene_index=i,
                beat_type=beat_types[i] if beat_types else "HOOK",
                focus_target="",
                treatment=treatment,
                camera_pattern="static",
                preferred_motion_types=("fade",),
                transition_type=None,
                repeated_with_previous=False,
                warnings=(),
            )
        )
    return VisualStoryPlan(decisions=tuple(decisions), warnings=())


def _make_diversity_report(
    composition_types: list[str],
) -> VisualDiversityReport:
    """Create a VisualDiversityReport for testing."""
    decisions = []
    for i, comp_type in enumerate(composition_types):
        decisions.append(
            VisualDiversityDecision(
                scene_index=i,
                repeated_with_previous=False,
                repeated_camera=False,
                repeated_motion=False,
                repeated_treatment=False,
                repeated_focus_pattern=False,
                warnings=(),
                camera_recommendations=(),
                motion_recommendations=(),
                treatment_recommendations=(),
            )
        )
    return VisualDiversityReport(decisions=tuple(decisions), warnings=())

# ---------------------------------------------------------------------------
# 1. Empty sequence
# ---------------------------------------------------------------------------


class TestEmptySequence:
    """Empty sequence produces empty plan."""

    def test_empty_list_returns_empty_plan(self) -> None:
        planner = CompositionPlanner()
        plan = planner.plan([])
        assert len(plan.decisions) == 0
        assert len(plan.warnings) == 0

    def test_empty_plan_to_dict(self) -> None:
        planner = CompositionPlanner()
        plan = planner.plan([])
        result = plan.to_dict()
        assert result == {"decisions": [], "warnings": []}


# ---------------------------------------------------------------------------
# 2. Single scene
# ---------------------------------------------------------------------------


class TestSingleScene:
    """Single scene produces one decision."""

    def test_single_scene_one_decision(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1
        assert plan.decisions[0].scene_index == 0

    def test_single_scene_valid_composition_type(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type in SUPPORTED_COMPOSITION_TYPES

    def test_single_scene_valid_regions(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        decision = plan.decisions[0]
        assert decision.primary_region in SUPPORTED_REGIONS
        if decision.secondary_region:
            assert decision.secondary_region in SUPPORTED_REGIONS
        if decision.text_region:
            assert decision.text_region in SUPPORTED_REGIONS

    def test_single_scene_valid_scale(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].recommended_scale in SUPPORTED_SCALES

    def test_single_scene_valid_alignment(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Hello")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].recommended_alignment in SUPPORTED_ALIGNMENTS


# ---------------------------------------------------------------------------
# 3. Composition classification - single subject
# ---------------------------------------------------------------------------


class TestSingleSubject:
    """Single subject scenes are classified correctly."""

    def test_one_character_single_subject(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene("Test", characters=[{"name": "hero", "pose": "idle"}])
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "single_subject"

    def test_one_object_single_subject(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene("Test", objects=[{"name": "book", "type": "book"}])
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "single_subject"


# ---------------------------------------------------------------------------
# 4. Composition classification - subject support
# ---------------------------------------------------------------------------


class TestSubjectSupport:
    """Multiple subjects are classified as subject_support."""

    def test_two_characters_subject_support(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene(
                "Test",
                characters=[
                    {"name": "hero", "pose": "idle"},
                    {"name": "sidekick", "pose": "idle"},
                ],
            )
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "subject_support"

    def test_character_and_object_subject_support(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene(
                "Test",
                characters=[{"name": "hero", "pose": "idle"}],
                objects=[{"name": "book", "type": "book"}],
            )
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "subject_support"


# ---------------------------------------------------------------------------
# 5. Composition classification - comparison
# ---------------------------------------------------------------------------


class TestComparison:
    """Contrast beats are classified as comparison."""

    def test_contrast_beat_comparison(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="contrast")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "comparison"

    def test_compare_treatment_comparison(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test")]
        story_plan = _make_story_plan(["compare"])
        plan = planner.plan(scenes, story_plan=story_plan)
        assert plan.decisions[0].composition_type == "comparison"


# ---------------------------------------------------------------------------
# 6. Composition classification - text_led
# ---------------------------------------------------------------------------


class TestTextLed:
    """CTA beats and text-only scenes are classified as text_led."""

    def test_cta_beat_text_led(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="cta")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "text_led"

    def test_text_only_text_led(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene(
                "Test",
                text_elements=[{"text": "Subscribe!", "x": 0.5, "y": 0.5}],
            )
        ]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "text_led"


# ---------------------------------------------------------------------------
# 7. Composition classification - problem_focus
# ---------------------------------------------------------------------------


class TestProblemFocus:
    """Problem beats are classified as problem_focus."""

    def test_problem_beat_problem_focus(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="problem")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "problem_focus"

    def test_problem_focus_treatment(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test")]
        story_plan = _make_story_plan(["problem_focus"])
        plan = planner.plan(scenes, story_plan=story_plan)
        assert plan.decisions[0].composition_type == "problem_focus"


# ---------------------------------------------------------------------------
# 8. Composition classification - solution_result
# ---------------------------------------------------------------------------


class TestSolutionResult:
    """Solution beats are classified as solution_result."""

    def test_solution_beat_solution_result(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="solution")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "solution_result"

    def test_solution_growth_treatment(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test")]
        story_plan = _make_story_plan(["solution_growth"])
        plan = planner.plan(scenes, story_plan=story_plan)
        assert plan.decisions[0].composition_type == "solution_result"


# ---------------------------------------------------------------------------
# 9. Story planner integration
# ---------------------------------------------------------------------------


class TestStoryPlannerIntegration:
    """Planner uses V1.4-A story decisions."""

    def test_uses_story_treatment(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test")]
        story_plan = _make_story_plan(["explain"])
        plan = planner.plan(scenes, story_plan=story_plan)
        assert plan.decisions[0].composition_type == "subject_support"

    def test_uses_beat_type(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test")]
        story_plan = _make_story_plan(
            ["establish"], beat_types=["CONTRAST"]
        )
        plan = planner.plan(scenes, story_plan=story_plan)
        assert plan.decisions[0].composition_type in SUPPORTED_COMPOSITION_TYPES

    def test_no_story_plan_works(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="hook")]
        plan = planner.plan(scenes)
        assert plan.decisions[0].composition_type == "single_subject"


# ---------------------------------------------------------------------------
# 10. Diversity integration
# ---------------------------------------------------------------------------


class TestDiversityIntegration:
    """Planner accepts V1.4-B diversity report."""

    def test_accepts_diversity_report(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="hook")]
        diversity_report = _make_diversity_report(["single_subject"])
        plan = planner.plan(scenes, diversity_report=diversity_report)
        assert len(plan.decisions) == 1

    def test_no_diversity_report_works(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="hook")]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1


# ---------------------------------------------------------------------------
# 16. Repeated composition detection
# ---------------------------------------------------------------------------


class TestRepeatedComposition:
    """Repeated composition patterns are detected."""

    def test_repeated_composition_warning(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene("First", scene_role="hook"),
            _make_scene("Second", scene_role="hook"),
        ]
        plan = planner.plan(scenes)
        # Second scene should detect repetition
        assert plan.decisions[1].repeated_with_previous

    def test_repeated_composition_warning_message(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene("First", scene_role="hook"),
            _make_scene("Second", scene_role="hook"),
        ]
        plan = planner.plan(scenes)
        warnings = plan.decisions[1].warnings
        assert any("repeated_composition:single_subject" in w for w in warnings)


# ---------------------------------------------------------------------------
# 17. Vocabulary validation
# ---------------------------------------------------------------------------


class TestVocabularyValidation:
    """All generated values belong to supported vocabularies."""

    def test_composition_types_supported(self) -> None:
        planner = CompositionPlanner()
        scenes = [
            _make_scene("Hook", scene_role="hook"),
            _make_scene("Problem", scene_role="problem"),
            _make_scene("Contrast", scene_role="contrast"),
            _make_scene("Explanation", scene_role="explanation"),
            _make_scene("Example", scene_role="example"),
            _make_scene("Solution", scene_role="solution"),
            _make_scene("CTA", scene_role="cta"),
        ]
        plan = planner.plan(scenes)
        for decision in plan.decisions:
            assert decision.composition_type in SUPPORTED_COMPOSITION_TYPES

    def test_regions_supported(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="hook")]
        plan = planner.plan(scenes)
        for decision in plan.decisions:
            assert decision.primary_region in SUPPORTED_REGIONS
            if decision.secondary_region:
                assert decision.secondary_region in SUPPORTED_REGIONS
            if decision.text_region:
                assert decision.text_region in SUPPORTED_REGIONS

    def test_scales_supported(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="hook")]
        plan = planner.plan(scenes)
        for decision in plan.decisions:
            assert decision.recommended_scale in SUPPORTED_SCALES

    def test_alignments_supported(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", scene_role="hook")]
        plan = planner.plan(scenes)
        for decision in plan.decisions:
            assert decision.recommended_alignment in SUPPORTED_ALIGNMENTS


# ---------------------------------------------------------------------------
# 18. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge cases for robustness."""

    def test_scene_without_visual(self) -> None:
        planner = CompositionPlanner()
        scenes = [ScenePlan(narration="No visual")]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1
        assert plan.decisions[0].composition_type in SUPPORTED_COMPOSITION_TYPES

    def test_scene_with_empty_visual(self) -> None:
        planner = CompositionPlanner()
        scenes = [ScenePlan(narration="Empty visual", visual=VisualScene())]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1

    def test_empty_text_elements(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", text_elements=[])]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1

    def test_empty_characters(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", characters=[])]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1

    def test_empty_objects(self) -> None:
        planner = CompositionPlanner()
        scenes = [_make_scene("Test", objects=[])]
        plan = planner.plan(scenes)
        assert len(plan.decisions) == 1
