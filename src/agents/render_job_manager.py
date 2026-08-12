"""Render Job Manager Agent.

Validates render job plans and creates execution-ready render job representations.
"""

from __future__ import annotations

from typing import Any

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext


class RenderJobManager(BaseAgent):
    """Validates render job plans and prepares execution-ready render jobs."""

    def __init__(self) -> None:
        super().__init__("RenderJobManager")

    def run(self, context: WorkflowContext) -> AgentResult:
        """Validate render job plan and create execution-ready render jobs.
        
        Args:
            context: Workflow context containing render_job_plan
            
        Returns:
            AgentResult with render_jobs list or error message
        """
        self.start()
        
        # Step 1: Check if render_job_plan exists in context
        if not context.has("render_job_plan"):
            self.finish()
            return AgentResult.fail("render_job_plan not found in workflow context")
        
        render_job_plan = context.get("render_job_plan")
        
        # Step 2: Validate render_job_plan structure
        if not isinstance(render_job_plan, dict):
            self.finish()
            return AgentResult.fail("render_job_plan must be a dictionary")
        
        # Step 3: Check if jobs list exists
        jobs_data = render_job_plan.get("jobs")
        if jobs_data is None:
            self.finish()
            return AgentResult.fail("render_job_plan.jobs is missing")
        
        if not isinstance(jobs_data, list):
            self.finish()
            return AgentResult.fail("render_job_plan.jobs must be a list")
        
        # Step 4: Validate each job
        validation_errors = self._validate_jobs(jobs_data)
        if validation_errors:
            self.finish()
            return AgentResult.fail(f"Invalid render jobs: {'; '.join(validation_errors)}")
        
        # Step 5: Create execution-ready render jobs
        render_jobs = self._create_execution_jobs(jobs_data)
        
        # Step 6: Store in context
        context.set("render_jobs", render_jobs)
        
        self.log(f"Prepared {len(render_jobs)} execution-ready render jobs")
        self.finish()
        
        return AgentResult.ok(
            render_jobs=render_jobs,
            total_jobs=len(render_jobs),
        )

    def _validate_jobs(self, jobs_data: list[dict[str, Any]]) -> list[str]:
        """Validate all jobs in the render job plan.
        
        Args:
            jobs_data: List of job dictionaries from render_job_plan
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        for idx, job_data in enumerate(jobs_data):
            job_prefix = f"Job {idx}"
            
            # Check if job_id exists
            if not isinstance(job_data, dict):
                errors.append(f"{job_prefix}: must be a dictionary")
                continue
            
            if "job_id" not in job_data:
                errors.append(f"{job_prefix}: missing job_id")
            elif not str(job_data["job_id"]).strip():
                errors.append(f"{job_prefix}: job_id cannot be empty")
            
            # Validate scene_number
            if "scene_number" not in job_data:
                errors.append(f"{job_prefix}: missing scene_number")
            else:
                scene_number = job_data["scene_number"]
                if not isinstance(scene_number, int) or scene_number < 1:
                    errors.append(f"{job_prefix}: scene_number must be a positive integer")
            
            # Validate duration_seconds
            if "duration_seconds" not in job_data:
                errors.append(f"{job_prefix}: missing duration_seconds")
            else:
                duration = job_data["duration_seconds"]
                if not isinstance(duration, (int, float)) or duration < 0:
                    errors.append(f"{job_prefix}: duration_seconds must be non-negative")
        
        return errors

    def _create_execution_jobs(self, jobs_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create execution-ready render job representations.
        
        Args:
            jobs_data: List of validated job dictionaries
            
        Returns:
            List of execution-ready render job dictionaries
        """
        execution_jobs = []
        
        for job_data in jobs_data:
            execution_job = {
                "job_id": str(job_data["job_id"]),
                "scene_number": int(job_data["scene_number"]),
                "status": "pending",
                "duration_seconds": int(job_data["duration_seconds"]),
                "render_type": str(job_data.get("render_type", "host_footage")),
                "visual_prompt": str(job_data.get("visual_prompt", "")),
                "animation_instructions": str(job_data.get("animation_instructions", "")),
                "camera_instructions": str(job_data.get("camera_instructions", "")),
                "audio_requirements": str(job_data.get("audio_requirements", "")),
            }
            execution_jobs.append(execution_job)
        
        return execution_jobs