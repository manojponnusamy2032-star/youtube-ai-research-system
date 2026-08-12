"""Tests for RenderOutputManager agent."""

from __future__ import annotations

from src.agents.render_output_manager import RenderOutputManager
from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext


def _render_results() -> list[dict[str, object]]:
    """Create valid render results for testing."""
    return [
        {
            "job_id": "render-scene-1",
            "status": "completed",
            "output_reference": "mock://render/render-scene-1",
            "duration_seconds": 45,
        },
        {
            "job_id": "render-scene-2",
            "status": "completed",
            "output_reference": "mock://render/render-scene-2",
            "duration_seconds": 90,
        },
        {
            "job_id": "render-scene-3",
            "status": "failed",
            "output_reference": None,
            "duration_seconds": 0,
            "error": "Render failed",
        },
    ]


def test_successful_output_normalization() -> None:
    """Test successful normalization of render results."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", [_render_results()[0]])
    
    result = manager.run(context)
    
    assert result.success is True
    assert "render_outputs" in result.data
    assert len(result.data["render_outputs"]) == 1
    
    output = result.data["render_outputs"][0]
    assert output["output_id"] == "output_render-scene-1"
    assert output["job_id"] == "render-scene-1"
    assert output["status"] == "completed"
    assert output["output_reference"] == "mock://render/render-scene-1"
    assert output["duration_seconds"] == 45


def test_multiple_outputs() -> None:
    """Test normalization of multiple render results."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", _render_results())
    
    result = manager.run(context)
    
    assert result.success is True
    assert len(result.data["render_outputs"]) == 3
    assert result.data["total_outputs"] == 3
    assert result.data["successful_outputs"] == 2
    assert result.data["failed_outputs"] == 1
    
    # Verify all outputs have correct structure
    output1 = result.data["render_outputs"][0]
    assert output1["output_id"] == "output_render-scene-1"
    assert output1["status"] == "completed"
    
    output2 = result.data["render_outputs"][1]
    assert output2["output_id"] == "output_render-scene-2"
    assert output2["status"] == "completed"
    
    output3 = result.data["render_outputs"][2]
    assert output3["output_id"] == "output_render-scene-3"
    assert output3["status"] == "failed"
    assert output3["output_reference"] is None


def test_missing_render_results_returns_failure() -> None:
    """Test that missing render_results returns failure."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    
    result = manager.run(context)
    
    assert result.success is False
    assert "render_results not found" in result.message


def test_non_list_render_results_returns_failure() -> None:
    """Test that non-list render_results returns failure."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", "not a list")
    
    result = manager.run(context)
    
    assert result.success is False
    assert "render_results must be a list" in result.message


def test_invalid_result_without_job_id_returns_failure() -> None:
    """Test that invalid result without job_id returns failure."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", [
        {"status": "completed", "output_reference": "mock://render/test"},
    ])
    
    result = manager.run(context)
    
    assert result.success is False
    assert "missing job_id" in result.message


def test_deterministic_output_id() -> None:
    """Test that output_id is deterministic and follows expected format."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", [
        {
            "job_id": "test-job-123",
            "status": "completed",
            "output_reference": "mock://render/test-job-123",
            "duration_seconds": 30,
        },
    ])
    
    result = manager.run(context)
    
    assert result.success is True
    output = result.data["render_outputs"][0]
    assert output["output_id"] == "output_test-job-123"


def test_successful_and_failed_output_counts() -> None:
    """Test that successful and failed output counts are correct."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", [
        {
            "job_id": "job-1",
            "status": "completed",
            "output_reference": "mock://render/job-1",
            "duration_seconds": 10,
        },
        {
            "job_id": "job-2",
            "status": "failed",
            "output_reference": None,
            "duration_seconds": 0,
            "error": "Failed",
        },
        {
            "job_id": "job-3",
            "status": "completed",
            "output_reference": "mock://render/job-3",
            "duration_seconds": 20,
        },
        {
            "job_id": "job-4",
            "status": "failed",
            "output_reference": None,
            "duration_seconds": 0,
            "error": "Error",
        },
    ])
    
    result = manager.run(context)
    
    assert result.success is True
    assert result.data["total_outputs"] == 4
    assert result.data["successful_outputs"] == 2
    assert result.data["failed_outputs"] == 2


def test_correct_workflow_context_output() -> None:
    """Test that render_outputs are correctly stored in WorkflowContext."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", _render_results())
    
    result = manager.run(context)
    
    assert result.success is True
    assert context.has("render_outputs")
    
    render_outputs = context.get("render_outputs")
    assert isinstance(render_outputs, list)
    assert len(render_outputs) == 3
    
    # Verify structure of all outputs
    for output in render_outputs:
        assert "output_id" in output
        assert "job_id" in output
        assert "status" in output
        assert "output_reference" in output
        assert "duration_seconds" in output
        assert output["output_id"].startswith("output_")


def test_empty_result_list() -> None:
    """Test that empty result list is handled correctly."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", [])
    
    result = manager.run(context)
    
    assert result.success is True
    assert len(result.data["render_outputs"]) == 0
    assert result.data["total_outputs"] == 0
    assert result.data["successful_outputs"] == 0
    assert result.data["failed_outputs"] == 0
    assert context.get("render_outputs") == []


def test_invalid_result_not_dict_returns_failure() -> None:
    """Test that non-dict result in list returns failure."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", ["not a dict"])
    
    result = manager.run(context)
    
    assert result.success is False
    assert "must be a dictionary" in result.message


def test_empty_job_id_returns_failure() -> None:
    """Test that empty job_id returns failure."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", [
        {"job_id": "  ", "status": "completed", "output_reference": "mock://render/test", "duration_seconds": 10},
    ])
    
    result = manager.run(context)
    
    assert result.success is False
    assert "job_id cannot be empty" in result.message


def test_output_preserves_all_required_fields() -> None:
    """Test that normalized output preserves all required fields from input."""
    manager = RenderOutputManager()
    context = WorkflowContext()
    context.set("render_results", [
        {
            "job_id": "job-1",
            "status": "completed",
            "output_reference": "mock://render/job-1",
            "duration_seconds": 45,
            "extra_field": "should be ignored",
        },
    ])
    
    result = manager.run(context)
    
    assert result.success is True
    output = result.data["render_outputs"][0]
    
    # Verify required fields are present
    assert "output_id" in output
    assert "job_id" in output
    assert "status" in output
    assert "output_reference" in output
    assert "duration_seconds" in output
    
    # Verify values
    assert output["job_id"] == "job-1"
    assert output["status"] == "completed"
    assert output["output_reference"] == "mock://render/job-1"
    assert output["duration_seconds"] == 45
    assert output["output_id"] == "output_job-1"