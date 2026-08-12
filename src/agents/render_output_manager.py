"""Render Output Manager Agent.

Normalizes and tracks outputs produced by RenderJobExecutor.
"""

from __future__ import annotations

from typing import Any

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext


class RenderOutputManager(BaseAgent):
    """Normalizes render results into tracked output records."""

    def __init__(self) -> None:
        super().__init__("RenderOutputManager")

    def run(self, context: WorkflowContext) -> AgentResult:
        """Normalize render results and store output records.
        
        Args:
            context: Workflow context containing render_results
            
        Returns:
            AgentResult with render_outputs list or error message
        """
        self.start()
        
        # Step 1: Validate render_results exists
        if not context.has("render_results"):
            self.finish()
            return AgentResult.fail("render_results not found in workflow context")
        
        render_results = context.get("render_results")
        
        # Step 2: Validate render_results is a list
        if not isinstance(render_results, list):
            self.finish()
            return AgentResult.fail("render_results must be a list")
        
        # Step 3: Validate each result is a dictionary with job_id
        validation_errors = self._validate_results(render_results)
        if validation_errors:
            self.finish()
            return AgentResult.fail(f"Invalid render results: {'; '.join(validation_errors)}")
        
        # Step 4: Normalize results into output records
        render_outputs = self._normalize_outputs(render_results)
        
        # Step 5: Store normalized outputs in context
        context.set("render_outputs", render_outputs)
        
        successful = sum(1 for o in render_outputs if o["status"] == "completed")
        failed = sum(1 for o in render_outputs if o["status"] == "failed")
        
        self.log(f"Normalized {len(render_outputs)} render outputs: {successful} succeeded, {failed} failed")
        self.finish()
        
        return AgentResult.ok(
            render_outputs=render_outputs,
            total_outputs=len(render_outputs),
            successful_outputs=successful,
            failed_outputs=failed,
        )

    def _validate_results(self, render_results: list[Any]) -> list[str]:
        """Validate all render results.
        
        Args:
            render_results: List of render result dictionaries
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        for idx, result in enumerate(render_results):
            result_prefix = f"Result {idx}"
            
            if not isinstance(result, dict):
                errors.append(f"{result_prefix}: must be a dictionary")
                continue
            
            if "job_id" not in result:
                errors.append(f"{result_prefix}: missing job_id")
            elif not str(result["job_id"]).strip():
                errors.append(f"{result_prefix}: job_id cannot be empty")
        
        return errors

    def _normalize_outputs(self, render_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize render results into output records.
        
        Args:
            render_results: List of validated render result dictionaries
            
        Returns:
            List of normalized output record dictionaries
        """
        outputs = []
        
        for result in render_results:
            job_id = str(result["job_id"])
            
            output_record = {
                "output_id": f"output_{job_id}",
                "job_id": job_id,
                "status": str(result.get("status", "unknown")),
                "output_reference": result.get("output_reference"),
                "duration_seconds": int(result.get("duration_seconds", 0)),
                "scene_number": result.get("scene_number"),
            }
            
            outputs.append(output_record)
        
        return outputs