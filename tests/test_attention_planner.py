"""Tests for AttentionPlanner (V1.4-E).

Comprehensive deterministic test suite for the attention continuity planning
service. Covers empty sequences, single scenes, multi-scene continuity,
primary/secondary target resolution, handoff states (retained / shifted /
returned / introduced / fallback), explicit focus preservation, integration
with V1.4-A/B/C/D outputs, no-target-invention, determinism, input
immutability, frozen output objects, JSON serialization, and vocabulary
conformance.

No renderer, FFmpeg, network, LLM, randomness, or pipeline execution is
required or exercised by any test in this module.
"""

from __future__ import annotations

import copy
import inspect
import json
import re
from dataclasses import FrozenInstanceError

import pytest

from src.pipeline.auto_publish_pipeline import ScenePlan, VisualScene
from src.services.attention_planner import (
    SUPPORTED_HANDOFF_STATES,
    SUPPORTED_TARGET_KINDS,
    AttentionDecision,
    AttentionPlan,
    AttentionPlanner,
)
from src.services.camera_planner import CameraDecision, CameraPlan
from src.services.composition_planner import CompositionDecision, CompositionPlan
from src.services.visual_diversity import (
    VisualDiversityDecision,
    VisualDiversityReport,
)
from src.services.visual_focus import VisualFocus
from src.services.visual_story_planner import (
    VisualStoryDecision,
    VisualStoryPlan,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_character(name: str = "hero") -> dict:
    """Create a simple character dict."""
    return {
        "name": name, "pose": "idle", "emotion": "neutral",
        "x": 0.5, "y": 0.5, "scale": 1.0, "color": "blue",
    }


def _make_object(name: str = "book", obj_type: str = "book") -> dict:
    """Create a simple object dict."""
    return {
        "name": name, "type": obj_type,
        "x": 0.5, "y": 0.5, "scale": 1.0, "rotation": 0, "opacity": 1.0,
    }


def _make_text(text: str = "Subscribe") -> dict:
    """Create a simple text element dict."""
    return {
        "text": text, "x": 0.5, "y": 0.9, "size": 24,
        "color": "white", "opacity": 1.0, "style": "bold",
        "fade_in": 0.2, "fade_out": 0.2,
    }


def _make_scene(
    narration: str = "Test",
    *,
    primary_focus: str | None = None,
    camera_spec: dict | None = None,
    characters: list[dict] | None = None,
    objects: list[dict] | None = None,
    text_elements: list[dict] | None = None,
    visual_prompt: str | None = None,
    no_visual: bool = False,
) -> ScenePlan:
    """Create a ScenePlan with optional visual configuration."""
    if no_visual:
        visual = VisualScene(camera_pattern="", primary_focus="")
        return ScenePlan(narration=narration, visual=visual)
    kwargs: dict = {}
    if primary_focus is not None:
        kwargs["primary_focus"] = primary_focus
    if camera_spec is not None:
        kwargs["camera_spec"] = camera_spec
    if characters is not None:
        kwargs["characters"] = characters
    if objects is not None:
        kwargs["objects"] = objects
    if text_elements is not None:
        kwargs["text_elements"] = text_elements
    if visual_prompt is not None:
        kwargs["visual_prompt"] = visual_prompt
    visual = VisualScene(**kwargs)
    return ScenePlan(narration=narration, visual=visual)


def _make_story_plan(
    treatments: list[str],
    *,
    focus_targets: list[str] | None = None,
    beat_types: list[str] | None = None,
) -> VisualStoryPlan:
    """Create a VisualStoryPlan with the given per-scene treatments."""
    decisions = tuple(
        VisualStoryDecision(
            scene_index=i,
            beat_type=(beat_types[i] if beat_types else "HOOK"),
            focus_target=(focus_targets[i] if focus_targets else ""),
            treatment=treatment,
            camera_pattern="static",
            preferred_motion_types=("fade",),
            transition_type=None,
            repeated_with_previous=False,
            warnings=(),
        )
        for i, treatment in enumerate(treatments)
    )
    return VisualStoryPlan(decisions=decisions, warnings=())


def _make_diversity_report(
    repeated_focus: list[bool] | None = None,
    repeated_prev: list[bool] | None = None,
) -> VisualDiversityReport:
    """Create a VisualDiversityReport with per-scene repetition flags."""
    n = max(len(repeated_focus or []), len(repeated_prev or []))
    decisions = tuple(
        VisualDiversityDecision(
            scene_index=i,
            repeated_with_previous=(
                repeated_prev[i] if repeated_prev and i < len(repeated_prev) else False
            ),
            repeated_camera=False,
            repeated_motion=False,
            repeated_treatment=False,
            repeated_focus_pattern=(
                repeated_focus[i] if repeated_focus and i < len(repeated_focus) else False
            ),
            warnings=(),
            camera_recommendations=(),
            motion_recommendations=(),
            treatment_recommendations=(),
        )
        for i in range(n)
    )
    return VisualDiversityReport(decisions=decisions, warnings=())

def _make_composition_plan(comp_types: list[str]) -> CompositionPlan:
    """Create a CompositionPlan with the given per-scene composition types."""
    decisions = tuple(
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
        for i, comp_type in enumerate(comp_types)
    )
    return CompositionPlan(decisions=decisions, warnings=())


def _make_camera_plan(
    focus_targets: list[str | None],
    patterns: list[str] | None = None,
) -> CameraPlan:
    """Create a CameraPlan with the given per-scene focus targets."""
    decisions = tuple(
        CameraDecision(
            scene_index=i,
            recommended_pattern=(patterns[i] if patterns else "static"),
            focus_target=(
                focus_targets[i] if focus_targets and i < len(focus_targets) else None
            ),
            continuity_from_previous="established",
            repeated_with_previous=False,
            explicit_camera_preserved=False,
            warnings=(),
        )
        for i in range(len(focus_targets))
    )
    return CameraPlan(decisions=decisions, warnings=())

# ---------------------------------------------------------------------------
# Empty and single-scene sequences
# ---------------------------------------------------------------------------


class TestEmptySequence:
    """An empty scene sequence yields an empty, serializable plan."""

    def test_empty_sequence_yields_empty_plan(self) -> None:
        plan = AttentionPlanner().plan([])
        assert plan.decisions == ()
        assert plan.warnings == ()
        assert plan.to_dict() == {"decisions": [], "warnings": []}

    def test_empty_sequence_is_deterministic(self) -> None:
        planner = AttentionPlanner()
        assert planner.plan([]).to_dict() == planner.plan([]).to_dict()


class TestSingleScene:
    """A single scene establishes attention with no previous handoff."""

    def test_single_scene_establishes_attention(self) -> None:
        plan = AttentionPlanner().plan(
            [_make_scene(characters=[_make_character("hero")])]
        )
        assert len(plan.decisions) == 1
        decision = plan.decisions[0]
        assert decision.scene_index == 0
        assert decision.primary_target == "hero"
        assert decision.target_kind == "character"
        assert decision.handoff_from_previous == "established"
        assert decision.handoff_to_next == "established"  # no next scene
        assert decision.retained_from_previous is False
        assert decision.target_changed is False
        assert decision.explicit_focus_preserved is False
        assert decision.warnings == ()

    def test_single_scene_with_no_targetable_elements(self) -> None:
        plan = AttentionPlanner().plan([_make_scene()])  # default: no intent
        decision = plan.decisions[0]
        assert decision.primary_target is None
        assert decision.target_kind is None
        assert decision.handoff_from_previous == "fallback"
        assert "no_target_found" in decision.warnings

    def test_no_visual_scene_is_safe(self) -> None:
        plan = AttentionPlanner().plan([_make_scene(no_visual=True)])
        decision = plan.decisions[0]
        assert decision.primary_target is None
        assert decision.handoff_from_previous == "fallback"

    def test_scene_level_fallback_when_intent_but_no_subjects(self) -> None:
        plan = AttentionPlanner().plan([_make_scene(visual_prompt="abstract motion")])
        decision = plan.decisions[0]
        assert decision.primary_target == "scene"
        assert decision.target_kind == "scene"
        assert "scene_level_fallback" in decision.warnings

# ---------------------------------------------------------------------------
# Multi-scene attention continuity
# ---------------------------------------------------------------------------


class TestMultiSceneContinuity:
    """Handoff tracking across adjacent scenes."""

    def test_ordering_preserved(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
            _make_scene("C", text_elements=[_make_text("Subscribe")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        assert [d.scene_index for d in plan.decisions] == [0, 1, 2]

    def test_character_to_character_retained(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", characters=[_make_character("hero")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        first, second = plan.decisions
        assert second.handoff_from_previous == "retained"
        assert second.retained_from_previous is True
        assert second.target_changed is False
        assert "repeated_attention:hero" in second.warnings
        assert first.handoff_to_next == "retained"

    def test_character_to_object_shifted(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        first, second = plan.decisions
        assert second.handoff_from_previous == "shifted"
        assert second.primary_target == "book"
        assert second.retained_from_previous is False
        assert second.target_changed is True
        assert first.handoff_to_next == "shifted"

    def test_object_to_character_shifted(self) -> None:
        scenes = [
            _make_scene("A", objects=[_make_object("book")]),
            _make_scene("B", characters=[_make_character("hero")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        second = plan.decisions[1]
        assert second.handoff_from_previous == "shifted"
        assert second.primary_target == "hero"
        assert second.target_changed is True

    def test_attention_return_detection(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
            _make_scene("C", characters=[_make_character("hero")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        third = plan.decisions[2]
        assert third.handoff_from_previous == "returned"
        assert third.primary_target == "hero"
        assert third.target_changed is True
        assert third.retained_from_previous is False
        assert third.warnings == ("attention_returned:hero",)
        assert plan.decisions[1].handoff_to_next == "returned"

    def test_attention_introduced_after_empty_scene(self) -> None:
        scenes = [
            _make_scene("A"),  # no target
            _make_scene("B", characters=[_make_character("hero")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        assert plan.decisions[0].handoff_from_previous == "fallback"
        assert plan.decisions[1].handoff_from_previous == "introduced"

    def test_handoff_to_next_mirrors_next_handoff(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
            _make_scene("C", characters=[_make_character("hero")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        assert (
            plan.decisions[0].handoff_to_next
            == plan.decisions[1].handoff_from_previous
        )
        assert (
            plan.decisions[1].handoff_to_next
            == plan.decisions[2].handoff_from_previous
        )
        # Final scene has no next transition (deterministic placeholder).
        assert plan.decisions[2].handoff_to_next == "established"

    def test_extended_attention_run_and_low_diversity(self) -> None:
        scenes = [
            _make_scene(str(i), characters=[_make_character("hero")])
            for i in range(4)
        ]
        plan = AttentionPlanner().plan(scenes)
        assert plan.warnings == ("low_attention_diversity",)
        assert "repeated_attention:hero" in plan.decisions[1].warnings
        assert "extended_attention_run:hero:3" in plan.decisions[2].warnings
        assert "extended_attention_run:hero:4" in plan.decisions[3].warnings
        assert all(d.primary_target == "hero" for d in plan.decisions)

    def test_two_scenes_no_sequence_diversity_warning(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        assert plan.warnings == ()

    def test_three_distinct_targets_no_sequence_warning(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
            _make_scene("C", text_elements=[_make_text("Subscribe")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        assert plan.warnings == ()

# ---------------------------------------------------------------------------
# Primary target resolution precedence
# ---------------------------------------------------------------------------


class TestPrimaryTargetResolution:
    """Primary target follows the documented strict precedence."""

    def test_explicit_character_focus_wins(self) -> None:
        scene = _make_scene(
            primary_focus="hero",
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "hero"
        assert decision.target_kind == "character"
        assert decision.explicit_focus_preserved is True
        assert "explicit_focus_preserved" in decision.warnings

    def test_visual_focus_result_used_before_subject_ordering(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book"), _make_object("chart", obj_type="diagram")],
        )
        focus = VisualFocus(primary="book", secondary="chart")
        plan = AttentionPlanner().plan([scene], focus_results={0: focus})
        decision = plan.decisions[0]
        assert decision.primary_target == "book"  # not the ordering default
        assert decision.target_kind == "object"

    def test_camera_focus_target_used(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan([scene], camera_plan=_make_camera_plan(["book"]))
        assert plan.decisions[0].primary_target == "book"

    def test_camera_scene_target_is_not_an_element(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        plan = AttentionPlanner().plan(
            [scene], camera_plan=_make_camera_plan(["scene"])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_composition_object_led_prefers_object(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["object_led"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "book"
        assert decision.target_kind == "object"

    def test_composition_text_led_prefers_text(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            text_elements=[_make_text("Subscribe")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["text_led"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "Subscribe"
        assert decision.target_kind == "text"

    def test_treatment_cta_prefers_text_over_character(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            text_elements=[_make_text("Subscribe")],
        )
        plan = AttentionPlanner().plan([scene], story_plan=_make_story_plan(["cta"]))
        decision = plan.decisions[0]
        assert decision.primary_target == "Subscribe"
        assert decision.target_kind == "text"

    def test_subject_ordering_defaults_to_first_character(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "hero"
        assert decision.target_kind == "character"

    def test_subject_ordering_object_when_no_character(self) -> None:
        scene = _make_scene(objects=[_make_object("book")])
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "book"
        assert decision.target_kind == "object"

    def test_subject_ordering_text_when_no_named_elements(self) -> None:
        scene = _make_scene(text_elements=[_make_text("Subscribe")])
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "Subscribe"
        assert decision.target_kind == "text"

    def test_default_scene_focus_is_not_explicit_intent(self) -> None:
        scene = _make_scene(primary_focus="scene", characters=[_make_character("hero")])
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "hero"
        assert decision.explicit_focus_preserved is False
        assert not any(w.startswith("explicit_focus") for w in decision.warnings)

    def test_resolution_precedence_explicit_over_all_planners(self) -> None:
        scene = _make_scene(
            primary_focus="book",
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
            text_elements=[_make_text("Subscribe")],
        )
        plan = AttentionPlanner().plan(
            [scene],
            story_plan=_make_story_plan(["cta"]),
            diversity_report=_make_diversity_report(repeated_focus=[True]),
            composition_plan=_make_composition_plan(["text_led"]),
            camera_plan=_make_camera_plan(["hero"]),
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "book"
        assert decision.explicit_focus_preserved is True
        assert decision.warnings == ("explicit_focus_preserved",)

# ---------------------------------------------------------------------------
# Secondary target resolution
# ---------------------------------------------------------------------------


class TestSecondaryTargetResolution:
    """Secondary targets exist only when scene data legitimately supports one."""

    def test_comparison_two_characters_dual_targets(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero"), _make_character("sidekick")]
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["comparison"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.secondary_target == "sidekick"
        assert "comparison_dual_targets" in decision.warnings

    def test_subject_support_character_with_object(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["subject_support"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.secondary_target == "book"
        assert "comparison_dual_targets" in decision.warnings

    def test_comparison_single_subject_has_no_secondary(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["comparison"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.secondary_target is None
        assert "comparison_dual_targets" not in decision.warnings

    def test_secondary_from_focus_result(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book"), _make_object("chart", obj_type="diagram")],
        )
        focus = VisualFocus(primary="book", secondary="chart")
        plan = AttentionPlanner().plan([scene], focus_results={0: focus})
        decision = plan.decisions[0]
        assert decision.primary_target == "book"
        assert decision.secondary_target == "chart"

    def test_secondary_never_equals_primary(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero"), _make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["comparison"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.secondary_target == "book"

    def test_no_secondary_without_supporting_data(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.secondary_target is None

    def test_invalid_focus_secondary_not_invented(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        focus = VisualFocus(primary="hero", secondary="ghost")
        plan = AttentionPlanner().plan([scene], focus_results={0: focus})
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.secondary_target is None

# ---------------------------------------------------------------------------
# Explicit focus preservation
# ---------------------------------------------------------------------------


class TestExplicitFocusPreservation:
    """Explicit scene focus intent is always preserved, never replaced."""

    def test_explicit_focus_survives_consecutive_scenes(self) -> None:
        scenes = [
            _make_scene("A", primary_focus="hero", characters=[_make_character("hero")]),
            _make_scene("B", primary_focus="hero", characters=[_make_character("hero")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        first, second = plan.decisions
        assert first.primary_target == "hero"
        assert first.explicit_focus_preserved is True
        assert first.warnings == ("explicit_focus_preserved",)
        assert second.primary_target == "hero"
        assert second.explicit_focus_preserved is True
        assert "explicit_focus_repetition" in second.warnings

    def test_explicit_camera_spec_focus_is_respected(self) -> None:
        scene = _make_scene(
            camera_spec={"pattern": "zoom_in", "focus_target": "book"},
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "book"
        assert decision.explicit_focus_preserved is True

    def test_unresolvable_explicit_focus_does_not_invent(self) -> None:
        scene = _make_scene(
            primary_focus="ghost",
            characters=[_make_character("hero")],
        )
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "hero"  # real element, no invention
        assert decision.explicit_focus_preserved is False
        assert "explicit_focus_unresolved" in decision.warnings

    def test_unresolvable_explicit_focus_on_empty_scene(self) -> None:
        scene = _make_scene(primary_focus="ghost")
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target is None
        assert "no_target_found" in decision.warnings
        assert "explicit_focus_unresolved" in decision.warnings

# ---------------------------------------------------------------------------
# Story treatment awareness (V1.4-A)
# ---------------------------------------------------------------------------


class TestTreatmentAwareness:
    """Every V1.4-A treatment maps to a deterministic target preference."""

    def test_establish_prefers_first_character(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            text_elements=[_make_text("Subscribe")],
        )
        plan = AttentionPlanner().plan(
            [scene], story_plan=_make_story_plan(["establish"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.target_kind == "character"

    def test_problem_focus_prefers_character(self) -> None:
        scene = _make_scene(
            objects=[_make_object("book")],
            characters=[_make_character("hero")],
        )
        plan = AttentionPlanner().plan(
            [scene], story_plan=_make_story_plan(["problem_focus"])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_compare_prefers_character_without_forcing_secondary(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero"), _make_character("sidekick")]
        )
        plan = AttentionPlanner().plan([scene], story_plan=_make_story_plan(["compare"]))
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        # Secondary pairs come from composition/focus data, not treatments.
        assert decision.secondary_target is None

    def test_explain_prefers_object(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan([scene], story_plan=_make_story_plan(["explain"]))
        assert plan.decisions[0].primary_target == "book"

    def test_proof_prefers_object(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("chart", obj_type="diagram")],
        )
        plan = AttentionPlanner().plan([scene], story_plan=_make_story_plan(["proof"]))
        assert plan.decisions[0].primary_target == "chart"

    def test_proof_prefers_text_when_no_object(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            text_elements=[_make_text("97% accuracy")],
        )
        plan = AttentionPlanner().plan([scene], story_plan=_make_story_plan(["proof"]))
        assert plan.decisions[0].primary_target == "97% accuracy"

    def test_solution_growth_prefers_object(self) -> None:
        scene = _make_scene(
            objects=[_make_object("book")],
            characters=[_make_character("hero")],
        )
        plan = AttentionPlanner().plan(
            [scene], story_plan=_make_story_plan(["solution_growth"])
        )
        assert plan.decisions[0].primary_target == "book"

    def test_cta_prefers_text(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            text_elements=[_make_text("Subscribe")],
        )
        plan = AttentionPlanner().plan([scene], story_plan=_make_story_plan(["cta"]))
        assert plan.decisions[0].primary_target == "Subscribe"

    def test_unavailable_preference_falls_back_to_ordering(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])  # no object/text
        plan = AttentionPlanner().plan([scene], story_plan=_make_story_plan(["cta"]))
        assert plan.decisions[0].primary_target == "hero"

    def test_story_focus_hint_applies_without_kind_preference(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene],
            story_plan=_make_story_plan(["custom_unknown"], focus_targets=["book"]),
        )
        assert plan.decisions[0].primary_target == "book"

# ---------------------------------------------------------------------------
# Composition awareness (V1.4-C)
# ---------------------------------------------------------------------------


class TestCompositionAwareness:
    """Composition types steer attention toward the composed subject."""

    def test_single_subject_uses_primary_subject(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["single_subject"])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_problem_focus_prefers_character(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["problem_focus"])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_solution_result_prefers_object(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("chart", obj_type="diagram")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["solution_result"])
        )
        assert plan.decisions[0].primary_target == "chart"

    def test_unknown_composition_falls_through_to_ordering(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], composition_plan=_make_composition_plan(["mystery_style"])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_no_composition_plan_uses_ordering(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target == "hero"

# ---------------------------------------------------------------------------
# Camera awareness (V1.4-D)
# ---------------------------------------------------------------------------


class TestCameraAwareness:
    """Camera focus intent is honored but stays subordinate to scene focus."""

    def test_focus_on_character_resolves_character(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene],
            camera_plan=_make_camera_plan(["hero"], patterns=["focus_on_character"]),
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.target_kind == "character"

    def test_focus_on_object_resolves_object(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene],
            camera_plan=_make_camera_plan(["book"], patterns=["focus_on_object"]),
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "book"
        assert decision.target_kind == "object"

    def test_named_camera_target_is_honored_regardless_of_pattern(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], camera_plan=_make_camera_plan(["book"], patterns=["pan_right"])
        )
        assert plan.decisions[0].primary_target == "book"

    def test_invalid_camera_target_not_invented(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        plan = AttentionPlanner().plan(
            [scene], camera_plan=_make_camera_plan(["ghost"])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_missing_camera_target_falls_through(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        plan = AttentionPlanner().plan(
            [scene], camera_plan=_make_camera_plan([None])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_scene_level_camera_target_is_not_an_element(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        plan = AttentionPlanner().plan(
            [scene], camera_plan=_make_camera_plan(["scene"])
        )
        assert plan.decisions[0].primary_target == "hero"

    def test_explicit_scene_focus_beats_camera_target(self) -> None:
        scene = _make_scene(
            primary_focus="hero",
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        plan = AttentionPlanner().plan(
            [scene], camera_plan=_make_camera_plan(["book"])
        )
        decision = plan.decisions[0]
        assert decision.primary_target == "hero"
        assert decision.explicit_focus_preserved is True

    def test_diversity_signal_does_not_block_camera_resolution(self) -> None:
        scene = _make_scene(
            characters=[_make_character("hero")],
            objects=[_make_object("book")],
        )
        report = _make_diversity_report(repeated_focus=[True], repeated_prev=[True])
        plan = AttentionPlanner().plan(
            [scene],
            diversity_report=report,
            camera_plan=_make_camera_plan(["book"]),
        )
        # No run exists yet, so no recommendation - but resolution proceeds.
        decision = plan.decisions[0]
        assert decision.primary_target == "book"
        assert decision.warnings == ()

# ---------------------------------------------------------------------------
# Diversity diagnostics (V1.4-B)
# ---------------------------------------------------------------------------


class TestDiversityAwareness:
    """V1.4-B repetition flags produce diagnostics, never forced changes."""

    def test_no_diversity_report_still_reports_repetition(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", characters=[_make_character("hero")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        assert plan.decisions[1].warnings == ("repeated_attention:hero",)

    def test_diversity_confirms_repetition_diagnostic(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", characters=[_make_character("hero")]),
        ]
        report = _make_diversity_report(repeated_focus=[False, True])
        plan = AttentionPlanner().plan(scenes, diversity_report=report)
        decision = plan.decisions[1]
        assert decision.primary_target == "hero"  # never forced
        assert "diversity_confirms_focus_repetition" in decision.warnings

    def test_diversity_recommendation_full_path(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", characters=[_make_character("hero")]),
            _make_scene(
                "C",
                characters=[_make_character("hero"), _make_character("sidekick")],
            ),
        ]
        report = _make_diversity_report(
            repeated_focus=[False, True, True],
            repeated_prev=[False, True, True],
        )
        composition = _make_composition_plan(
            ["single_subject", "single_subject", "comparison"]
        )
        plan = AttentionPlanner().plan(
            scenes, diversity_report=report, composition_plan=composition
        )
        third = plan.decisions[2]
        assert third.primary_target == "hero"
        assert third.secondary_target == "sidekick"
        assert third.warnings == (
            "repeated_attention:hero",
            "extended_attention_run:hero:3",
            "comparison_dual_targets",
            "attention_diversity_recommendation:sidekick",
            "diversity_confirms_focus_repetition",
        )

    def test_diversity_index_mismatch_is_safe(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        report = _make_diversity_report(repeated_focus=[True, True, True])
        plan = AttentionPlanner().plan([scene], diversity_report=report)
        assert plan.decisions[0].primary_target == "hero"

    def test_attention_is_never_forced_to_change(self) -> None:
        scenes = [
            _make_scene(str(i), characters=[_make_character("hero")])
            for i in range(4)
        ]
        report = _make_diversity_report(
            repeated_focus=[False, True, True, True],
            repeated_prev=[False, True, True, True],
        )
        plan = AttentionPlanner().plan(scenes, diversity_report=report)
        assert all(d.primary_target == "hero" for d in plan.decisions)
        assert [d.target_changed for d in plan.decisions] == [
            False, False, False, False,
        ]
        assert [d.retained_from_previous for d in plan.decisions] == [
            False, True, True, True,
        ]
        # Narrative correctness wins: only diagnostics, no target switches.
        assert not any(
            w.startswith("attention_diversity_recommendation")
            for d in plan.decisions
            for w in d.warnings
        )

# ---------------------------------------------------------------------------
# No target invention
# ---------------------------------------------------------------------------


class TestNoTargetInvention:
    """Every returned target must exist in the supplied scene."""

    def test_bogus_explicit_focus_never_becomes_target(self) -> None:
        scene = _make_scene(
            primary_focus="character_99",
            characters=[_make_character("hero")],
        )
        decision = AttentionPlanner().plan([scene]).decisions[0]
        assert decision.primary_target in {None, "hero", "scene"}

    def test_bogus_planner_targets_never_become_targets(self) -> None:
        scene = _make_scene(characters=[_make_character("hero")])
        plan = AttentionPlanner().plan(
            [scene],
            story_plan=_make_story_plan(["custom_unknown"], focus_targets=["object_x"]),
            camera_plan=_make_camera_plan(["unknown_subject"]),
        )
        decision = plan.decisions[0]
        assert decision.primary_target in {None, "hero", "scene"}
        assert decision.secondary_target is None

    def test_all_returned_targets_exist_in_scene(self) -> None:
        scenes = [
            _make_scene(
                "A",
                primary_focus="hero",
                characters=[_make_character("hero")],
                objects=[_make_object("book")],
            ),
            _make_scene("B", objects=[_make_object("book")]),
            _make_scene("C", text_elements=[_make_text("Subscribe")]),
            _make_scene("D", visual_prompt="ambient"),
        ]
        plan = AttentionPlanner().plan(
            scenes,
            story_plan=_make_story_plan(
                ["establish", "explain", "cta", "custom_unknown"],
                focus_targets=["hero", "ghost", "Subscribe", "object_x"],
            ),
            composition_plan=_make_composition_plan(
                ["single_subject", "object_led", "text_led", "single_subject"]
            ),
            camera_plan=_make_camera_plan(["hero", "book", "Subscribe", None]),
        )
        for decision in plan.decisions:
            scene = scenes[decision.scene_index]
            visual = scene.visual
            assert visual is not None
            valid = {"scene"}
            valid |= {c["name"] for c in visual.characters}
            valid |= {o["name"] for o in visual.objects}
            valid |= {t["text"] for t in visual.text_elements}
            if decision.primary_target is not None:
                assert decision.primary_target in valid
            if decision.secondary_target is not None:
                assert decision.secondary_target in valid


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Identical inputs produce identical serialized plans."""

    def test_identical_inputs_identical_outputs(self) -> None:
        def build() -> tuple[list[ScenePlan], VisualStoryPlan, CameraPlan]:
            scenes = [
                _make_scene("A", characters=[_make_character("hero")]),
                _make_scene("B", objects=[_make_object("book")]),
                _make_scene(
                    "C",
                    characters=[_make_character("hero"), _make_character("sidekick")],
                ),
            ]
            return (
                scenes,
                _make_story_plan(["establish", "explain", "compare"]),
                _make_camera_plan(["hero", "book", "hero"]),
            )

        scenes_a, story_a, camera_a = build()
        scenes_b, story_b, camera_b = build()
        plan_a = AttentionPlanner().plan(
            scenes_a, story_plan=story_a, camera_plan=camera_a
        )
        plan_b = AttentionPlanner().plan(
            scenes_b, story_plan=story_b, camera_plan=camera_b
        )
        assert plan_a.to_dict() == plan_b.to_dict()

    def test_repeated_calls_on_same_planner_are_stable(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
        ]
        planner = AttentionPlanner()
        assert planner.plan(scenes).to_dict() == planner.plan(scenes).to_dict()


# ---------------------------------------------------------------------------
# No mutation of inputs
# ---------------------------------------------------------------------------


class TestNoMutation:
    """Planning never mutates scenes or supplied plans."""

    def test_scenes_unchanged_after_planning(self) -> None:
        scenes = [
            _make_scene(
                "A",
                primary_focus="hero",
                characters=[_make_character("hero")],
                objects=[_make_object("book")],
                text_elements=[_make_text("Subscribe")],
            ),
            _make_scene(
                "B",
                camera_spec={"pattern": "zoom_in", "focus_target": "book"},
                characters=[_make_character("hero")],
            ),
        ]
        snapshot = copy.deepcopy(scenes)
        AttentionPlanner().plan(scenes)
        assert scenes == snapshot

    def test_v14_inputs_unchanged_after_planning(self) -> None:
        scenes = [_make_scene("A", characters=[_make_character("hero")])]
        story = _make_story_plan(["establish"], focus_targets=["hero"])
        diversity = _make_diversity_report(repeated_focus=[True])
        composition = _make_composition_plan(["single_subject"])
        camera = _make_camera_plan(["hero"])
        snapshots = (
            copy.deepcopy(story.to_dict()),
            copy.deepcopy(diversity.to_dict()),
            copy.deepcopy(composition.to_dict()),
            copy.deepcopy(camera.to_dict()),
        )
        AttentionPlanner().plan(
            scenes,
            story_plan=story,
            diversity_report=diversity,
            composition_plan=composition,
            camera_plan=camera,
        )
        assert story.to_dict() == snapshots[0]
        assert diversity.to_dict() == snapshots[1]
        assert composition.to_dict() == snapshots[2]
        assert camera.to_dict() == snapshots[3]


# ---------------------------------------------------------------------------
# Frozen / immutable outputs
# ---------------------------------------------------------------------------


class TestFrozenOutputs:
    """AttentionDecision and AttentionPlan are immutable."""

    def test_decision_is_frozen(self) -> None:
        decision = AttentionPlanner().plan(
            [_make_scene(characters=[_make_character("hero")])]
        ).decisions[0]
        with pytest.raises(FrozenInstanceError):
            decision.primary_target = "sidekick"  # type: ignore[misc]

    def test_plan_is_frozen(self) -> None:
        plan = AttentionPlanner().plan(
            [_make_scene(characters=[_make_character("hero")])]
        )
        with pytest.raises(FrozenInstanceError):
            plan.warnings = ()  # type: ignore[misc]

    def test_decisions_container_is_a_tuple(self) -> None:
        plan = AttentionPlanner().plan(
            [
                _make_scene("A", characters=[_make_character("hero")]),
                _make_scene("B", objects=[_make_object("book")]),
            ]
        )
        assert isinstance(plan.decisions, tuple)
        assert all(isinstance(d, AttentionDecision) for d in plan.decisions)


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """to_dict() produces JSON-serializable structures."""

    def test_to_dict_structure(self) -> None:
        plan = AttentionPlanner().plan(
            [_make_scene(characters=[_make_character("hero")])]
        )
        data = plan.to_dict()
        assert set(data.keys()) == {"decisions", "warnings"}
        assert len(data["decisions"]) == 1
        decision = data["decisions"][0]
        for key in (
            "scene_index",
            "primary_target",
            "secondary_target",
            "target_kind",
            "handoff_from_previous",
            "handoff_to_next",
            "retained_from_previous",
            "target_changed",
            "explicit_focus_preserved",
            "warnings",
        ):
            assert key in decision

    def test_to_dict_round_trips_through_json(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", objects=[_make_object("book")]),
        ]
        plan = AttentionPlanner().plan(
            scenes, story_plan=_make_story_plan(["establish", "explain"])
        )
        encoded = json.dumps(plan.to_dict())
        assert json.loads(encoded) == json.loads(json.dumps(plan.to_dict()))


# ---------------------------------------------------------------------------
# Supported vocabulary
# ---------------------------------------------------------------------------


class TestVocabulary:
    """Only supported handoff states and target kinds are ever emitted."""

    def test_handoff_states_within_vocabulary(self) -> None:
        scenes = [
            _make_scene("A", characters=[_make_character("hero")]),
            _make_scene("B", characters=[_make_character("hero")]),
            _make_scene("C", objects=[_make_object("book")]),
            _make_scene("D", characters=[_make_character("hero")]),
            _make_scene("E"),
            _make_scene("F", text_elements=[_make_text("Subscribe")]),
        ]
        plan = AttentionPlanner().plan(scenes)
        for decision in plan.decisions:
            assert decision.handoff_from_previous in SUPPORTED_HANDOFF_STATES
            assert decision.handoff_to_next in SUPPORTED_HANDOFF_STATES
            if decision.target_kind is not None:
                assert decision.target_kind in SUPPORTED_TARGET_KINDS

    def test_vocabulary_sets_are_frozen_finite(self) -> None:
        assert SUPPORTED_HANDOFF_STATES == {
            "established",
            "retained",
            "shifted",
            "introduced",
            "returned",
            "lost",
            "fallback",
        }
        assert SUPPORTED_TARGET_KINDS == {"character", "object", "text", "scene"}


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


class TestForbiddenImports:
    """The planner imports no renderer/network/LLM/randomness machinery."""

    def test_no_renderer_network_llm_random_time_uuid_imports(self) -> None:
        import src.services.attention_planner as module

        source = inspect.getsource(module)
        import_targets: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            match = re.match(r"(?:from|import)\s+([A-Za-z_][\w.]*)", stripped)
            if match:
                import_targets.append(match.group(1).split(".")[0])
        forbidden = {
            "random", "time", "uuid", "requests", "openai", "anthropic",
            "ollama", "ffmpeg", "socket", "http", "subprocess",
            "stickman_renderer", "video_assembler",
        }
        assert not (set(import_targets) & forbidden)
