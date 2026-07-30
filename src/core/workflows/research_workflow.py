"""
Research Workflow.

Defines the complete research pipeline.
"""

from src.core.manager_agent import ManagerAgent


class ResearchWorkflow:
    """Builds the research workflow."""

    def __init__(self, manager: ManagerAgent):
        self.manager = manager

    def build(
        self,
        collector,
        keyword: str,
        max_results: int,
    ) -> None:
        """
        Register the workflow.
        """

        self.manager.add_task(
            collector,
            keyword,
            max_results,
        )