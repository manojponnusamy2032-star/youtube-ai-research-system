"""
Research Pipeline Runner.

Runs the complete research workflow.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.prompt import Prompt

from src.utils.config import config
from src.utils.logger import setup_logger

from src.database.database_service import DatabaseService

from src.services.youtube_service import YouTubeService
from src.services.transcript_service import TranscriptService
from src.services.analysis_service import (
    AnalysisService,
    OllamaProvider,
)
from src.services.pattern_service import PatternService

from src.agents.collector_agent import CollectorAgent
from src.agents.transcript_agent import TranscriptAgent
from src.agents.analysis_agent import AnalysisAgent
from src.agents.pattern_agent import PatternAgent

from src.core.bootstrap import create_manager
from src.core.workflows.research_workflow import ResearchWorkflow

console = Console()


def main():

    console.print("[bold cyan]YAIRS Research Pipeline[/bold cyan]")
    console.print()

    setup_logger(
        name="yairs",
        level=config.LOG_LEVEL,
        log_file=config.LOG_FILE,
        console_output=True,
    )

    database = DatabaseService(config.database_url)
    database.connect()
    database.create_tables()

    try:

        youtube_service = YouTubeService(config.YOUTUBE_API_KEY)

        transcript_service = TranscriptService(database)

        ollama_provider = OllamaProvider()

        analysis_service = AnalysisService(
            ollama_provider,
            database,
        )

        pattern_service = PatternService(database)

        collector = CollectorAgent(
            youtube_service,
            database,
        )

        transcript = TranscriptAgent(
            transcript_service,
            database,
        )

        analysis = AnalysisAgent(
            analysis_service,
            database,
        )

        pattern = PatternAgent(
            pattern_service,
            database,
        )

        manager = create_manager(
            collector,
            transcript,
            analysis,
            pattern,
        )

        workflow = ResearchWorkflow(manager)

        keyword = Prompt.ask(
            "[cyan]Keyword[/cyan]",
            default="stickman animation",
        )

        max_results = int(
            Prompt.ask(
                "[cyan]Max Results[/cyan]",
                default="50",
            )
        )

        workflow.build(
            collector,
            transcript,
            analysis,
            pattern,
            keyword,
            max_results,
        )

        console.print()
        console.print("[green]Starting research workflow...[/green]")
        console.print()

        manager.run()

        console.print()
        console.print("[bold green]Research pipeline completed.[/bold green]")

    finally:

        database.disconnect()

        try:
            youtube_service.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()