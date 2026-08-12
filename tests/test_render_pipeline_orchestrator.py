"""Tests for RenderPipelineOrchestrator agent."""

from __future__ import annotations

from typing import Any

from src.agents.render_job_executor import MockRenderer, RenderJobExecutor, RenderRequest
from src.agents.render_job_manager import RenderJobManager
from src.agents.render_output_manager import RenderOutputManager
from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext


def _render_job_plan() -> dict[str, Any]:
    """Create a valid render job plan."""
    return {
        "total_jobs": 2,
        "jobs": [
            {
                "job_id": "render-scene-1",
                "scene_number": 1,
                "duration_seconds": 45,
                "render_type": "host_footage",
                "visual_prompt": "Scene 1",
                "animation_instructions": "Fade in",
                "camera_instructions": "Wide shot",
                "audio_requirements": "Narration",
            },
            {
                "job_id": "render-scene-2",
                "scene_number": 2,
                "duration_seconds": 90,
                "render_type": "b-roll",
                "visual_prompt": "Scene 2",
                "animation_instructions": "Ken Burns",
                "camera_instructions": "Static shot",
                "audio_requirements": "Music",
            },
        ],
        "total_duration_seconds": 135,
    }


def test_successful_complete_pipeline() -> None:
    """Test successful execution of the complete render pipeline."""
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    
    result = orchestrator.run(context)
    
    assert result.success is True
    assert "render_outputs" in result.data
    assert result.data["total_outputs"] == 2
    assert len(result.data["render_outputs"]) == 2
    
    # Verify all outputs were created
    output1 = result.data["render_outputs"][0]
    assert output1["output_id"] == "output_render-scene-1"
    assert output1["status"] == "completed"
    
    output2 = result.data["render_outputs"][1]
    assert output2["output_id"] == "output_render-scene-2"
    assert output2["status"] == "completed"


def test_render_job_manager_failure_stops_pipeline() -> None:
    """Test that RenderJobManager failure stops the pipeline."""
    class FailingManager(RenderJobManager):
        def run(self, context: WorkflowContext) -> AgentResult:
            return AgentResult.fail("Manager failed")
    
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=FailingManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    
    result = orchestrator.run(context)
    
    assert result.success is False
    assert "Manager failed" in result.message
    assert not context.has("render_jobs")
    assert not context.has("render_results")
    assert not context.has("render_outputs")


def test_render_job_executor_failure_stops_pipeline() -> None:
    """Test that RenderJobExecutor failure stops the pipeline."""
    class FailingExecutor(RenderJobExecutor):
        def run(self, context: WorkflowContext) -> AgentResult:
            return AgentResult.fail("Executor failed")
    
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=FailingExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    
    result = orchestrator.run(context)
    
    assert result.success is False
    assert "Executor failed" in result.message
    assert not context.has("render_results")
    assert not context.has("render_outputs")


def test_render_output_manager_failure_is_propagated() -> None:
    """Test that RenderOutputManager failure is propagated."""
    class FailingOutputManager(RenderOutputManager):
        def run(self, context: WorkflowContext) -> AgentResult:
            return AgentResult.fail("Output manager failed")
    
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=FailingOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    
    result = orchestrator.run(context)
    
    assert result.success is False
    assert "Output manager failed" in result.message


def test_same_workflow_context_passed_through_all_stages() -> None:
    """Test that the same WorkflowContext is passed through all stages."""
    context_used_in_stages = []
    
    class TrackingManager(RenderJobManager):
        def run(self, context: WorkflowContext) -> AgentResult:
            context_used_in_stages.append(("manager", id(context)))
            return super().run(context)
    
    class TrackingExecutor(RenderJobExecutor):
        def run(self, context: WorkflowContext) -> AgentResult:
            context_used_in_stages.append(("executor", id(context)))
            return super().run(context)
    
    class TrackingOutputManager(RenderOutputManager):
        def run(self, context: WorkflowContext) -> AgentResult:
            context_used_in_stages.append(("output_manager", id(context)))
            return super().run(context)
    
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=TrackingManager(),
        render_job_executor=TrackingExecutor(),
        render_output_manager=TrackingOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    original_context_id = id(context)
    
    result = orchestrator.run(context)
    
    assert result.success is True
    assert len(context_used_in_stages) == 3
    
    # Verify all stages received the same context object
    for stage_name, context_id in context_used_in_stages:
        assert context_id == original_context_id, f"{stage_name} received different context"


def test_final_render_outputs_are_returned() -> None:
    """Test that final render_outputs are returned in the result."""
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    
    result = orchestrator.run(context)
    
    assert result.success is True
    assert result.data["render_outputs"] == context.get("render_outputs")
    assert len(result.data["render_outputs"]) == 2


def test_empty_pipeline_behavior() -> None:
    """Test pipeline behavior with empty jobs list."""
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", {
        "total_jobs": 0,
        "jobs": [],
        "total_duration_seconds": 0,
    })
    
    result = orchestrator.run(context)
    
    assert result.success is True
    assert result.data["total_outputs"] == 0
    assert len(result.data["render_outputs"]) == 0
    assert context.get("render_outputs") == []


def test_pipeline_preserves_context_data() -> None:
    """Test that pipeline preserves existing context data."""
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    context.set("existing_data", "should be preserved")
    context.set("another_key", 42)
    
    result = orchestrator.run(context)
    
    assert result.success is True
    assert context.get("existing_data") == "should be preserved"
    assert context.get("another_key") == 42
    assert context.has("render_outputs")


def test_orchestrator_uses_injected_dependencies() -> None:
    """Test that orchestrator uses injected dependencies."""
    custom_manager = RenderJobManager()
    custom_executor = RenderJobExecutor()
    custom_output_manager = RenderOutputManager()
    
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=custom_manager,
        render_job_executor=custom_executor,
        render_output_manager=custom_output_manager,
    )
    
    assert orchestrator.render_job_manager is custom_manager
    assert orchestrator.render_job_executor is custom_executor
    assert orchestrator.render_output_manager is custom_output_manager


def test_missing_render_job_plan_stops_pipeline() -> None:
    """Test that missing render_job_plan stops the pipeline at manager stage."""
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    # Not setting render_job_plan
    
    result = orchestrator.run(context)
    
    assert result.success is False
    assert "render_job_plan not found" in result.message
    assert not context.has("render_outputs")


def test_pipeline_with_failed_render_jobs() -> None:
    """Test pipeline with some failed render jobs."""
    
    class PartialFailingRenderer(MockRenderer):
        def render(self, request: RenderRequest) -> dict[str, Any]:
            if request.job["job_id"] == "render-scene-1":
                raise RuntimeError("Render failed")
            return super().render(request)
    
    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(renderer=PartialFailingRenderer()),
        render_output_manager=RenderOutputManager(),
    )
    
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan())
    
    result = orchestrator.run(context)
    
    assert result.success is True
    assert result.data["total_outputs"] == 2
    
    # First output should be failed
    output1 = result.data["render_outputs"][0]
    assert output1["job_id"] == "render-scene-1"
    assert output1["status"] == "failed"
    
    # Second output should be completed
    output2 = result.data["render_outputs"][1]
    assert output2["job_id"] == "render-scene-2"
    assert output2["status"] == "completed"


def test_pipeline_invokes_final_media_orchestrator_when_enabled() -> None:
    """Test that final media orchestration is invoked when configured."""
    calls: list[dict[str, Any]] = []

    class CapturingFinalMediaOrchestrator:
        def create_final_media(self, render_outputs: list[dict[str, Any]], audio_requests: list[Any], output_path: str) -> dict[str, Any]:
            calls.append({
                "render_outputs": render_outputs,
                "audio_requests": audio_requests,
                "output_path": output_path,
            })
            return {"status": "completed", "output_path": output_path}

    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
        final_media_orchestrator=CapturingFinalMediaOrchestrator(),
    )

    context = WorkflowContext()
    context.set("run_final_media_generation", True)
    context.set("final_media_output_path", "output/final.mp4")
    context.set("render_job_plan", {
        "total_jobs": 1,
        "jobs": [{
            "job_id": "render-scene-1",
            "scene_number": 1,
            "duration_seconds": 15,
            "render_type": "host_footage",
            "visual_prompt": "Scene 1",
            "animation_instructions": "Fade in",
            "camera_instructions": "Wide shot",
            "audio_requirements": "Narration",
            "audio_request": {
                "scene_number": 1,
                "duration_seconds": 15,
                "narration_text": "Hello world",
                "voice_reference": "default",
                "background_music_reference": "",
                "sound_effect_references": [],
                "audio_format": "wav",
            },
        }],
        "total_duration_seconds": 15,
    })

    result = orchestrator.run(context)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["output_path"] == "output/final.mp4"
    assert len(calls[0]["render_outputs"]) == 1
    assert calls[0]["audio_requests"][0].narration_text == "Hello world"
    assert context.get("final_media_result")["status"] == "completed"
    assert result.data["final_media_result"]["status"] == "completed"


def test_final_media_failure_preserves_render_outputs() -> None:
    """Test that if FinalMediaOrchestrator raises an exception, render outputs are not corrupted."""
    class FailingFinalMediaOrchestrator:
        def create_final_media(self, render_outputs: list[dict[str, Any]], audio_requests: list[Any], output_path: str) -> dict[str, Any]:
            raise ValueError("Something went terribly wrong")

    orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
        final_media_orchestrator=FailingFinalMediaOrchestrator(),
    )

    context = WorkflowContext()
    context.set("run_final_media_generation", True)
    context.set("final_media_output_path", "output/final.mp4")
    context.set("render_job_plan", {
        "total_jobs": 1,
        "jobs": [{
            "job_id": "render-scene-1",
            "scene_number": 1,
            "duration_seconds": 15,
            "render_type": "host_footage",
            "audio_request": {
                "scene_number": 1,
                "duration_seconds": 15,
                "narration_text": "Hello world",
                "voice_reference": "default",
                "background_music_reference": "",
                "sound_effect_references": [],
                "audio_format": "wav",
            },
        }],
        "total_duration_seconds": 15,
    })

    result = orchestrator.run(context)

    assert result.success is True
    # Render outputs should still be intact
    assert len(result.data["render_outputs"]) == 1
    # Final media result should indicate failure
    assert context.get("final_media_result")["status"] == "failed"
    assert "Something went terribly wrong" in context.get("final_media_result")["error"]
    assert result.data["final_media_result"]["status"] == "failed"