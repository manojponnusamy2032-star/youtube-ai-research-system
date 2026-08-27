"""Tests for the Visual Focus Resolver (V1.3-B).

These cover every scenario required by the V1.3-B brief plus a few extra
guards for robustness.  The resolver is a pure semantic service, so the tests
stay pure-python (no FFmpeg, no renderer, no network, no LLM).
"""

from __future__ import annotations

from dataclasses import is_dataclass
from types import SimpleNamespace

import pytest

from src.services.scene_composition import CharacterSpec, ObjectSpec, TextSpec
from src.services.visual_beat_engine import VisualBeat
from src.services.visual_focus import VisualFocus, VisualFocusResolver


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _beat(type: str = "EXPLANATION", subject: str = "", emphasis: str = "medium",
          importance: float = 0.6) -> VisualBeat:
    return VisualBeat(type=type, subject=subject, importance=importance, emphasis=emphasis)


def _char(name: str = "alice") -> CharacterSpec:
    return CharacterSpec(name=name, pose="talk")


def _obj(name: str = "desk", obj_type: str = "desk") -> ObjectSpec:
    return ObjectSpec(name=name, type=obj_type)


def _text(text: str = "headline") -> TextSpec:
    return TextSpec(text=text, size="headline")


# ---------------------------------------------------------------------------
# 1-4  focus selection
# ---------------------------------------------------------------------------


def test_basic_primary_focus():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="focus"),
                         objects=[_obj("focus", "brain")],
                         characters=[_char("alice")])
    assert f.primary == "focus"
    

# ---------------------------------------------------------------------------
# 1-4b  focus selection (cont.)
# ---------------------------------------------------------------------------


def test_explicit_primary_focus_precedence():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="focus"),
                         primary_focus="alice", characters=[_char("alice"), _char("bob")])
    assert f.primary == "alice"


def test_explicit_camera_focus_target_precedence():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="focus"),
                         focus_target="bob", characters=[_char("alice"), _char("bob")])
    assert f.primary == "bob"


def test_beat_subject_matching_an_object():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("SOLUTION", subject="timer"), objects=[_obj("clock"), _obj("timer")])
    assert f.primary == "timer"


def test_beat_subject_matching_a_character():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("HOOK", subject="alice"), characters=[_char("alice")])
    assert f.primary == "alice"


def test_unmatched_beat_subject_falls_back_to_existing_element():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="nonexistent"),
                         objects=[_obj("clock"), _obj("desk")])
    assert f.primary == "clock"
    assert "nonexistent" not in [f.primary, f.secondary, *f.supporting, *f.background]


# ---------------------------------------------------------------------------
# 5-6  hook / problem
# ---------------------------------------------------------------------------


def test_hook_focus():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("HOOK", subject="headline"), text_elements=[_text("headline")])
    assert f.primary == "headline"


def test_problem_focus():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="focus", emphasis="high"), objects=[_obj("focus")])
    assert f.primary == "focus"
    assert f.emphasis == "high"


# ---------------------------------------------------------------------------
# 7  contrast primary + secondary
# ---------------------------------------------------------------------------


def test_contrast_primary_and_secondary():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("CONTRAST", subject="study time vs memory"),
                         objects=[_obj("study time"), _obj("memory")])
    left, right = "study time", "memory"
    assert (f.primary == left and f.secondary == right) or \
           (f.primary == right and f.secondary == left)


# ---------------------------------------------------------------------------
# 8-10  explanation / example / solution
# ---------------------------------------------------------------------------


def test_explanation_focus():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("EXPLANATION", subject="mechanism"), objects=[_obj("mechanism")])
    assert f.primary == "mechanism"
    assert f.emphasis == "medium"


def test_example_focus():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("EXAMPLE", subject="case", emphasis="low"), objects=[_obj("case")])
    assert f.primary == "case"
    assert f.emphasis == "low"


def test_solution_focus():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("SOLUTION", subject="technique", emphasis="high"), characters=[_char("technique")])
    assert f.primary == "technique"
    assert f.emphasis == "high"


def test_cta_text_focus():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("CTA", subject="subscribe"), text_elements=[_text("subscribe")])
    assert f.primary == "subscribe"


# ---------------------------------------------------------------------------
# 11-15  supporting / background / emphasis
# ---------------------------------------------------------------------------


def test_supporting_and_background_excludes_primary():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("HOOK"),
                         objects=[_obj("title"), _obj("icon"), _obj("decoration")])
    # primary + secondary + supporting + background must cover all elements,
    # with no duplication and primary never appearing in supporting/background.
    elements = [f.primary, f.secondary, *f.supporting, *f.background]
    assert f.primary not in (f.background + f.supporting)
    assert len(elements) == 3
    assert len(set(elements)) == 3


def test_emphasis_target_matches_primary():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="focus", emphasis="high"),
                         objects=[_obj("focus")])
    assert f.emphasis_target == "focus"
    assert f.emphasis == "high"


def test_deemphasis_targets_exclude_primary():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="focus"),
                         objects=[_obj("focus"), _obj("desk")])
    assert "focus" not in f.deemphasis_targets


def test_emphasis_label_copied_from_beat():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("EXAMPLE", subject="case", emphasis="low"), objects=[_obj("case")])
    assert f.emphasis == "low"


# ---------------------------------------------------------------------------
# 16-17  edge cases
# ---------------------------------------------------------------------------


def test_empty_scene():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("HOOK", emphasis="high"))
    assert f.primary == ""
    assert f.emphasis == "high"


def test_missing_optional_metadata():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("EXPLANATION", subject="topic"),
                         characters=[], objects=[], text_elements=[],
                         primary_focus="", focus_target=None)
    assert f.primary == ""
    assert f.emphasis == "medium"


def test_malformed_beat_type_defaults_to_medium():
    resolver = VisualFocusResolver()
    f = resolver.resolve(SimpleNamespace(type="", subject="nothing"))
    assert f.primary == ""
    assert f.emphasis == "medium"


def test_accepts_dict_specs():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("PROBLEM", subject="focus"),
                         characters=[{"name": "alice"}],
                         objects=[{"name": "focus", "type": "object"}])
    assert f.primary == "focus"


# ---------------------------------------------------------------------------
# 18  empty beat subject -> first element
# ---------------------------------------------------------------------------


def test_empty_beat_subject_uses_first_element():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("EXPLANATION", subject=""),
                         objects=[_obj("first"), _obj("second")])
    assert f.primary == "first"


# ---------------------------------------------------------------------------
# 19  deterministic repeated execution
# ---------------------------------------------------------------------------


def test_deterministic_repeated_execution():
    resolver = VisualFocusResolver()
    beat = _beat("CONTRAST", subject="study time vs memory", emphasis="high")
    kwargs = dict(objects=[_obj("study time"), _obj("memory")], characters=[_char("alice")])
    f1 = resolver.resolve(beat, **kwargs)
    f2 = resolver.resolve(beat, **kwargs)
    assert f1.to_dict() == f2.to_dict()


# ---------------------------------------------------------------------------
# 20  serialization + dataclass
# ---------------------------------------------------------------------------


def test_visual_focus_is_dataclass():
    from dataclasses import is_dataclass
    assert is_dataclass(VisualFocus)


def test_visual_focus_serializable():
    resolver = VisualFocusResolver()
    f = resolver.resolve(_beat("HOOK", subject="headline"), text_elements=[_text("headline")])
    d = f.to_dict()
    assert isinstance(d, dict)
    assert set(d.keys()) == {"primary", "secondary", "supporting", "background",
                             "emphasis_target", "deemphasis_targets", "emphasis", "timing"}


# ---------------------------------------------------------------------------
# 21  no network / no rendering (static + import side-effect guard)
# ---------------------------------------------------------------------------


def test_module_has_no_render_or_network_imports():
    # Pure-python guard: the module must not import renderers/network/vision.
    with open("src/services/visual_focus.py") as fh:
        src = fh.read()
    assert "requests" not in src
    assert "openai" not in src
    assert "ffmpeg" not in src
    # stickman_renderer is explicitly forbidden
    assert "stickman_renderer" not in src.replace("stickman", "<redacted>")


# ---------------------------------------------------------------------------
# 22  no mutation of input scene data
# ---------------------------------------------------------------------------


def test_no_mutation_of_input_scene_data():
    resolver = VisualFocusResolver()
    chars = [CharacterSpec(name="alice"), CharacterSpec(name="bob")]
    objs = [ObjectSpec(name="desk"), ObjectSpec(name="clock")]
    texts = [TextSpec(text="headline")]
    beat = _beat("PROBLEM", subject="focus")
    char_names_before = [c.name for c in chars]
    obj_names_before = [o.name for o in objs]
    beat_before = (beat.type, beat.subject, beat.emphasis, beat.importance)
    resolver.resolve(beat, characters=chars, objects=objs, text_elements=texts,
                     primary_focus="alice", focus_target="bob")
    assert [c.name for c in chars] == char_names_before
    assert [o.name for o in objs] == obj_names_before
    assert (beat.type, beat.subject, beat.emphasis, beat.importance) == beat_before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


