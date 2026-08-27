"""V1.3-B demo: Visual Focus Resolver over a 10-scene educational example.

Runs the V1.3-A VisualBeatEngine, then resolves a deterministic
``VisualFocus`` for each scene using a small, realistic set of scene elements.

This demo ONLY shows beat -> focus generation.  No rendering, no FFmpeg,
no network, no LLM, no stickman_renderer import.

Run from the project root:
    python demo_visual_focus.py
"""

from __future__ import annotations

from src.services.scene_composition import CharacterSpec, ObjectSpec, TextSpec
from src.services.visual_beat_engine import VisualBeatEngine
from src.services.visual_focus import VisualFocusResolver

SCENES = [
    "Did you know that studying for six hours can leave you remembering almost nothing?",
    "The problem is that longer sessions actually hurt your memory.",
    "This is because the brain loses focus after about 25 minutes of effort.",
    "For example, a student who crammed all night remembered less the next day.",
    "Cramming until 3am does not mean the material reaches long-term memory.",
    "The solution is to switch to short focused sessions with breaks in between.",
    "Here is how the technique works: work for 25 minutes, then rest for five.",
    "Imagine a study session that repeats that cycle four times and ends with a recap.",
    "Use that same cycle for every subject to keep attention and recall high.",
    "Subscribe and try the first 25 minute session today.",
]

# Minimal element set per scene (element names echo narration subjects so
# subject-matching is exercised; names are made up but plausible for school).
SCENE_ELEMENTS = [
    dict(characters=[], objects=[], text_elements=[TextSpec(text="study vs memory")]),
    dict(characters=[], objects=[ObjectSpec(name="brain")], text_elements=[]),
    dict(characters=[], objects=[ObjectSpec(name="brain")], text_elements=[]),
    dict(characters=[CharacterSpec(name="student")], objects=[], text_elements=[]),
    dict(characters=[], objects=[ObjectSpec(name="clock")], text_elements=[]),
    dict(characters=[], objects=[ObjectSpec(name="technique")], text_elements=[]),
    dict(characters=[], objects=[ObjectSpec(name="technique")], text_elements=[]),
    dict(characters=[], objects=[], text_elements=[TextSpec(text="recap")]),
    dict(characters=[], objects=[ObjectSpec(name="cycle")], text_elements=[]),
    dict(characters=[], objects=[], text_elements=[TextSpec(text="subscribe")]),
]


def main() -> None:
    engine = VisualBeatEngine()
    resolver = VisualFocusResolver()
    beats = engine.detect_sequence(SCENES)

    print("V1.3-B Visual Focus Resolver -- demo")
    print("Topic: Does studying longer actually improve memory?")
    print("-" * 72)
    for i, (narration, beat, elements) in enumerate(zip(SCENES, beats, SCENE_ELEMENTS), start=1):
        focus = resolver.resolve(beat, **elements)
        print(f"Scene {i:2} [{beat.type:<11}] imp={beat.importance:<4} emph={beat.emphasis:<6} subj={beat.subject!r}")
        print(f"    primary   : {focus.primary!r}")
        print(f"    secondary : {focus.secondary!r}")
        print(f"    emphasis  : {focus.emphasis}  (target={focus.emphasis_target!r})")
        print(f"    supporting: {focus.supporting}")
        print(f"    background: {focus.background}")
        print(f"    narration : {narration}")
    print("-" * 72)
    print("Resolution: " + " -> ".join(b.type for b in beats))


if __name__ == "__main__":
    main()
