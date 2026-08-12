"""Render Pipeline Orchestrator Agent.

Coordinates the render pipeline stages in order:
RenderJobManager → RenderJobExecutor → RenderOutputManager
"""

from __future__ import annotations

from typing import Any

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.models.content_package import AudioRequest


class RenderPipelineOrchestrator(BaseAgent):
    """Orchestrates the render pipeline stages."""

    def __init__(
        self,
        render_job_manager: BaseAgent,
        render_job_executor: BaseAgent,
        render_output_manager: BaseAgent,
        final_media_orchestrator: Any | None = None,
    ) -> None:
        super().__init__("RenderPipelineOrchestrator")
        self.render_job_manager = render_job_manager
        self.render_job_executor = render_job_executor
        self.render_output_manager = render_output_manager
        self.final_media_orchestrator = final_media_orchestrator

    def run(self, context: WorkflowContext) -> AgentResult:
        """Execute the render pipeline in order.
        
        Args:
            context: Workflow context to pass through all stages
            
        Returns:
            AgentResult with final render_outputs or error message
        """
        self.start()
        
        # Stage 1: RenderJobManager
        manager_result = self.render_job_manager.run(context)
        if isinstance(manager_result, AgentResult) and not manager_result.success:
            self.finish()
            return manager_result
        
        # Stage 2: RenderJobExecutor
        executor_result = self.render_job_executor.run(context)
        if isinstance(executor_result, AgentResult) and not executor_result.success:
            self.finish()
            return executor_result
        
        # Stage 3: RenderOutputManager
        output_manager_result = self.render_output_manager.run(context)
        if isinstance(output_manager_result, AgentResult) and not output_manager_result.success:
            self.finish()
            return output_manager_result
        
        # Extract final render_outputs
        render_outputs = context.get("render_outputs", [])
        final_media_result = self._maybe_create_final_media(context, render_outputs)
        
        self.log(f"Render pipeline completed successfully with {len(render_outputs)} outputs")
        self.finish()
        
        result_data: dict[str, Any] = {
            "render_outputs": render_outputs,
            "total_outputs": len(render_outputs),
        }
        if final_media_result is not None:
            result_data["final_media_result"] = final_media_result
        
        return AgentResult.ok(**result_data)

    def _maybe_create_final_media(self, context: WorkflowContext, render_outputs: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Invoke the final media orchestrator when final media generation is enabled."""
        if self.final_media_orchestrator is None:
            return None
        if not context.get("run_final_media_generation", False):
            return None

        output_path = self._get_final_output_path(context)
        if not output_path:
            return None

        audio_requests = self._extract_audio_requests(context)
        if not audio_requests or not render_outputs:
            return None

        try:
            final_media_result = self.final_media_orchestrator.create_final_media(
                render_outputs=render_outputs,
                audio_requests=audio_requests,
                output_path=output_path,
            )
            context.set("final_media_result", final_media_result)
            return final_media_result
        except Exception as e:
            error_result = {"status": "failed", "error": str(e)}
            context.set("final_media_result", error_result)
            return error_result

    def _extract_audio_requests(self, context: WorkflowContext) -> list[AudioRequest]:
        """Extract audio requests from explicit context or render_job_plan jobs."""
        audio_requests = context.get("audio_requests")
        if isinstance(audio_requests, list):
            return [request for request in audio_requests if isinstance(request, AudioRequest)]

        render_job_plan = context.get("render_job_plan")
        if not isinstance(render_job_plan, dict):
            return []

        jobs = render_job_plan.get("jobs")
        if not isinstance(jobs, list):
            return []

        extracted: list[AudioRequest] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            audio_request_data = job.get("audio_request")
            if isinstance(audio_request_data, AudioRequest):
                extracted.append(audio_request_data)
                continue
            if isinstance(audio_request_data, dict):
                try:
                    extracted.append(AudioRequest(**audio_request_data))
                except Exception:
                    continue

        return extracted

    def _get_final_output_path(self, context: WorkflowContext) -> str:
        """Return the configured output path for final media generation."""
        for key in ("final_media_output_path", "output_path", "final_output_path"):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""
