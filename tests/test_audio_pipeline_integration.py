"""Focused integration tests for the production narration/audio pipeline.

Covers the chain:
    narration -> AudioRequest (render job plan)
              -> RenderJobExecutor audio rendering
              -> RenderOutputManager metadata preservation
              -> MultiSceneRenderer per-scene audio
              -> VideoAssembler final mux
"""

from __future__ import annotations

from typing import Any

import pytest

from src.models.content_package import (
    AudioRequest,
    MotionIntent,
    Transition,
    VideoProductionPlan,
    VideoProductionScene,
)
from src.agents.render_job_executor import RenderJobExecutor, Renderer
from src.agents.render_output_manager import RenderOutputManager
from src.services.audio_renderer import AudioRenderRequest, AudioRenderer
from src.services.multi_scene_renderer import MultiSceneRenderer
from src.services.video_assembler import VideoAssembler


class CapturingAudioRenderer(AudioRenderer):
    """Audio renderer that records the requests it receives."""

    def __init__(self) -> None:
        self.requests: list[AudioRenderRequest] = []

    def render(self, request: AudioRenderRequest) -> dict[str, Any]:
        self.requests.append(request)
        return {
            "scene_number": request.audio_request.scene_number,
            "status": "completed",
            "audio_reference": (
                f"output/audio/narration_{request.audio_request.scene_number}.wav"
            ),
            "duration_seconds": request.audio_request.duration_seconds,
        }


class NullRenderer(Renderer):
    """Video renderer stub returning completed results without rendering."""

    def render(self, request) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        job = request.job
        return {
            "job_id": str(job["job_id"]),
            "status": "completed",
            "output_reference": f"output/{job['job_id']}.mp4",
            "duration_seconds": int(job.get("duration_seconds", 0)),
            "scene_number": job.get("scene_number"),
        }


def _production_plan() -> VideoProductionPlan:
    """Two-scene plan: narrated hook + silent end card."""
    scenes = [
        VideoProductionScene(
            scene_number=1,
            duration_seconds=9,
            visual_description="Opening hook",
            narration="This is the untold story of stickman fight animations.",
            dialogue="",
            sound_effects="",
            camera_direction="Slow push in",
            animation_direction="Character enters with energy",
            transition="cut",
            motions=[],
            motion_intent=MotionIntent(
                scene_role="hook", primary_focus="character", camera_pattern="push"
            ),
            transition_to_next=Transition(
                type="crossfade", duration=0.25, parameters={}
            ),
        ),
        VideoProductionScene(
            scene_number=2,
            duration_seconds=6,
            visual_description="End card",
            narration="",
            dialogue="",
            sound_effects="",
            camera_direction="Static",
            animation_direction="Text fades out",
            transition="cut",
            motions=[],
            motion_intent=MotionIntent(
                scene_role="cta", primary_focus="text", camera_pattern="hold"
            ),
            transition_to_next=None,
        ),
    ]
    return VideoProductionPlan(
        title="Narration pipeline test", total_duration_seconds=15, scenes=scenes
    )


def _job_with_narration(scene_number: int = 3) -> dict[str, Any]:
    """Execution-ready job whose audio_request uses the serialized dict form."""
    return {
        "job_id": f"render-scene-{scene_number}",
        "scene_number": scene_number,
        "duration_seconds": 8,
        "audio_requirements": "Narration: hello world",
        "audio_request": {
            "scene_number": scene_number,
            "duration_seconds": 8,
            "narration_text": "hello world",
            "voice_reference": "default",
            "background_music_reference": "",
            "sound_effect_references": [],
            "audio_format": "wav",
        },
    }


def _output_record(scene_number: int, with_audio: bool = False) -> dict[str, Any]:
    record = {
        "output_id": f"output_render-scene-{scene_number}",
        "job_id": f"render-scene-{scene_number}",
        "scene_number": scene_number,
        "status": "completed",
        "output_reference": f"output/render-scene-{scene_number}.mp4",
        "duration_seconds": 9,
        "has_audio": False,
    }
    if with_audio:
        record["audio_reference"] = f"output/audio/narration_{scene_number}.wav"
    return record


# ---------------------------------------------------------------------------
# 1. Narration reaches the render pipeline
# ---------------------------------------------------------------------------


def test_render_job_plan_attaches_narration_audio_request(tmp_path) -> None:
    """Scenes with narration get an AudioRequest; silent scenes stay silent."""
    from src.database.database_service import DatabaseService
    from src.models.content_package import (
        CharacterAssetPlan,
        SceneAssetPlan,
        VisualStylePlan,
    )
    from src.services.content_generation_service import ContentGenerationService

    db = DatabaseService(str(tmp_path / "audio.db"))
    db.connect()
    db.create_tables()
    try:
        service = ContentGenerationService(db)
        plan = _production_plan()
        asset_plan = SceneAssetPlan(total_assets=0, assets=[])
        visual_style = VisualStylePlan(
            style_name="test",
            art_style="2d",
            background_style="flat",
            lighting_style="soft",
            camera_style="static",
            characters=[],
            consistency_rules=[],
        )
        character_plan: CharacterAssetPlan = service.create_character_asset_plan(
            visual_style
        )

        render_plan = service.create_render_job_plan(plan, asset_plan, character_plan)
    finally:
        db.disconnect()

    assert render_plan.total_jobs == 2

    narrated = render_plan.jobs[0]
    assert isinstance(narrated.audio_request, AudioRequest)
    assert (
        narrated.audio_request.narration_text
        == "This is the untold story of stickman fight animations."
    )
    assert narrated.audio_request.duration_seconds == 9
    assert narrated.audio_request.scene_number == 1
    assert narrated.audio_request.audio_format == "wav"

    silent = render_plan.jobs[1]
    assert silent.audio_request is None


# ---------------------------------------------------------------------------
# 2. Audio metadata preserved through RenderJobExecutor (+ OutputManager)
# ---------------------------------------------------------------------------


def test_executor_renders_audio_and_preserves_metadata() -> None:
    """Dict-form audio_request is coerced and its result lands on the output."""
    from src.core.context import WorkflowContext

    audio = CapturingAudioRenderer()
    executor = RenderJobExecutor(renderer=NullRenderer(), audio_renderer=audio)

    context = WorkflowContext()
    context.set("render_jobs", [_job_with_narration(3)])
    result = executor.run(context)
    results = result.data["render_results"]

    assert len(audio.requests) == 1
    received = audio.requests[0].audio_request
    assert received.narration_text == "hello world"
    assert received.duration_seconds == 8

    rendered = results[0]
    assert rendered["status"] == "completed"
    assert rendered["audio_result"]["status"] == "completed"
    assert rendered["audio_result"]["audio_reference"].endswith("narration_3.wav")

    outputs = RenderOutputManager()._normalize_outputs(results)
    record = outputs[0]
    assert record["audio_reference"].endswith("narration_3.wav")
    assert record["audio_status"] == "completed"


def test_no_audio_request_skips_audio_renderer() -> None:
    """Jobs without audio_request never touch the audio renderer."""
    from src.core.context import WorkflowContext

    audio = CapturingAudioRenderer()
    executor = RenderJobExecutor(renderer=NullRenderer(), audio_renderer=audio)

    job = _job_with_narration(1)
    job.pop("audio_request")

    context = WorkflowContext()
    context.set("render_jobs", [job])
    result = executor.run(context)
    results = result.data["render_results"]

    assert audio.requests == []
    outputs = RenderOutputManager()._normalize_outputs(results)
    assert outputs[0]["audio_reference"] is None
    assert outputs[0]["audio_status"] == "no_audio"


# ---------------------------------------------------------------------------
# 3. Scene audio reaches MultiSceneRenderer
# ---------------------------------------------------------------------------


def test_multi_scene_renderer_attaches_scene_audio(monkeypatch) -> None:
    """Per-scene narration is rendered and passed to the final assembler."""

    def fake_render_stickman_job(job_spec, config):  # type: ignore[no-untyped-def]
        return {
            "job_id": job_spec.job_id,
            "status": "completed",
            "output_reference": f"output/{job_spec.job_id}.mp4",
            "duration_seconds": job_spec.duration_seconds,
        }

    monkeypatch.setattr(
        "src.services.multi_scene_renderer.render_stickman_job",
        fake_render_stickman_job,
    )

    captured: dict[str, Any] = {}

    def fake_assemble(self, outputs):  # type: ignore[no-untyped-def]
        captured["outputs"] = outputs
        return {
            "status": "completed",
            "output_reference": "output/final_video.mp4",
            "command": [],
            "filter_complex": "",
        }

    monkeypatch.setattr(VideoAssembler, "assemble", fake_assemble)

    audio = CapturingAudioRenderer()
    renderer = MultiSceneRenderer(
        video_assembler=VideoAssembler(), audio_renderer=audio
    )

    jobs = [_job_with_narration(1)]
    silent_job = _job_with_narration(2)
    silent_job.pop("audio_request")
    jobs.append(silent_job)

    result = renderer.render_plan({"jobs": jobs})

    assert result["status"] == "completed"
    assert len(audio.requests) == 1
    assert audio.requests[0].audio_request.scene_number == 1

    outputs = captured["outputs"]
    assert outputs[0]["audio_reference"].endswith("narration_1.wav")
    assert outputs[1]["audio_reference"] is None


def test_multi_scene_renderer_without_audio_renderer_stays_silent(monkeypatch) -> None:
    """No injected audio renderer preserves legacy silent behavior."""

    def fake_render_stickman_job(job_spec, config):  # type: ignore[no-untyped-def]
        return {
            "job_id": job_spec.job_id,
            "status": "completed",
            "output_reference": f"output/{job_spec.job_id}.mp4",
            "duration_seconds": job_spec.duration_seconds,
        }

    monkeypatch.setattr(
        "src.services.multi_scene_renderer.render_stickman_job",
        fake_render_stickman_job,
    )

    def fake_silent_assemble(self, outputs):  # type: ignore[no-untyped-def]
        return {
            "status": "completed",
            "output_reference": "output/final_video.mp4",
            "command": [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
            ],
            "filter_complex": "",
        }

    monkeypatch.setattr(VideoAssembler, "assemble", fake_silent_assemble)

    renderer = MultiSceneRenderer(video_assembler=VideoAssembler(), audio_renderer=None)
    result = renderer.render_plan({"jobs": [_job_with_narration(1)]})

    assert result["status"] == "completed"
    assert any("anullsrc" in arg for arg in result["assembly_result"]["command"])


# ---------------------------------------------------------------------------
# 4/5. Final assembly receives audio; no-audio scenes still work
# ---------------------------------------------------------------------------


def test_assembler_muxes_narration_audio() -> None:
    """Scenes with audio_reference feed real narration into the filter graph."""
    assembler = VideoAssembler(execute_enabled=False)

    outputs = [
        _output_record(1, with_audio=True),
        _output_record(2, with_audio=False),
    ]
    outputs[0]["transition_to_next"] = {
        "type": "crossfade",
        "duration": 0.25,
        "parameters": {},
    }

    result = assembler.assemble(outputs)

    assert result["status"] == "command_built"
    command = " ".join(result["command"])
    assert "output/audio/narration_1.wav" in command
    filter_complex = result["filter_complex"]
    assert "apad" in filter_complex
    assert "atrim=0:9.000" in filter_complex
    # The silent second scene still gets synthesized silence.
    assert "anullsrc" in command


def test_no_audio_scenes_still_assemble_silently() -> None:
    """Existing no-audio behavior is unchanged (all scenes use anullsrc)."""
    assembler = VideoAssembler(execute_enabled=False)

    outputs = [_output_record(1), _output_record(2)]
    outputs[0]["transition_to_next"] = {
        "type": "crossfade",
        "duration": 0.25,
        "parameters": {},
    }

    result = assembler.assemble(outputs)

    assert result["status"] == "command_built"
    command = " ".join(result["command"])
    assert command.count("anullsrc") == 2
    assert "acrossfade" in result["filter_complex"]
    assert "narration_" not in command


def test_settb_unifies_timebase_for_transition_chain() -> None:
    """Every video branch normalizes timebase so xfade-after-concat works."""
    assembler = VideoAssembler(execute_enabled=False)

    outputs = [
        _output_record(1, with_audio=True),
        _output_record(2, with_audio=False),
    ]
    outputs[0]["transition_to_next"] = {"type": "cut", "duration": 0.0}
    outputs[1]["transition_to_next"] = {"type": "crossfade", "duration": 0.25}

    result = assembler.assemble(outputs)
    assert result["filter_complex"].count("settb=AVTB") >= 2


# ---------------------------------------------------------------------------
# 6. Real TTS provider produces non-silent samples
# ---------------------------------------------------------------------------


def test_system_speech_tts_produces_audible_samples(tmp_path) -> None:
    """Real Windows TTS generates a WAV with actual (non-silent) samples."""
    import os
    import struct
    import wave

    from src.services.system_speech_tts_service import SystemSpeechTTSService
    from src.services.tts_service import TTSRequest

    service = SystemSpeechTTSService(output_directory=str(tmp_path / "audio"))
    if not service.is_available():
        pytest.skip("Windows System.Speech not available")

    request = TTSRequest(
        text=(
            "Phase one validation of the production narration pipeline. "
            "If you can hear this voice, synchronized audio is working."
        ),
        voice_reference="default",
        audio_format="wav",
    )
    result = service.generate(request)

    assert result["status"] == "completed"
    wav_path = result["audio_reference"]
    assert os.path.exists(wav_path)
    assert os.path.getsize(wav_path) > 1000

    with wave.open(wav_path, "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
        width = handle.getsampwidth()
        raw = handle.readframes(frames)

    assert frames / rate >= 1.5, "narration should last at least 1.5s"
    assert width == 2, "expected 16-bit PCM samples"

    # Loudness check: RMS amplitude must be clearly above digital silence.
    sample_count = len(raw) // 2
    assert sample_count > 0
    total = 0
    for offset in range(sample_count):
        value = struct.unpack_from("<h", raw, offset * 2)[0]
        total += value * value
    rms = (total / sample_count) ** 0.5
    assert rms > 200, f"narration is effectively silent (RMS={rms:.1f})"
