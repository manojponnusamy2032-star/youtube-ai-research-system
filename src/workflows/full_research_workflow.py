"""
Full YouTube Research Workflow.
"""

from src.core.manager_agent import ManagerAgent


class FullResearchWorkflow:
    """Research workflow."""

    def __init__(self, manager: ManagerAgent):
        self.manager = manager

    def build(
        self,
        collector,
        transcript,
        analysis,
        pattern,
        keyword: str,
        max_results: int,
    ) -> None:
        """
        Build the research pipeline.
        """

        self.manager.add_task(
            collector,
            keyword,
            max_results,
        )

        self.manager.add_task(
            transcript,
        )

        self.manager.add_task(
            analysis,
        )

        self.manager.add_task(
            pattern,
        )