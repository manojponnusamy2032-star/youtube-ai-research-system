"""Day-4 tests: storytelling validation report generator.

Covers the metrics computed by ``run_day4_validation_report.py`` used in the
quantitative Day-4 validation (section 14 of the brief): scene counts,
duration, unique visual states, camera / character-action uniqueness,
scene-purpose distribution, and repeated consecutive visual/camera states.
"""
from __future__ import annotations

import json

from run_day4_validation_report import (
    _count_repeated_runs,
    _visual_state,
    generate_report,
)


def _write_plan(tmp_path, scenes, total=None):
    path = tmp_path / "visual_plan.json"
    payload = {
        "topic": "t",
        "title": "T",
        "scenes": scenes,
        "total_duration_seconds": total or sum(s["duration_seconds"] for s in scenes),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _scene(num, dur, cam="static", action="talk", env="study_desk",
           emotion="focused", objects=(), purpose="Explain it."):
    return {
        "scene_number": num,
        "duration_seconds": dur,
        "camera_instructions": cam,
        "character_action": action,
        "visual_prompt": f"Stickman scene: {purpose}",
        "visual_description": {
            "environment": {"type": env},
            "characters": [{"emotion": emotion}],
            "objects": [{"type": o} for o in objects],
        },
    }


def test_report_counts_scenes_duration(tmp_path):
    scenes = [
        _scene(1, 10, "slow zoom in", "wave", "study_desk", "happy", ("book",)),
        _scene(2, 12, "static", "talk", "office", "focused", ("laptop",)),
    ]
    report = generate_report(_write_plan(tmp_path, scenes, total=22))
    assert report["total_scenes"] == 2
    assert report["total_duration"] == 22
    assert report["average_scene_duration"] == 11.0


def test_report_unique_counts(tmp_path):
    scenes = [
        _scene(1, 10, "slow zoom in", "wave", "study_desk", "happy", ["book"]),
        _scene(2, 10, "pan right", "run", "office", "excited", ["laptop"]),
        _scene(3, 10, "static", "talk", "classroom", "focused", ["pen"]),
    ]
    report = generate_report(_write_plan(tmp_path, scenes, total=30))
    assert report["unique_visual_states"] == 3
    assert report["unique_camera_decisions"] == 3
    assert report["unique_character_actions"] == 3


def test_report_purpose_distribution(tmp_path):
    scenes = [
        _scene(1, 10, purpose="Establish attention."),
        _scene(2, 10, purpose="Explain the concept."),
        _scene(3, 10, purpose="Explain the concept."),
    ]
    report = generate_report(_write_plan(tmp_path, scenes, total=30))
    dist = report["scene_purpose_distribution"]
    assert dist["Establish attention."] == 1
    assert dist["Explain the concept."] == 2


def test_report_repeated_consecutive_states(tmp_path):
    scenes = [
        _scene(1, 10, "static", "talk"),
        _scene(2, 10, "static", "talk"),
        _scene(3, 10, "pan right", "run"),
        _scene(4, 10, "pan right", "run"),
        _scene(5, 10, "static", "talk"),
    ]
    report = generate_report(_write_plan(tmp_path, scenes, total=50))
    assert report["repeated_consecutive_visual_states"] == 2
    assert report["repeated_consecutive_camera_states"] == 2


def test_count_repeated_runs():
    assert _count_repeated_runs([1, 1, 2, 2, 3, 3, 3]) == 4
    assert _count_repeated_runs([1, 2, 3]) == 0
    assert _count_repeated_runs([]) == 0


def test_visual_state_fingerprint():
    s1 = _scene(1, 10, "static", "talk", "study_desk", "focused", ["book"])
    s2 = _scene(2, 10, "static", "talk", "study_desk", "focused", ["book"])
    assert _visual_state(s1) == _visual_state(s2)
    # Camera is tracked separately from the visual state fingerprint.
    s3 = _scene(3, 10, "pan right", "talk", "study_desk", "focused", ["book"])
    assert _visual_state(s1) == _visual_state(s3)
    # A real state difference (character action) changes the fingerprint.
    s4 = _scene(4, 10, "static", "run", "study_desk", "focused", ["book"])
    assert _visual_state(s1) != _visual_state(s4)
    # An environment difference also changes the fingerprint.
    s5 = _scene(5, 10, "static", "talk", "office", "focused", ["book"])
    assert _visual_state(s1) != _visual_state(s5)