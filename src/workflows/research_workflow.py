"""
Research Workflow.

Registers the complete research workflow with the Manager.
"""

from src.core.manager_agent import ManagerAgent


class ResearchWorkflow:
    """Collector → Transcript → Analysis → Pattern"""

    def __init__(self, manager: ManagerAgent):
        self.manager = manager

    def register(
        self,
        collector_agent,
        transcript_agent,
        analysis_agent,
        pattern_agent,
        keyword: str,
        max_results: int = 50,
    ) -> None:
        """
        Register every task in execution order.
        """

        self.manager.add_task(
            collector_agent,
            keyword,
            max_results,
        )

        self.manager.add_task(
            transcript_agent,
        )

        self.manager.add_task(
            analysis_agent,
        )

        self.manager.add_task(
            pattern_agent,
        )