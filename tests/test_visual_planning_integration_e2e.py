"""V1.4-F end-to-end smoke tests: full pipeline.run with the planning stack.

Uses the existing fake-media test infrastructure (stub TTS, stub scene
renderer, fake stickman render, patched assembly/concat) so a full
multi-scene run exercises the real pipeline stages without FFmpeg.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import src.services.visual_beat_engine as beat_module
from src.models.content_package import Transition
from src.pipeline import auto_publish_pipeline as pipeline_module
from src.pipeline.auto_publish_pipeline import (
    AutoPublishPipeline,
    ScenePlan,
    VideoPlan,
    VisualScene,
)


def _scene(role: str, name: str, transition: Transition | None = None) -> ScenePlan:
    return ScenePlan(
        narration=f"{role} evidence about memory",
        visual=VisualScene(
            scene_role=role,
            transition=transition,
            characters=[{"name": name, "x": 0.3, "y": 0.7}],
            objects=[{"name": f"{name}_object", "type": "brain", "x": 0.72, "y": 0.7}],
            text_elements=[{"text": role.title(), "size": "headline", "x": 0.5, "y": 0.12}],
        ),
    )


def _plan() -> VideoPlan:
    return VideoPlan(
        title="V1.4-F E2E",
        scenes=[
            _scene("hook", "hook_subject"),
            _scene("problem", "problem_subject"),
            _scene("solution", "solution_subject", Transition(type="fade_to_black", duration=0.5)),
            _scene("cta", "cta_subject"),
        ],
    )


class _StubTTS:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "status": "completed",
            "audio_reference": f"/tmp/audio_{self.calls}.wav",
            "duration_seconds": 3.0,
        }


def _pipeline(tmp_path) -> AutoPublishPipeline:
    muxer = MagicMock()
    muxer.mux.return_value = {"status": "completed"}
    return AutoPublishPipeline(
        output_directory=str(tmp_path / "publish"),
        tts_service=_StubTTS(),
        scene_renderer=MagicMock(),
        muxer=muxer,
    )


def _run(monkeypatch, tmp_path, semantic: bool, planner: bool):
    captured = []

    def fake_render(job, config):
        captured.append(job)
        return {
            "status": "completed",
            "scene_number": job.scene_number,
            "output_reference": f"scene_{job.scene_number}.mp4",
        }

    monkeypatch.setattr("src.services.stickman_renderer.render_stickman_job", fake_render)
    monkeypatch.setattr(pipeline_module, "SEMANTIC_VISUALS_ENABLED", semantic)
    monkeypatch.setattr(pipeline_module, "VISUAL_STORY_PLANNER_ENABLED", planner)
    beat_calls = []
    original_beat = beat_module.VisualBeatEngine.detect_sequence

    def spy_beat(self, scenes):
        beat_calls.append(1)
        return original_beat(self, scenes)

    monkeypatch.setattr(beat_module.VisualBeatEngine, "detect_sequence", spy_beat)

    with patch.object(
        AutoPublishPipeline,
        "_assemble",
        return_value={"status": "completed", "output_reference": "/tmp/silent.mp4"},
    ), patch.object(
        AutoPublishPipeline,
        "_concat_audio",
        return_value={"status": "completed", "audio_reference": "/tmp/all.wav"},
    ):
        result = _pipeline(tmp_path).run(_plan())
    return result, captured, beat_calls


# --- 20. Real multi-scene render smoke test -------------------------------------


def test_full_run_with_planning_stack_enabled(monkeypatch, tmp_path) -> None:
    result, jobs, beat_calls = _run(monkeypatch, tmp_path, semantic=True, planner=True)
    assert result["status"] == "completed"
    assert result.get("visual_planning") is True
    assert result["scene_count"] == 4
    assert len(jobs) == 4
    assert beat_calls == [1]
    for job in jobs:
        assert "semantics" in job.visual_description
        assert "qa_report" in job.visual_description
        assert "visual_planning" in job.visual_description
    treatments = [job.visual_description["visual_planning"]["treatment"] for job in jobs]
    assert treatments == ["establish", "problem_focus", "solution_growth", "cta"]


def test_full_run_without_planning_stack_is_unchanged(monkeypatch, tmp_path) -> None:
    result, jobs, beat_calls = _run(monkeypatch, tmp_path, semantic=True, planner=False)
    assert result["status"] == "completed"
    assert "visual_planning" not in result
    assert result["scene_count"] == 4
    assert beat_calls == [1]
    for job in jobs:
        assert "semantics" in job.visual_description
        assert "qa_report" in job.visual_description
        assert "visual_planning" not in job.visual_description


def test_full_run_v12_baseline_unchanged(monkeypatch, tmp_path) -> None:
    result, jobs, _ = _run(monkeypatch, tmp_path, semantic=False, planner=False)
    assert result["status"] == "completed"
    assert "visual_planning" not in result
    for job in jobs:
        assert job.motions == []
        assert "semantics" not in (job.visual_description or {})
        assert "qa_report" not in (job.visual_description or {})
        assert "visual_planning" not in (job.visual_description or {})
