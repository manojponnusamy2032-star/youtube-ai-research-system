"""Tests for the V1.3-A Visual Beat Engine.

Covers beat taxonomy detection, scene-position fallback, explicit scene_role
precedence, narration-only operation, empty/weak fallback, determinism, subject
extraction, importance/emphasis assignment, malformed Analysis fields, and
no network/LLM dependency.  Pure Python -- no FFmpeg.
"""

from __future__ import annotations

import json

import pytest

from src.services.visual_beat_engine import (
    SUPPORTED_BEAT_TYPES,
    VisualBeat,
    VisualBeatEngine,
)


@pytest.fixture
def engine() -> VisualBeatEngine:
    return VisualBeatEngine()


# ---------------------------------------------------------------------------
# Beat taxonomy detection
# ---------------------------------------------------------------------------


class TestBeatDetection:
    def test_hook_detection(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "Did you know that studying six hours can hurt your memory?",
            scene_index=4, total_scenes=10,
        )
        assert beat.type == "HOOK"

    def test_problem_detection(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "The problem is that focus drops after prolonged study.",
            scene_index=3, total_scenes=10,
        )
        assert beat.type == "PROBLEM"

    def test_contrast_detection(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "Studying longer does not mean you remember more.",
            scene_index=4, total_scenes=10,
        )
        assert beat.type == "CONTRAST"

    def test_explanation_detection(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "This works because the brain consolidates during breaks.",
            scene_index=4, total_scenes=10,
        )
        assert beat.type == "EXPLANATION"

    def test_example_detection(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "For example, a 25 minute focus block beats two hours of cramming.",
            scene_index=4, total_scenes=10,
        )
        assert beat.type == "EXAMPLE"

    def test_solution_detection(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "The solution is to use short focused sessions with breaks.",
            scene_index=4, total_scenes=10,
        )
        assert beat.type == "SOLUTION"

    def test_cta_detection(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "Subscribe for more study techniques and try it today.",
            scene_index=4, total_scenes=10,
        )
        assert beat.type == "CTA"


# ---------------------------------------------------------------------------
# Position fallback and role precedence
# ---------------------------------------------------------------------------


class TestPositionAndPrecedence:
    def test_scene_position_first_is_hook(self, engine: VisualBeatEngine) -> None:
        # Even an empty narration at position 0 is a HOOK.
        assert engine.detect("", scene_index=0, total_scenes=10).type == "HOOK"

    def test_scene_position_last_is_cta(self, engine: VisualBeatEngine) -> None:
        assert engine.detect("", scene_index=9, total_scenes=10).type == "CTA"

    def test_scene_role_precedence(self, engine: VisualBeatEngine) -> None:
        # Explicit role wins even though narration and position suggest HOOK.
        beat = engine.detect(
            "A surprising opening line.",
            scene_index=5, total_scenes=10, scene_role="explanation",
        )
        assert beat.type == "EXPLANATION"

    def test_scene_role_cta_overrides_position(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect("", scene_index=5, total_scenes=10, scene_role="solution")
        assert beat.type == "SOLUTION"


# ---------------------------------------------------------------------------
# Fallback and robustness
# ---------------------------------------------------------------------------


class TestFallback:
    def test_empty_narration_middle_falls_to_explanation(
        self, engine: VisualBeatEngine,
    ) -> None:
        beat = engine.detect("", scene_index=4, total_scenes=10)
        assert beat.type == "EXPLANATION"
        assert beat.subject == ""

    def test_weak_narration_falls_back(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect("  ", scene_index=4, total_scenes=10)
        assert beat.type == "EXPLANATION"

    def test_malformed_analysis_fields(self, engine: VisualBeatEngine) -> None:
        # None / partial dict / object with missing fields must not raise.
        assert engine.detect("ok", scene_index=4, total_scenes=10, analysis=None).type
        assert engine.detect(
            "ok", scene_index=4, total_scenes=10, analysis={},
        ).type
        beat = engine.detect(
            "ok", scene_index=4, total_scenes=10, analysis={"main_topic": None},
        )
        assert beat.type



# ---------------------------------------------------------------------------
# Determinism and serialization
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_execution_is_deterministic(
        self, engine: VisualBeatEngine,
    ) -> None:
        kwargs = dict(
            narration="The problem is that focus drops after long sessions.",
            scene_index=3, total_scenes=10,
        )
        first = engine.detect(**kwargs)
        for _ in range(20):
            assert engine.detect(**kwargs) == first

    def test_sequence_is_deterministic(self, engine: VisualBeatEngine) -> None:
        scenes = ["First scene", "second", "third", "last"]
        a = engine.detect_sequence(scenes)
        b = engine.detect_sequence(scenes)
        assert [x.to_dict() for x in a] == [x.to_dict() for x in b]


class TestSerialization:
    def test_visual_beat_is_serializable(self) -> None:
        beat = VisualBeat(type="PROBLEM", subject="focus", importance=0.9, emphasis="high")
        payload = json.dumps(beat.to_dict())
        restored = json.loads(payload)
        assert restored == {
            "type": "PROBLEM",
            "subject": "focus",
            "importance": 0.9,
            "emphasis": "high",
        }

    def test_sequence_serializes(self, engine: VisualBeatEngine) -> None:
        beats = engine.detect_sequence(["a", "b", "c"])
        json.dumps([b.to_dict() for b in beats])  # must not raise



# ---------------------------------------------------------------------------
# Subject, importance, emphasis
# ---------------------------------------------------------------------------


class TestSubjectImportanceEmphasis:
    def test_contrast_subject_extraction(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "Studying longer does not mean you remember more.",
            scene_index=4, total_scenes=10,
        )
        assert beat.subject == "study vs memory"

    def test_problem_subject_extraction(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "The problem is that focus drops after prolonged study.",
            scene_index=4, total_scenes=10,
        )
        assert beat.subject == "focus"

    def test_uncertain_subject_stays_empty(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "Here is a neutral statement with no clear subject.",
            scene_index=4, total_scenes=10,
        )
        assert beat.subject == ""

    def test_main_topic_fallback(self, engine: VisualBeatEngine) -> None:
        beat = engine.detect(
            "No clue here for a subject at all",
            scene_index=4, total_scenes=10,
            analysis={"main_topic": "study efficiency and memory retention"},
        )
        assert beat.subject == "study efficiency and memory retention"

    def test_importance_assignment(self, engine: VisualBeatEngine) -> None:
        assert engine.detect(
            "Did you know something?", scene_index=0, total_scenes=10,
        ).importance > 0.9
        beat = engine.detect("", scene_index=4, total_scenes=10)
        assert beat.importance == pytest.approx(0.6)

    def test_emphasis_assignment(self, engine: VisualBeatEngine) -> None:
        assert engine.detect(
            "Did you know something?", scene_index=0, total_scenes=10,
        ).emphasis == "high"
        assert engine.detect(
            "This is because of a mechanism.", scene_index=4, total_scenes=10,
        ).emphasis == "medium"


# ---------------------------------------------------------------------------
# No network / LLM dependency and structural guarantees
# ---------------------------------------------------------------------------


class TestPurity:
    def test_narration_only_operation(self, engine: VisualBeatEngine) -> None:
        # No analysis, no role, only narration at a known position.
        beat = engine.detect(
            "The problem is that focus drops.",
            scene_index=2, total_scenes=5,
        )
        assert beat.type == "PROBLEM"

    def test_no_network_or_llm_dependency(self, engine: VisualBeatEngine) -> None:
        # Engine is a pure local computation; detection must not touch I/O.
        beat = engine.detect("Subscribe today.", scene_index=5, total_scenes=6)
        assert beat.type == "CTA"

    def test_supported_beat_types_exhaustive(self) -> None:
        assert SUPPORTED_BEAT_TYPES == {
            "HOOK", "PROBLEM", "CONTRAST", "EXPLANATION",
            "EXAMPLE", "SOLUTION", "CTA",
        }

    def test_invalid_beat_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            VisualBeat(type="REVEAL")

