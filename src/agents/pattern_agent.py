"""
Pattern Agent for YouTube AI Research System.

This module implements the Pattern Intelligence Agent responsible for
analyzing all stored analysis results and discovering patterns across
the entire dataset.
"""

import logging
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from src.services.pattern_service import PatternService
from src.database.database_service import DatabaseService
from src.models.pattern import PatternSummary

logger = logging.getLogger(__name__)


class PatternAgent:
    """
    Agent responsible for pattern intelligence analysis.

    Analyzes all stored analysis results and discovers patterns across
    the entire dataset, generating aggregate insights and reports.

    Attributes:
        pattern_service: PatternService instance
        database_service: DatabaseService instance
        console: Rich console for formatted output
    """

    def __init__(
        self,
        pattern_service: PatternService,
        database_service: DatabaseService
    ) -> None:
        """
        Initialize the Pattern Agent.

        Args:
            pattern_service: PatternService instance
            database_service: DatabaseService instance
        """
        self.pattern_service = pattern_service
        self.database_service = database_service
        self.console = Console()
        logger.info("Pattern Agent initialized")

    def _print_banner(self) -> None:
        """Print the YAIRS Pattern Intelligence Agent banner."""
        banner = Panel(
            Text("YAIRS Pattern Intelligence Agent", style="bold magenta"),
            border_style="magenta",
            padding=(1, 2)
        )
        self.console.print(banner)
        self.console.print()

    def _print_dashboard(self, summary: PatternSummary) -> None:
        """
        Print a Rich dashboard with pattern analysis results.

        Args:
            summary: Pattern analysis summary
        """
        self.console.print()

        # Main stats table
        table = Table(show_header=False, border_style="green", show_lines=True)
        table.add_column("Metric", style="bold cyan", no_wrap=True)
        table.add_column("Value", justify="right")

        table.add_row("Videos analyzed", str(summary.videos_analyzed))
        table.add_row("Patterns found", f"[yellow]{summary.patterns_found}[/yellow]")
        table.add_row("Reports saved", f"[green]{summary.reports_saved}[/green]")

        self.console.print(table)
        self.console.print()

        # Top patterns display
        top_patterns_table = Table(
            title="Top Patterns",
            show_header=True,
            border_style="cyan",
            header_style="bold cyan"
        )
        top_patterns_table.add_column("Category", style="cyan")
        top_patterns_table.add_column("Top Pattern", style="yellow")

        top_patterns = [
            ("Top Hook", summary.top_hook),
            ("Top Emotion", summary.top_emotion),
            ("Top Story Structure", summary.top_story_structure),
            ("Top Thumbnail Pattern", summary.top_thumbnail_pattern),
            ("Top Title Formula", summary.top_title_formula),
        ]

        for category, pattern in top_patterns:
            pattern_display = pattern if pattern else "[dim]N/A[/dim]"
            top_patterns_table.add_row(category, pattern_display)

        self.console.print(top_patterns_table)
        self.console.print()

        # Footer
        self.console.print(
            Panel(
                Text("Pattern analysis complete! Reports exported to data/output/reports/",
                     style="green"),
                border_style="green",
                padding=(1, 2)
            )
        )
        self.console.print()

    def run(self, report_name: Optional[str] = None) -> PatternSummary:
        """
        Execute the pattern analysis workflow.

        Workflow:
        1. Run PatternService to analyze all analysis records
        2. Generate statistics and rankings
        3. Save reports to database
        4. Export JSON report to data/output/reports/
        5. Display Rich dashboard

        Args:
            report_name: Optional custom report name

        Returns:
            PatternSummary with results
        """
        self._print_banner()

        # Check if there are any analysis records
        analysis_count = self.database_service.get_analysis_count()
        video_count = self.database_service.get_video_count()

        self.console.print(
            f"[cyan]Videos in database: {video_count}[/cyan]"
        )
        self.console.print(
            f"[cyan]Analyses in database: {analysis_count}[/cyan]"
        )
        self.console.print()

        if analysis_count == 0:
            self.console.print(
                Panel(
                    Text("No analysis records found. Run the Analysis Agent first.",
                         style="yellow"),
                    border_style="yellow",
                    padding=(1, 2)
                )
            )
            return PatternSummary(
                videos_analyzed=0,
                patterns_found=0,
                reports_saved=0
            )

        # Run pattern analysis
        self.console.print("[cyan]Analyzing patterns across dataset...[/cyan]")

        summary = self.pattern_service.run(report_name)

        # Display dashboard
        self._print_dashboard(summary)

        logger.info(
            f"Pattern Agent complete: "
            f"{summary.videos_analyzed} videos, "
            f"{summary.patterns_found} patterns found"
        )

        return summary