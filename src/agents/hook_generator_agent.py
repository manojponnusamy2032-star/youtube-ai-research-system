"""Agent for hook generation."""

from __future__ import annotations

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.services.content_generation_service import ContentGenerationService


class HookGeneratorAgent(BaseAgent):
    """Generate and publish best hook candidate to workflow context."""

    def __init__(self, content_generation_service: ContentGenerationService) -> None:
        super().__init__("HookGeneratorAgent")
        self.content_generation_service = content_generation_service

    def run(self, context: WorkflowContext) -> AgentResult:
        """Generate best hook from current workflow inputs."""
        self.start()
        data = self.content_generation_service.extract_generation_inputs(context.data)
        hook = self.content_generation_service.generate_hook(**data)
        context.set("generated_hook", hook)
        self.finish()
        return AgentResult.ok(hook=hook)
