from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from src.models.content_package import SUPPORTED_TRANSITION_TYPES, Transition
from src.services.semantic_transition import (
    SemanticTransitionInput,
    SemanticTransitionResolver,
)
from src.services.visual_beat_engine import VisualBeat


resolver = SemanticTransitionResolver()


def beat(kind: str, subject: str = "topic") -> VisualBeat:
    return VisualBeat(type=kind, subject=subject)


def test_problem_to_solution() -> None:
    transition = resolver.resolve(beat("PROBLEM"), beat("SOLUTION"))
    assert transition is not None and transition.type == "slide_up"


def test_contrast_to_contrast() -> None:
    transition = resolver.resolve(beat("CONTRAST", "before"), beat("CONTRAST", "after"))
    assert transition is not None and transition.type == "slide_left"


def test_explanation_to_example() -> None:
    transition = resolver.resolve(beat("EXPLANATION"), beat("EXAMPLE"))
    assert transition is not None and transition.type == "crossfade"


def test_explanation_to_explanation_is_cut() -> None:
    transition = resolver.resolve(beat("EXPLANATION"), beat("EXPLANATION"))
    assert transition is not None and transition.type == "cut" and transition.duration == 0


def test_explicit_relationships() -> None:
    cases = [
        ("cause_effect", "crossfade"),
        ("before_after", "crossfade"),
        ("reveal", "fade"),
        ("escalation", "slide_up"),
        ("continuation", "cut"),
    ]
    for relationship, expected in cases:
        left = {"type": "EXPLANATION", "metadata": {"relationship": relationship}}
        right = {"type": "EXAMPLE"}
        transition = resolver.resolve(left, right)
        assert transition is not None and transition.type == expected


def test_missing_or_ambiguous_relationship_returns_none() -> None:
    assert resolver.resolve(beat("HOOK"), beat("CTA")) is None
    assert resolver.resolve(None, beat("SOLUTION")) is None
    assert resolver.resolve(beat("PROBLEM"), None) is None
    assert resolver.resolve(None, None) is None


def test_unknown_beat_returns_none() -> None:
    assert resolver.resolve({"type": "UNKNOWN"}, beat("SOLUTION")) is None
    assert resolver.resolve(beat("PROBLEM"), {"type": "PROOF"}) is None


def test_transition_is_supported_and_model_valid() -> None:
    transition = resolver.resolve(beat("PROBLEM"), beat("SOLUTION"))
    assert transition is not None
    assert transition.type in SUPPORTED_TRANSITION_TYPES
    transition.validate(max_duration=1.0)


def test_deterministic_output_and_no_mutation() -> None:
    left = beat("PROBLEM", "study")
    right = beat("SOLUTION", "memory")
    before = (copy.deepcopy(left.to_dict()), copy.deepcopy(right.to_dict()))
    first = resolver.resolve(left, right)
    second = resolver.resolve(left, right)
    assert first is not None and second is not None
    assert first.to_dict() == second.to_dict()
    assert (left.to_dict(), right.to_dict()) == before


def test_input_wrapper_serializes() -> None:
    value = SemanticTransitionInput(beat("PROBLEM"), beat("SOLUTION"))
    assert value.to_dict()["left_beat"]["type"] == "PROBLEM"
    assert value.to_dict()["right_beat"]["type"] == "SOLUTION"


def test_no_forbidden_imports() -> None:
    path = Path(__file__).parents[1] / "src" / "services" / "semantic_transition.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imported.intersection({"random", "requests", "ffmpeg", "openai", "anthropic"})
    source = path.read_text(encoding="utf-8")
    assert "StickmanRenderer" not in source
    assert "VideoAssembler" not in source
    assert "AutoPublishPipeline" not in source


@pytest.mark.parametrize(
    ("left_type", "right_type", "expected"),
    [
        ("PROBLEM", "SOLUTION", "slide_up"),
        ("CONTRAST", "EXAMPLE", "slide_left"),
        ("EXPLANATION", "EXAMPLE", "crossfade"),
        ("EXPLANATION", "EXPLANATION", "cut"),
    ],
)
def test_core_relationship_vocabulary(left_type: str, right_type: str, expected: str) -> None:
    transition = resolver.resolve(beat(left_type), beat(right_type))
    assert transition is not None and transition.type == expected
