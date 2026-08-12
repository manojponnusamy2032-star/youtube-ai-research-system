"""Agent for SEO generation."""

from __future__ import annotations

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.services.content_generation_service import ContentGenerationService


class SeoGeneratorAgent(BaseAgent):
    """Generate SEO package including description, tags, and chapters."""

    def __init__(self, content_generation_service: ContentGenerationService) -> None:
        super().__init__("SeoGeneratorAgent")
        self.content_generation_service = content_generation_service

    def run(self, context: WorkflowContext) -> AgentResult:
        """Generate SEO artifacts for the content package."""
        self.start()
        data = self.content_generation_service.extract_generation_inputs(context.data)
        best_title = context.get("best_title") or self.content_generation_service.select_best_title(
            data["generated_titles"], data["topic"]
        )
        script = context.get("generated_script") or self.content_generation_service.generate_script(
            best_title=best_title,
            hook=context.get("generated_hook"),
            **data,
        )
        seo = self.content_generation_service.generate_seo(best_title=best_title, script=script, **data)
        context.set("generated_seo", seo)
        self.finish()
        return AgentResult.ok(seo=seo)
