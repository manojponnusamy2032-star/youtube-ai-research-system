"""
Research Pipeline.

Executes the complete research workflow.
"""

from src.core.manager_agent import ManagerAgent


class ResearchPipeline:
    """Complete research pipeline."""

    def __init__(self, manager: ManagerAgent):
        self.manager = manager

    def execute(
        self,
        collector,
        transcript,
        analysis,
        pattern,
        keyword: str,
        max_results: int,
    ):
        """
        Execute the complete research workflow.
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

        return self.manager.run()