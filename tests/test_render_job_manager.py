"""Tests for RenderJobManager agent."""

from __future__ import annotations

from src.agents.render_job_manager import RenderJobManager
from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext


def _render_job_plan_with_jobs() -> dict[str, object]:
    """Create a valid render job plan with multiple jobs."""
    return {
        "total_jobs": 2,
        "jobs": [
            {
                "job_id": "render-scene-1",
                "scene_number": 1,
                "duration_seconds": 45,
                "render_type": "host_footage",
                "character_ids": ["char-host"],
                "asset_ids": ["asset-scene-1"],
                "visual_prompt": "Scene 1: Opening shot with host",
                "animation_instructions": "Fade in from black",
                "camera_instructions": "Wide establishing shot",
                "audio_requirements": "Narration: Welcome to the video",
            },
            {
                "job_id": "render-scene-2",
                "scene_number": 2,
                "duration_seconds": 90,
                "render_type": "b-roll",
                "character_ids": ["char-host"],
                "asset_ids": ["asset-scene-2"],
                "visual_prompt": "Scene 2: B-roll examples",
                "animation_instructions": "Ken Burns effect",
                "camera_instructions": "Static medium shot",
                "audio_requirements": "Narration: Here is why this matters",
            },
        ],
        "total_duration_seconds": 135,
    }


def test_valid_render_plan_creates_execution_jobs() -> None:
    """Test that a valid render job plan creates execution-ready jobs."""
    manager = RenderJobManager()
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan_with_jobs())
    
    result = manager.run(context)
    
    assert result.success is True
    assert "render_jobs" in result.data
    assert result.data["total_jobs"] == 2
    assert len(result.data["render_jobs"]) == 2
    
    # Verify first job structure
    job1 = result.data["render_jobs"][0]
    assert job1["job_id"] == "render-scene-1"
    assert job1["scene_number"] == 1
    assert job1["status"] == "pending"
    assert job1["duration_seconds"] == 45
    assert job1["render_type"] == "host_footage"
    assert job1["visual_prompt"] == "Scene 1: Opening shot with host"
    assert job1["animation_instructions"] == "Fade in from black"
    assert job1["camera_instructions"] == "Wide establishing shot"
    assert job1["audio_requirements"] == "Narration: Welcome to the video"
    
    # Verify second job structure
    job2 = result.data["render_jobs"][1]
    assert job2["job_id"] == "render-scene-2"
    assert job2["scene_number"] == 2
    assert job2["status"] == "pending"
    assert job2["duration_seconds"] == 90
    assert job2["render_type"] == "b-roll"
    
    # Verify context was updated
    assert context.has("render_jobs")
    assert context.get("render_jobs") == result.data["render_jobs"]


def test_missing_render_plan_returns_failure() -> None:
    """Test that missing render_job_plan returns failure."""
    manager = RenderJobManager()
    context = WorkflowContext()
    
    result = manager.run(context)
    
    assert result.success is False
    assert "render_job_plan not found" in result.message


def test_invalid_job_data_returns_failure() -> None:
    """Test that invalid job data returns failure."""
    manager = RenderJobManager()
    
    # Test missing job_id
    context1 = WorkflowContext()
    context1.set("render_job_plan", {
        "jobs": [
            {"scene_number": 1, "duration_seconds": 45},
        ]
    })
    result1 = manager.run(context1)
    assert result1.success is False
    assert "missing job_id" in result1.message
    
    # Test invalid scene_number
    context2 = WorkflowContext()
    context2.set("render_job_plan", {
        "jobs": [
            {"job_id": "job-1", "scene_number": 0, "duration_seconds": 45},
        ]
    })
    result2 = manager.run(context2)
    assert result2.success is False
    assert "scene_number must be a positive integer" in result2.message
    
    # Test negative duration
    context3 = WorkflowContext()
    context3.set("render_job_plan", {
        "jobs": [
            {"job_id": "job-1", "scene_number": 1, "duration_seconds": -10},
        ]
    })
    result3 = manager.run(context3)
    assert result3.success is False
    assert "duration_seconds must be non-negative" in result3.message
    
    # Test missing jobs list
    context4 = WorkflowContext()
    context4.set("render_job_plan", {"total_jobs": 0})
    result4 = manager.run(context4)
    assert result4.success is False
    assert "jobs is missing" in result4.message


def test_correct_number_of_execution_jobs() -> None:
    """Test that the correct number of execution jobs are created."""
    manager = RenderJobManager()
    
    # Test with 3 jobs
    context = WorkflowContext()
    context.set("render_job_plan", {
        "total_jobs": 3,
        "jobs": [
            {"job_id": f"job-{i}", "scene_number": i, "duration_seconds": i * 10}
            for i in range(1, 4)
        ],
        "total_duration_seconds": 60,
    })
    
    result = manager.run(context)
    
    assert result.success is True
    assert len(result.data["render_jobs"]) == 3
    assert result.data["total_jobs"] == 3
    
    # Verify all jobs have pending status
    for job in result.data["render_jobs"]:
        assert job["status"] == "pending"


def test_context_output_contains_render_jobs() -> None:
    """Test that context output contains render_jobs with correct structure."""
    manager = RenderJobManager()
    context = WorkflowContext()
    context.set("render_job_plan", _render_job_plan_with_jobs())
    
    result = manager.run(context)
    
    assert result.success is True
    assert context.has("render_jobs")
    
    render_jobs = context.get("render_jobs")
    assert isinstance(render_jobs, list)
    assert len(render_jobs) == 2
    
    # Verify all jobs have required fields
    for job in render_jobs:
        assert "job_id" in job
        assert "scene_number" in job
        assert "status" in job
        assert "duration_seconds" in job
        assert "render_type" in job
        assert "visual_prompt" in job
        assert "animation_instructions" in job
        assert "camera_instructions" in job
        assert "audio_requirements" in job
        assert job["status"] == "pending"


def test_zero_duration_job_is_valid() -> None:
    """Test that zero duration jobs are valid (non-negative includes zero)."""
    manager = RenderJobManager()
    context = WorkflowContext()
    context.set("render_job_plan", {
        "jobs": [
            {"job_id": "job-1", "scene_number": 1, "duration_seconds": 0},
        ]
    })
    
    result = manager.run(context)
    
    assert result.success is True
    assert result.data["render_jobs"][0]["duration_seconds"] == 0


def test_empty_jobs_list_creates_empty_render_jobs() -> None:
    """Test that empty jobs list creates empty render_jobs list."""
    manager = RenderJobManager()
    context = WorkflowContext()
    context.set("render_job_plan", {
        "total_jobs": 0,
        "jobs": [],
        "total_duration_seconds": 0,
    })
    
    result = manager.run(context)
    
    assert result.success is True
    assert len(result.data["render_jobs"]) == 0
    assert result.data["total_jobs"] == 0
    assert context.get("render_jobs") == []


def test_render_job_plan_not_dict_returns_failure() -> None:
    """Test that non-dict render_job_plan returns failure."""
    manager = RenderJobManager()
    context = WorkflowContext()
    context.set("render_job_plan", "invalid")
    
    result = manager.run(context)
    
    assert result.success is False
    assert "must be a dictionary" in result.message


def test_jobs_not_list_returns_failure() -> None:
    """Test that non-list jobs field returns failure."""
    manager = RenderJobManager()
    context = WorkflowContext()
    context.set("render_job_plan", {
        "jobs": "not a list"
    })
    
    result = manager.run(context)
    
    assert result.success is False
    assert "jobs must be a list" in result.message