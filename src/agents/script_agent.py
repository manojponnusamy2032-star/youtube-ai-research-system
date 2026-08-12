"""
Script Agent.

Generates YouTube scripts from Ideas.
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.panel import Panel

from src.services.script_service import ScriptService
from src.database.database_service import DatabaseService

logger = logging.getLogger(__name__)


class ScriptAgent:
    """
    Generates scripts for ideas that do not yet have scripts.
    """

    def __init__(
        self,
        script_service: ScriptService,
        database_service: DatabaseService,
    ) -> None:

        self.script_service = script_service
        self.database_service = database_service
        self.console = Console()

    def run(
        self,
        limit: int = 10,
    ) -> tuple[int, int]:
        """
        Generate scripts.

        Returns:
            (generated, skipped)
        """

        generated = 0
        skipped = 0

        ideas = self.database_service.get_pending_ideas(limit)

        if not ideas:
            self.console.print(
                "[yellow]No ideas available for script generation.[/yellow]"
            )
            return 0, 0

        self.console.print(
            Panel.fit(
                f"Generating scripts for {len(ideas)} ideas...",
                title="Script Agent",
            )
        )

        for idea in ideas:

            if self.database_service.script_exists(idea.id):
                skipped += 1
                continue

            try:

                script = self.script_service.generate(idea)

                self.database_service.insert_script(script)

                generated += 1

                logger.info(
                    "Generated script: %s",
                    script.title,
                )

            except Exception as e:

                logger.exception(e)

        self.console.print()

        self.console.print(
            f"[green]Generated:[/green] {generated}"
        )

        self.console.print(
            f"[yellow]Skipped:[/yellow] {skipped}"
        )

        return generated, skipped