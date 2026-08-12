"""Agent for thumbnail generation."""

from __future__ import annotations

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.services.content_generation_service import ContentGenerationService


class ThumbnailGeneratorAgent(BaseAgent):
    """Generate thumbnail plan using best available title candidate."""

    def __init__(self, content_generation_service: ContentGenerationService) -> None:
        super().__init__("ThumbnailGeneratorAgent")
        self.content_generation_service = content_generation_service

    def run(self, context: WorkflowContext) -> AgentResult:
        """Generate thumbnail concept and image prompt."""
        self.start()
        data = self.content_generation_service.extract_generation_inputs(context.data)
        best_title = self.content_generation_service.select_best_title(data["generated_titles"], data["topic"])
        context.set("best_title", best_title)
        thumbnail = self.content_generation_service.generate_thumbnail(best_title=best_title, **data)
        context.set("generated_thumbnail", thumbnail)
        self.finish()
        return AgentResult.ok(thumbnail=thumbnail)
