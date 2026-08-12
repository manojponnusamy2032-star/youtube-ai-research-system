"""
Idea Generator Agent.

Generates and stores YouTube video ideas from extracted patterns.
"""

import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.database.database_service import DatabaseService
from src.services.idea_service import IdeaService
from src.services.pattern_service import PatternService

logger = logging.getLogger(__name__)


class IdeaGeneratorAgent:
    """Generates and stores new YouTube ideas."""

    def __init__(
        self,
        idea_service: IdeaService,
        pattern_service: PatternService,
        database_service: DatabaseService,
    ) -> None:

        self.idea_service = idea_service
        self.pattern_service = pattern_service
        self.database_service = database_service
        self.console = Console()

    def run(self) -> int:
        """
        Generate ideas from the latest pattern summary.

        Returns
        -------
        Number of ideas saved.
        """

        self.console.print(
            Panel(
                "[bold cyan]YAIRS Idea Generator[/bold cyan]",
                border_style="cyan",
            )
        )

        logger.info("Loading latest pattern summary...")

        pattern_summary = self.pattern_service.get_latest_summary()

        if not pattern_summary:
            self.console.print(
                "[yellow]No pattern summary found. Nothing to generate.[/yellow]"
            )
            return 0

        logger.info("Generating ideas...")

        ideas = self.idea_service.generate(pattern_summary)

        table = Table(title="Generated Ideas")

        table.add_column("#")
        table.add_column("Title")
        table.add_column("Virality")
        table.add_column("Confidence")

        saved = 0

        for index, idea in enumerate(ideas, start=1):

            self.database_service.insert_idea(idea)

            table.add_row(
                str(index),
                idea.title,
                f"{idea.virality_score:.1f}",
                f"{idea.confidence_score:.1f}",
            )

            saved += 1

        self.console.print(table)

        logger.info("%s ideas saved.", saved)

        return saved