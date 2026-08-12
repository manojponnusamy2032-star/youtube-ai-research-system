"""Tests for RenderJobExecutor agent."""

from __future__ import annotations

from unittest.mock import patch

from src.agents.render_job_executor import MockRenderer, RenderJobExecutor, RenderRequest, Renderer
from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext


def _render_jobs() -> list[dict[str, object]]:
    """Create valid render jobs for testing."""
    return [
        {
            "job_id": "render-scene-1",
            "scene_number": 1,
            "status": "pending",
            "duration_seconds": 45,
            "render_type": "host_footage",
            "visual_prompt": "Scene 1: Opening shot",
            "animation_instructions": "Fade in",
            "camera_instructions": "Wide shot",
            "audio_requirements": "Narration",
        },
        {
            "job_id": "render-scene-2",
            "scene_number": 2,
            "status": "pending",
            "duration_seconds": 90,
            "render_type": "b-roll",
            "visual_prompt": "Scene 2: B-roll",
            "animation_instructions": "Ken Burns",
            "camera_instructions": "Static shot",
            "audio_requirements": "Music",
        },
    ]


def test_successful_single_job_execution() -> None:
    """Test successful execution of a single render job."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", [_render_jobs()[0]])
    
    result = executor.run(context)
    
    assert result.success is True
    assert "render_results" in result.data
    assert len(result.data["render_results"]) == 1
    
    job_result = result.data["render_results"][0]
    assert job_result["job_id"] == "render-scene-1"
    assert job_result["status"] == "completed"
    assert job_result["output_reference"] == "mock://render/render-scene-1"
    assert job_result["duration_seconds"] == 45


def test_multiple_jobs_execution() -> None:
    """Test execution of multiple render jobs."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", _render_jobs())
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(result.data["render_results"]) == 2
    assert result.data["total_jobs"] == 2
    assert result.data["successful_jobs"] == 2
    assert result.data["failed_jobs"] == 0
    
    # Verify both jobs completed
    job1 = result.data["render_results"][0]
    job2 = result.data["render_results"][1]
    assert job1["job_id"] == "render-scene-1"
    assert job1["status"] == "completed"
    assert job2["job_id"] == "render-scene-2"
    assert job2["status"] == "completed"


def test_missing_render_jobs_returns_failure() -> None:
    """Test that missing render_jobs returns failure."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    
    result = executor.run(context)
    
    assert result.success is False
    assert "render_jobs not found" in result.message


def test_invalid_job_without_job_id_returns_failure() -> None:
    """Test that invalid job without job_id returns failure."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", [
        {"scene_number": 1, "duration_seconds": 45},
    ])
    
    result = executor.run(context)
    
    assert result.success is False
    assert "missing job_id" in result.message


def test_renderer_failure_allows_other_jobs_to_continue() -> None:
    """Test that renderer failure for one job allows others to continue."""
    
    class FailingRenderer(Renderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            if request.job["job_id"] == "render-scene-1":
                raise RuntimeError("Render failed")
            return {
                "job_id": str(request.job["job_id"]),
                "status": "completed",
                "output_reference": f"mock://render/{request.job['job_id']}",
                "duration_seconds": int(request.job.get("duration_seconds", 0)),
            }
    
    executor = RenderJobExecutor(renderer=FailingRenderer())
    context = WorkflowContext()
    context.set("render_jobs", _render_jobs())
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(result.data["render_results"]) == 2
    assert result.data["successful_jobs"] == 1
    assert result.data["failed_jobs"] == 1
    
    # First job should have failed
    job1 = result.data["render_results"][0]
    assert job1["job_id"] == "render-scene-1"
    assert job1["status"] == "failed"
    assert "error" in job1
    assert "Render failed" in job1["error"]
    
    # Second job should have succeeded
    job2 = result.data["render_results"][1]
    assert job2["job_id"] == "render-scene-2"
    assert job2["status"] == "completed"


def test_correct_render_results_context_output() -> None:
    """Test that render_results are correctly stored in context."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", _render_jobs())
    
    result = executor.run(context)
    
    assert result.success is True
    assert context.has("render_results")
    
    render_results = context.get("render_results")
    assert isinstance(render_results, list)
    assert len(render_results) == 2
    
    # Verify structure
    for job_result in render_results:
        assert "job_id" in job_result
        assert "status" in job_result
        assert "output_reference" in job_result
        assert "duration_seconds" in job_result
        assert job_result["status"] == "completed"


def test_deterministic_mock_renderer_output() -> None:
    """Test that MockRenderer produces deterministic output."""
    renderer = MockRenderer()
    request = RenderRequest(
        job={
            "job_id": "test-job",
            "scene_number": 1,
            "duration_seconds": 30,
        }
    )
    
    # Call render multiple times
    result1 = renderer.render(request)
    result2 = renderer.render(request)
    result3 = renderer.render(request)
    
    # All results should be identical
    assert result1 == result2 == result3
    assert result1["job_id"] == "test-job"
    assert result1["status"] == "completed"
    assert result1["output_reference"] == "mock://render/test-job"
    assert result1["duration_seconds"] == 30


def test_render_jobs_not_list_returns_failure() -> None:
    """Test that non-list render_jobs returns failure."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", "not a list")
    
    result = executor.run(context)
    
    assert result.success is False
    assert "render_jobs must be a list" in result.message


def test_empty_jobs_list_executes_successfully() -> None:
    """Test that empty jobs list executes successfully."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", [])
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(result.data["render_results"]) == 0
    assert result.data["total_jobs"] == 0
    assert result.data["successful_jobs"] == 0
    assert result.data["failed_jobs"] == 0
    assert context.get("render_results") == []


def test_custom_renderer_is_used() -> None:
    """Test that custom renderer is used when provided."""
    
    class CustomRenderer(Renderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            return {
                "job_id": str(request.job["job_id"]),
                "status": "custom_completed",
                "output_reference": "custom://output",
                "duration_seconds": 999,
            }
    
    executor = RenderJobExecutor(renderer=CustomRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [_render_jobs()[0]])
    
    result = executor.run(context)
    
    assert result.success is True
    job_result = result.data["render_results"][0]
    assert job_result["status"] == "custom_completed"
    assert job_result["output_reference"] == "custom://output"
    assert job_result["duration_seconds"] == 999


def test_invalid_job_not_dict_returns_failure() -> None:
    """Test that non-dict job in list returns failure."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", ["not a dict"])
    
    result = executor.run(context)
    
    assert result.success is False
    assert "must be a dictionary" in result.message


def test_empty_job_id_returns_failure() -> None:
    """Test that empty job_id returns failure."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", [
        {"job_id": "  ", "scene_number": 1, "duration_seconds": 45},
    ])
    
    result = executor.run(context)
    
    assert result.success is False
    assert "job_id cannot be empty" in result.message


def test_render_config_reaches_renderer() -> None:
    """Test that RenderConfig is passed to the renderer."""
    from src.models.content_package import RenderConfig
    
    received_requests = []
    
    class ConfigCapturingRenderer(Renderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            received_requests.append(request)
            return {
                "job_id": str(request.job["job_id"]),
                "status": "completed",
                "output_reference": f"mock://render/{request.job['job_id']}",
                "duration_seconds": int(request.job.get("duration_seconds", 0)),
            }
    
    executor = RenderJobExecutor(renderer=ConfigCapturingRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [_render_jobs()[0]])
    context.set("render_config", RenderConfig(width=1280, height=720, fps=60))
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(received_requests) == 1
    assert received_requests[0].render_config.width == 1280
    assert received_requests[0].render_config.height == 720
    assert received_requests[0].render_config.fps == 60


def test_asset_ids_are_resolved() -> None:
    """Test that asset IDs are resolved using the asset resolver."""
    from src.services.render_asset_resolver import LocalRenderAssetResolver
    
    received_requests = []
    
    class AssetCapturingRenderer(Renderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            received_requests.append(request)
            return {
                "job_id": str(request.job["job_id"]),
                "status": "completed",
                "output_reference": f"mock://render/{request.job['job_id']}",
                "duration_seconds": int(request.job.get("duration_seconds", 0)),
            }
    
    resolver = LocalRenderAssetResolver(asset_root="custom_assets")
    executor = RenderJobExecutor(
        renderer=AssetCapturingRenderer(),
        asset_resolver=resolver,
    )
    context = WorkflowContext()
    context.set("render_jobs", [{
        "job_id": "job-1",
        "scene_number": 1,
        "duration_seconds": 45,
        "asset_ids": ["asset1", "asset2"],
    }])
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(received_requests) == 1
    assert received_requests[0].resolved_assets == ["custom_assets/asset1", "custom_assets/asset2"]


def test_character_ids_are_resolved() -> None:
    """Test that character IDs are resolved using the asset resolver."""
    from src.services.render_asset_resolver import LocalRenderAssetResolver
    
    received_requests = []
    
    class CharacterCapturingRenderer(Renderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            received_requests.append(request)
            return {
                "job_id": str(request.job["job_id"]),
                "status": "completed",
                "output_reference": f"mock://render/{request.job['job_id']}",
                "duration_seconds": int(request.job.get("duration_seconds", 0)),
            }
    
    resolver = LocalRenderAssetResolver()
    executor = RenderJobExecutor(
        renderer=CharacterCapturingRenderer(),
        asset_resolver=resolver,
    )
    context = WorkflowContext()
    context.set("render_jobs", [{
        "job_id": "job-1",
        "scene_number": 1,
        "duration_seconds": 45,
        "character_ids": ["char_host", "char_guest"],
    }])
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(received_requests) == 1
    assert received_requests[0].resolved_characters == [
        "assets/characters/char_host",
        "assets/characters/char_guest",
    ]


def test_injected_resolver_is_called() -> None:
    """Test that injected resolver is actually called."""
    from src.services.render_asset_resolver import LocalRenderAssetResolver
    
    resolver = LocalRenderAssetResolver(asset_root="test_assets")
    executor = RenderJobExecutor(asset_resolver=resolver)
    
    # Verify resolver is stored
    assert executor.asset_resolver is resolver
    assert executor.asset_resolver.asset_root == "test_assets"


def test_job_with_no_assets_still_works() -> None:
    """Test that job with no assets or characters still works."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", [{
        "job_id": "job-1",
        "scene_number": 1,
        "duration_seconds": 45,
    }])
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(result.data["render_results"]) == 1
    assert result.data["render_results"][0]["status"] == "completed"


def test_mock_renderer_remains_deterministic_with_request() -> None:
    """Test that MockRenderer remains deterministic with RenderRequest."""
    renderer = MockRenderer()
    from src.models.content_package import RenderConfig
    
    request = RenderRequest(
        job={"job_id": "test-job", "duration_seconds": 30},
        render_config=RenderConfig(width=1920, height=1080),
        resolved_assets=["assets/asset1"],
        resolved_characters=["assets/characters/char1"],
    )
    
    # Call render multiple times
    result1 = renderer.render(request)
    result2 = renderer.render(request)
    result3 = renderer.render(request)
    
    # All results should be identical
    assert result1 == result2 == result3
    assert result1["job_id"] == "test-job"
    assert result1["status"] == "completed"
    assert result1["output_reference"] == "mock://render/test-job"
    assert result1["duration_seconds"] == 30


def test_existing_executor_behavior_remains_compatible() -> None:
    """Test that existing executor behavior remains compatible without resolver."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", _render_jobs())
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(result.data["render_results"]) == 2
    assert result.data["total_jobs"] == 2
    assert result.data["successful_jobs"] == 2
    assert result.data["failed_jobs"] == 0


def test_default_executor_uses_mock_renderer() -> None:
    """Test that default executor uses MockRenderer."""
    executor = RenderJobExecutor()
    
    # Verify the renderer is MockRenderer
    assert isinstance(executor.renderer, MockRenderer)


def test_injected_ffmpeg_renderer_is_used() -> None:
    """Test that injected FFmpegRenderer is used."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    
    ffmpeg_renderer = FFmpegRenderer(execute_enabled=False)
    executor = RenderJobExecutor(renderer=ffmpeg_renderer)
    
    # Verify the renderer is FFmpegRenderer
    assert executor.renderer is ffmpeg_renderer
    assert isinstance(executor.renderer, FFmpegRenderer)


def test_render_request_reaches_ffmpeg_renderer() -> None:
    """Test that RenderRequest reaches FFmpegRenderer correctly."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    
    received_requests = []
    
    class RequestCapturingRenderer(FFmpegRenderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            received_requests.append(request)
            return super().render(request)
    
    renderer = RequestCapturingRenderer(execute_enabled=False)
    executor = RenderJobExecutor(renderer=renderer)
    context = WorkflowContext()
    context.set("render_jobs", [_render_jobs()[0]])
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(received_requests) == 1
    assert received_requests[0].job["job_id"] == "render-scene-1"
    assert received_requests[0].render_config.width == 1920  # Default config


def test_ffmpeg_renderer_with_execute_disabled_does_not_execute() -> None:
    """Test that FFmpegRenderer with execute_enabled=False does not execute FFmpeg."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=False)
    mock_process = MagicMock()
    
    with patch("subprocess.run", return_value=mock_process) as mock_run, \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        executor = RenderJobExecutor(renderer=renderer)
        context = WorkflowContext()
        context.set("render_jobs", [_render_jobs()[0]])
        
        result = executor.run(context)
        
        assert result.success is True
        assert result.data["render_results"][0]["status"] == "command_built"
        mock_run.assert_not_called()


def test_mocked_successful_ffmpeg_renderer_result_reaches_executor() -> None:
    """Test that mocked successful FFmpeg renderer result reaches executor."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process), \
         patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        executor = RenderJobExecutor(renderer=renderer)
        context = WorkflowContext()
        context.set("render_jobs", [_render_jobs()[0]])
        
        result = executor.run(context)
        
        assert result.success is True
        assert result.data["render_results"][0]["status"] == "completed"
        assert result.data["render_results"][0]["job_id"] == "render-scene-1"


def test_mocked_ffmpeg_failure_becomes_failed_render_result() -> None:
    """Test that mocked FFmpeg failure becomes a failed render result."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    from unittest.mock import MagicMock
    
    renderer = FFmpegRenderer(execute_enabled=True)
    
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = "Error: invalid argument"
    
    with patch("subprocess.run", return_value=mock_process), \
         patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        
        executor = RenderJobExecutor(renderer=renderer)
        context = WorkflowContext()
        context.set("render_jobs", [_render_jobs()[0]])
        
        result = executor.run(context)
        
        assert result.success is True  # Executor succeeds even if render fails
        assert result.data["render_results"][0]["status"] == "failed"
        assert "return code 1" in result.data["render_results"][0]["error"]


def test_multiple_jobs_continue_when_one_ffmpeg_renderer_job_fails() -> None:
    """Test that multiple jobs continue correctly when one renderer job fails."""
    from src.services.ffmpeg_renderer import FFmpegRenderer
    
    class PartialFailingFFmpegRenderer(FFmpegRenderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            if request.job["job_id"] == "render-scene-1":
                # Simulate FFmpeg failure
                return {
                    "job_id": "render-scene-1",
                    "status": "failed",
                    "output_reference": None,
                    "duration_seconds": 0,
                    "error": "FFmpeg failed",
                }
            # For non-failing jobs, return completed status
            return {
                "job_id": str(request.job["job_id"]),
                "status": "completed",
                "output_reference": f"mock://render/{request.job['job_id']}",
                "duration_seconds": int(request.job.get("duration_seconds", 0)),
            }
    
    renderer = PartialFailingFFmpegRenderer(execute_enabled=False)
    executor = RenderJobExecutor(renderer=renderer)
    context = WorkflowContext()
    context.set("render_jobs", _render_jobs())
    
    result = executor.run(context)
    
    assert result.success is True
    assert len(result.data["render_results"]) == 2
    assert result.data["successful_jobs"] == 1
    assert result.data["failed_jobs"] == 1
    
    # First job should have failed
    assert result.data["render_results"][0]["status"] == "failed"
    assert "FFmpeg failed" in result.data["render_results"][0]["error"]
    
    # Second job should have succeeded
    assert result.data["render_results"][1]["status"] == "completed"


# --- Audio integration tests ---


def _job_with_audio(scene_number: int = 1) -> dict[str, object]:
    """Create a render job with an audio_request."""
    from src.models.content_package import AudioRequest

    return {
        "job_id": f"render-scene-{scene_number}",
        "scene_number": scene_number,
        "status": "pending",
        "duration_seconds": 45,
        "render_type": "host_footage",
        "visual_prompt": "Scene",
        "animation_instructions": "Fade in",
        "camera_instructions": "Wide shot",
        "audio_requirements": "Narration",
        "audio_request": AudioRequest(
            scene_number=scene_number,
            duration_seconds=45,
            narration_text="Test narration",
        ),
    }


def test_injected_audio_renderer_is_used() -> None:
    """Test that injected audio renderer is used."""
    from src.services.audio_renderer import MockAudioRenderer

    audio_renderer = MockAudioRenderer()
    executor = RenderJobExecutor(audio_renderer=audio_renderer)
    context = WorkflowContext()
    context.set("render_jobs", [_job_with_audio()])

    result = executor.run(context)

    assert result.success is True
    job_result = result.data["render_results"][0]
    assert "audio_result" in job_result
    assert job_result["audio_result"]["status"] == "completed"
    assert job_result["audio_result"]["audio_reference"] == "mock://audio/scene_1"


def test_audio_render_request_receives_correct_audio_request() -> None:
    """Test that AudioRenderRequest receives the correct AudioRequest."""
    from src.models.content_package import AudioRequest
    from src.services.audio_renderer import AudioRenderRequest, AudioRenderer

    received_requests = []

    class CapturingAudioRenderer(AudioRenderer):
        def render(self, request: AudioRenderRequest) -> dict[str, Any]:
            received_requests.append(request)
            return {
                "scene_number": request.audio_request.scene_number,
                "status": "completed",
                "audio_reference": f"mock://audio/scene_{request.audio_request.scene_number}",
                "duration_seconds": request.audio_request.duration_seconds,
            }

    audio = AudioRequest(scene_number=3, duration_seconds=30)
    executor = RenderJobExecutor(audio_renderer=CapturingAudioRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [{
        "job_id": "job-1",
        "scene_number": 3,
        "duration_seconds": 30,
        "audio_request": audio,
    }])

    result = executor.run(context)

    assert result.success is True
    assert len(received_requests) == 1
    assert received_requests[0].audio_request is audio
    assert received_requests[0].audio_request.scene_number == 3
    assert received_requests[0].job["job_id"] == "job-1"


def test_audio_result_reaches_render_result() -> None:
    """Test that audio result reaches the render result."""
    from src.services.audio_renderer import MockAudioRenderer

    executor = RenderJobExecutor(audio_renderer=MockAudioRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [_job_with_audio(scene_number=2)])

    result = executor.run(context)

    assert result.success is True
    job_result = result.data["render_results"][0]
    assert "audio_result" in job_result
    assert job_result["audio_result"]["scene_number"] == 2
    assert job_result["audio_result"]["audio_reference"] == "mock://audio/scene_2"


def test_job_without_audio_request_skips_audio_renderer() -> None:
    """Test that job without audio_request skips the audio renderer."""
    from src.services.audio_renderer import AudioRenderRequest, AudioRenderer

    calls = []

    class CountingAudioRenderer(AudioRenderer):
        def render(self, request: AudioRenderRequest) -> dict[str, Any]:
            calls.append(request)
            return {"status": "completed"}

    executor = RenderJobExecutor(audio_renderer=CountingAudioRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [_render_jobs()[0]])  # No audio_request

    result = executor.run(context)

    assert result.success is True
    assert len(calls) == 0
    assert "audio_result" not in result.data["render_results"][0]


def test_no_audio_renderer_preserves_existing_behavior() -> None:
    """Test that no audio renderer preserves existing behavior."""
    executor = RenderJobExecutor()
    context = WorkflowContext()
    context.set("render_jobs", [_job_with_audio()])

    result = executor.run(context)

    assert result.success is True
    job_result = result.data["render_results"][0]
    assert job_result["status"] == "completed"
    assert "audio_result" not in job_result


def test_audio_renderer_failure_does_not_destroy_video_result() -> None:
    """Test that audio renderer failure does not destroy successful video result."""
    from src.services.audio_renderer import AudioRenderRequest, AudioRenderer

    class FailingAudioRenderer(AudioRenderer):
        def render(self, request: AudioRenderRequest) -> dict[str, Any]:
            raise RuntimeError("Audio render failed")

    executor = RenderJobExecutor(audio_renderer=FailingAudioRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [_job_with_audio()])

    result = executor.run(context)

    assert result.success is True
    job_result = result.data["render_results"][0]
    # Video result preserved
    assert job_result["status"] == "completed"
    assert job_result["output_reference"] == "mock://render/render-scene-1"
    # Audio failure recorded
    assert "audio_result" in job_result
    assert job_result["audio_result"]["status"] == "failed"
    assert "Audio render failed" in job_result["audio_result"]["error"]


def test_tts_audio_renderer_flow_through_render_job_executor() -> None:
    """Test that RenderJobExecutor passes audio_request into TTSAudioRenderer."""
    from src.models.content_package import AudioRequest
    from src.services.tts_audio_renderer import TTSAudioRenderer
    from src.services.tts_service import MockTTSService

    executor = RenderJobExecutor(
        audio_renderer=TTSAudioRenderer(tts_service=MockTTSService()),
    )
    context = WorkflowContext()
    context.set("render_jobs", [{
        "job_id": "tts-scene-1",
        "scene_number": 1,
        "status": "pending",
        "duration_seconds": 45,
        "render_type": "host_footage",
        "visual_prompt": "Scene",
        "animation_instructions": "Fade in",
        "camera_instructions": "Wide shot",
        "audio_requirements": "Narration",
        "audio_request": AudioRequest(
            scene_number=1,
            duration_seconds=45,
            narration_text="Hello world",
            voice_reference="default",
            audio_format="wav",
        ),
    }])

    result = executor.run(context)

    assert result.success is True
    job_result = result.data["render_results"][0]
    assert "audio_result" in job_result
    assert job_result["audio_result"]["status"] == "completed"
    assert job_result["audio_result"]["audio_reference"].startswith("mock://tts/")


def test_audio_result_contains_correct_scene_number() -> None:
    """Test that audio result contains the correct scene number."""
    from src.services.audio_renderer import MockAudioRenderer

    executor = RenderJobExecutor(audio_renderer=MockAudioRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [_job_with_audio(scene_number=5)])

    result = executor.run(context)

    assert result.success is True
    job_result = result.data["render_results"][0]
    assert job_result["audio_result"]["scene_number"] == 5


def test_multiple_jobs_render_audio_independently() -> None:
    """Test that multiple jobs render their audio independently."""
    from src.services.audio_renderer import MockAudioRenderer

    executor = RenderJobExecutor(audio_renderer=MockAudioRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [
        _job_with_audio(scene_number=1),
        _job_with_audio(scene_number=2),
    ])

    result = executor.run(context)

    assert result.success is True
    assert len(result.data["render_results"]) == 2

    job1 = result.data["render_results"][0]
    job2 = result.data["render_results"][1]

    assert job1["audio_result"]["audio_reference"] == "mock://audio/scene_1"
    assert job2["audio_result"]["audio_reference"] == "mock://audio/scene_2"
    assert job1["audio_result"]["scene_number"] == 1
    assert job2["audio_result"]["scene_number"] == 2
