"""Agent responsible for generating ranked YouTube title candidates."""

from __future__ import annotations

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.database.database_service import DatabaseService
from src.services.title_generation_service import TitleGenerationService


class TitleGeneratorAgent(BaseAgent):
    """Generate explainable titles from topic, knowledge, patterns, and trends."""

    def __init__(
        self,
        title_generation_service: TitleGenerationService,
        database_service: DatabaseService,
    ) -> None:
        super().__init__("TitleGeneratorAgent")
        self.title_generation_service = title_generation_service
        self.database_service = database_service

    def run(self, context: WorkflowContext) -> AgentResult:
        """Generate and return 20 ranked title candidates from workflow context."""
        self.start()
        topic = str(context.get("title_topic") or context.get("topic") or context.get("keyword", "")).strip()
        if not topic:
            return AgentResult.fail("title topic is required in workflow context")
        titles = self.title_generation_service.generate_titles(
            topic=topic,
            niche=context.get("niche"),
            audience=context.get("audience"),
            trend_data=context.get("trend_data"),
            count=int(context.get("title_count", 20)),
        )
        payload = [item.to_dict() for item in titles]
        context.set("generated_titles", payload)
        context.set("generated_titles_count", len(payload))
        self.finish()
        return AgentResult.ok(titles=payload, count=len(payload))
