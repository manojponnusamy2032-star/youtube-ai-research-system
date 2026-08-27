"""V1.3-A demo: Visual Beat Engine generation over a 10-scene educational example.

Shows ONLY beat generation.  No rendering, no FFmpeg, no network, no LLM.

Topic: "Does studying longer actually improve memory?"
Runs narration through the deterministic VisualBeatEngine and prints the
resulting beats, which future V1.3-B/C/D layers will consume.

Run from the repository root:
    python demo_visual_beat_engine.py
"""

from __future__ import annotations

from src.services.visual_beat_engine import VisualBeatEngine

# 10 scenes, narration-only (the deterministic rules decide the type; some
# scenes use the narration content itself to select a more specific beat).
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


def main() -> None:
    engine = VisualBeatEngine()
    beats = engine.detect_sequence(SCENES)

    print("V1.3-A Visual Beat Engine -- demo")
    print("Topic: Does studying longer actually improve memory?")
    print("-" * 70)
    for i, (narration, beat) in enumerate(zip(SCENES, beats), start=1):
        print(f"Scene {i}: {beat.type:<12} imp={beat.importance:<4} "
              f"emph={beat.emphasis:<6} subject={beat.subject!r}")
        print(f"    narration: {narration}")
    print("-" * 70)
    print("Resolution: " + " -> ".join(b.type for b in beats))


if __name__ == "__main__":
    main()
