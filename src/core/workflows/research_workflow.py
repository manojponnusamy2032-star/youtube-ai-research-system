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
        transcript,
        analysis,
        pattern,
        keyword: str,
        max_results: int,
    ) -> None:
        """
        Register the complete workflow.
        """

        # 1. Collect videos
        self.manager.add_task(
            collector,
            keyword,
            max_results,
        )

        # 2. Download transcripts
        self.manager.add_task(
            transcript,
        )

        # 3. Analyze transcripts
        self.manager.add_task(
            analysis,
        )

        # 4. Generate pattern report
        self.manager.add_task(
            pattern,
        )