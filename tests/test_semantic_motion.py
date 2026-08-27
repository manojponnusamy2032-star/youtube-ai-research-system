from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from src.models.content_package import SUPPORTED_EASINGS, SUPPORTED_MOTION_TYPES
from src.services.scene_composition import SUPPORTED_EFFECTS, CharacterSpec, EffectSpec, ObjectSpec
from src.services.semantic_motion import (
    SUPPORTED_SEMANTIC_INTENTS,
    LoweredSemanticMotion,
    SemanticMotionLowerer,
    SemanticMotionSpec,
)
from src.services.visual_focus import VisualFocus


@pytest.fixture
def scene() -> dict[str, list[object]]:
    return {
        "characters": [CharacterSpec(name="student"), CharacterSpec(name="coach")],
        "objects": [ObjectSpec(name="desk"), ObjectSpec(name="clock")],
        "text": [{"text": "study longer"}, {"text": "memory"}],
    }


def lower(spec: SemanticMotionSpec, scene: dict[str, list[object]], **kwargs: object) -> LoweredSemanticMotion:
    return SemanticMotionLowerer().lower(spec, **scene, **kwargs)


def test_spec_creation_and_serialization() -> None:
    spec = SemanticMotionSpec(subject="student", intent="EMPHASIZE", start_time=2, duration=1.5)
    assert spec.intent == "emphasize"
    assert spec.to_dict() == {"subject": "student", "intent": "emphasize", "start_time": 2.0, "duration": 1.5, "parameters": {}}


@pytest.mark.parametrize("intent", sorted(SUPPORTED_SEMANTIC_INTENTS))
def test_supported_intent_is_accepted(intent: str, scene: dict[str, list[object]]) -> None:
    subject = "student"
    parameters: dict[str, object] = {}
    if intent in {"compare", "accumulate"}:
        subject = "student vs coach"
        parameters = {"subjects": ["student", "coach"]}
    if intent == "transform":
        parameters = {"from_subject": "student", "to_subject": "coach"}
    if intent == "point_to":
        parameters = {"from_to": {"from": {"x": 0.2, "y": 0.75}, "to": {"x": 0.6, "y": 0.75}}}
    result = lower(SemanticMotionSpec(subject=subject, intent=intent, parameters=parameters), scene)
    assert isinstance(result, LoweredSemanticMotion)
    assert result.motions or intent == "transition_attention"


def test_actual_lowering_shapes(scene: dict[str, list[object]]) -> None:
    assert [m.type for m in lower(SemanticMotionSpec("student", "emphasize"), scene).motions] == ["scale"]
    assert [m.type for m in lower(SemanticMotionSpec("student", "reveal"), scene).motions] == ["fade"]
    assert [m.type for m in lower(SemanticMotionSpec("student", "reveal_decline"), scene).motions] == ["fade", "scale"]
    assert [m.type for m in lower(SemanticMotionSpec("student", "emphasize_growth"), scene).motions] == ["scale"]
    assert [m.type for m in lower(SemanticMotionSpec("student vs coach", "compare", parameters={"subjects": ["student", "coach"]}), scene).motions] == ["enter", "enter"]
    assert [m.type for m in lower(SemanticMotionSpec("student", "transform", parameters={"from_subject": "student", "to_subject": "coach"}), scene).motions] == ["exit", "enter"]
    assert [m.type for m in lower(SemanticMotionSpec("student", "point_to", parameters={"from_to": {"from": {"x": 0, "y": 0}, "to": {"x": 1, "y": 1}}}), scene).motions] == ["move"]
    assert [m.type for m in lower(SemanticMotionSpec("student", "isolate"), scene).motions] == ["scale"]
    assert len(lower(SemanticMotionSpec("student vs coach", "accumulate", parameters={"subjects": ["student", "coach"]}), scene).motions) == 2
    assert [m.type for m in lower(SemanticMotionSpec("student", "remove"), scene).motions] == ["exit"]
    assert [m.type for m in lower(SemanticMotionSpec("student", "transition_attention"), scene).motions] == ["fade"]


def test_unknown_missing_and_invalid_targets_fallback(scene: dict[str, list[object]]) -> None:
    assert not lower(SemanticMotionSpec("student", "unknown"), scene).motions
    assert not lower(SemanticMotionSpec("focus", "emphasize"), scene).motions
    assert not lower(SemanticMotionSpec("student", "compare", parameters={"subjects": ["student", "missing"]}), scene).motions


def test_timing_and_supported_easing(scene: dict[str, list[object]]) -> None:
    result = lower(SemanticMotionSpec("student", "emphasize", start_time=3.25, duration=2.75, parameters={"easing": "ease_in"}), scene)
    assert result.motions[0].start_time == 3.25
    assert result.motions[0].duration == 2.75
    assert result.motions[0].easing in SUPPORTED_EASINGS
    fallback = lower(SemanticMotionSpec("student", "emphasize", parameters={"easing": "bounce"}), scene)
    assert fallback.motions[0].easing in SUPPORTED_EASINGS


def test_optional_effect_and_vocabulary(scene: dict[str, list[object]]) -> None:
    result = lower(SemanticMotionSpec("student", "emphasize", parameters={"effect": True}), scene)
    assert result.effects and result.effects[0].type == "highlight"
    assert all(motion.type in SUPPORTED_MOTION_TYPES for motion in result.motions)
    assert all(effect.type in SUPPORTED_EFFECTS for effect in result.effects)
    assert all(isinstance(effect, EffectSpec) for effect in result.effects)


def test_visual_focus_integration_and_isolation(scene: dict[str, list[object]]) -> None:
    focus = VisualFocus(primary="student", emphasis_target="student", deemphasis_targets=["desk", "clock"])
    result = lower(SemanticMotionSpec(intent="isolate"), scene, visual_focus=focus)
    assert [motion.target_id for motion in result.motions] == ["student", "desk", "clock"]


def test_no_input_mutation_and_determinism(scene: dict[str, list[object]]) -> None:
    spec = SemanticMotionSpec("student", "emphasize", parameters={"effect": True})
    before = copy.deepcopy(spec.to_dict())
    first = lower(spec, scene).to_dict()
    second = lower(spec, scene).to_dict()
    assert spec.to_dict() == before
    assert first == second
    assert scene["characters"][0].name == "student"


def test_direct_tuple_adapter(scene: dict[str, list[object]]) -> None:
    motions, effects = SemanticMotionLowerer().lower_to_primitives(SemanticMotionSpec("student", "remove"), **scene)
    assert motions[0].type == "exit"
    assert effects == []


def test_forbidden_dependencies_are_absent() -> None:
    path = Path(__file__).parents[1] / "src" / "services" / "semantic_motion.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    assert not imports.intersection({"random", "requests", "ffmpeg", "openai", "anthropic"})
