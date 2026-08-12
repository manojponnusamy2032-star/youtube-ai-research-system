"""Agent for script generation."""

from __future__ import annotations

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.services.content_generation_service import ContentGenerationService


class ScriptGeneratorAgent(BaseAgent):
    """Generate full script plan with sections and retention checkpoints."""

    def __init__(self, content_generation_service: ContentGenerationService) -> None:
        super().__init__("ScriptGeneratorAgent")
        self.content_generation_service = content_generation_service

    def run(self, context: WorkflowContext) -> AgentResult:
        """Generate script from topic, hook, title, and knowledge signals."""
        self.start()
        data = self.content_generation_service.extract_generation_inputs(context.data)
        best_title = context.get("best_title") or self.content_generation_service.select_best_title(
            data["generated_titles"], data["topic"]
        )
        hook = context.get("generated_hook") or self.content_generation_service.generate_hook(**data)
        script = self.content_generation_service.generate_script(best_title=best_title, hook=hook, **data)
        context.set("generated_script", script)
        self.finish()
        return AgentResult.ok(script=script)
