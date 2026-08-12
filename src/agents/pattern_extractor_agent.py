"""Agent that extracts repeated viral patterns from the full analysis dataset."""

from __future__ import annotations

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.database.database_service import DatabaseService
from src.services.pattern_service import PatternService


class PatternExtractorAgent(BaseAgent):
    """Run full-database pattern extraction and publish a JSON report."""

    def __init__(
        self,
        pattern_service: PatternService,
        database_service: DatabaseService,
    ) -> None:
        super().__init__("PatternExtractorAgent")
        self.pattern_service = pattern_service
        self.database_service = database_service

    def run(self, context: WorkflowContext) -> AgentResult:
        """Generate pattern report and place it in workflow context."""
        self.start()
        report = self.pattern_service.generate_report()
        context.set("pattern_report", report)
        self.finish()
        return AgentResult.ok(report=report)
