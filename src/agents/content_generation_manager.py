"""Agent that coordinates the full content generation pipeline."""

from __future__ import annotations

from typing import Any

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.services.content_generation_service import ContentGenerationService


class ContentGenerationManager(BaseAgent):
    """Run hook, thumbnail, script, and SEO agents, then assemble package."""

    def __init__(
        self,
        hook_generator_agent: Any,
        thumbnail_generator_agent: Any,
        script_generator_agent: Any,
        seo_generator_agent: Any,
        content_generation_service: ContentGenerationService,
        render_job_manager: Any | None = None,
        render_pipeline_orchestrator: Any | None = None,
    ) -> None:
        super().__init__("ContentGenerationManager")
        self.hook_generator_agent = hook_generator_agent
        self.thumbnail_generator_agent = thumbnail_generator_agent
        self.script_generator_agent = script_generator_agent
        self.seo_generator_agent = seo_generator_agent
        self.content_generation_service = content_generation_service
        self.render_job_manager = render_job_manager
        self.render_pipeline_orchestrator = render_pipeline_orchestrator

    def run(self, context: WorkflowContext) -> AgentResult:
        """Execute modular generation agents and persist a final package."""
        self.start()
        stage_results = [
            self.hook_generator_agent.run(context),
            self.thumbnail_generator_agent.run(context),
            self.script_generator_agent.run(context),
            self.seo_generator_agent.run(context),
        ]
        for result in stage_results:
            if isinstance(result, AgentResult) and not result.success:
                return result
        package = self.content_generation_service.generate_content_package(
            context.data,
            hook=context.get("generated_hook"),
            thumbnail=context.get("generated_thumbnail"),
            script=context.get("generated_script"),
            seo=context.get("generated_seo"),
        )
        payload = package.to_dict()
        context.set("content_package", payload)
        context.set("content_package_count", 1)
        
        # Run render pipeline if orchestrator is available and enabled
        if self.render_pipeline_orchestrator is not None and context.get("run_render_job_management", False):
            # Extract render_job_plan from the generated package and set it in context
            if payload.get("render_job_plan"):
                context.set("render_job_plan", payload["render_job_plan"])
                context.set("render_jobs", payload["render_job_plan"].get("jobs", []))
            render_result = self.render_pipeline_orchestrator.run(context)
            if isinstance(render_result, AgentResult) and not render_result.success:
                return render_result
        # Fallback to legacy render_job_manager if orchestrator not provided
        elif self.render_job_manager is not None and context.get("run_render_job_management", False):
            if payload.get("render_job_plan"):
                context.set("render_job_plan", payload["render_job_plan"])
                context.set("render_jobs", payload["render_job_plan"].get("jobs", []))
            render_result = self.render_job_manager.run(context)
            if isinstance(render_result, AgentResult) and not render_result.success:
                return render_result
        
        self.finish()
        return AgentResult.ok(content_package=payload, count=1)

