"""
Analysis Agent for YouTube AI Research System.

This module implements the Analysis Agent responsible for analyzing
video transcripts and storing structured insights using LLM.
"""

import logging
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from src.models.transcript import Transcript
from src.services.analysis_service import AnalysisService, LLMProvider
from src.database.database_service import DatabaseService

logger = logging.getLogger(__name__)


class AnalysisAgent:
    """
    Agent responsible for analyzing video transcripts.
    
    Fetches transcripts without analysis from the database, analyzes them
    using the AnalysisService and LLM, and stores results with model tracking.
    
    Attributes:
        analysis_service: AnalysisService instance
        database_service: DatabaseService instance
        console: Rich console for formatted output
    """
    
    def __init__(
        self,
        analysis_service: AnalysisService,
        database_service: DatabaseService
    ) -> None:
        """
        Initialize the Analysis Agent.
        
        Args:
            analysis_service: AnalysisService instance
            database_service: DatabaseService instance
        """
        self.analysis_service = analysis_service
        self.database_service = database_service
        self.console = Console()
        logger.info("Analysis Agent initialized")
    
    def _print_banner(self) -> None:
        """Print the YAIRS Analysis Agent banner."""
        banner = Panel(
            Text("YAIRS Analysis Agent", style="bold cyan"),
            border_style="cyan",
            padding=(1, 2)
        )
        self.console.print(banner)
        self.console.print()
    
    def _print_summary(
        self,
        processed: int,
        analyzed_count: int,
        failed_count: int,
        skipped_count: int,
        model_name: str
    ) -> None:
        """
        Print a formatted summary of analysis processing.
        
        Args:
            processed: Total transcripts processed
            analyzed_count: Successfully analyzed
            failed_count: Failed to analyze
            skipped_count: Skipped (already exists)
            model_name: LLM model used
        """
        self.console.print()
        
        # Create summary table
        table = Table(show_header=False, border_style="green")
        table.add_column("Metric", style="bold")
        table.add_column("Count", justify="right")
        
        table.add_row("Transcripts processed", str(processed))
        table.add_row("Newly analyzed", f"[green]{analyzed_count}[/green]")
        table.add_row("Skipped (already exists)", f"[yellow]{skipped_count}[/yellow]")
        table.add_row("Failed", f"[red]{failed_count}[/red]")
        table.add_row("LLM Model", model_name)
        
        self.console.print(table)
        self.console.print()
        
        success_rate = (analyzed_count / processed * 100) if processed > 0 else 0
        self.console.print(
            f"[bold green]Analysis complete![/bold green] "
            f"Success rate: {success_rate:.1f}%"
        )
        self.console.print()
    
    def run(self, limit: int = 50, force_reanalyze: bool = False) -> tuple[int, int, int]:
        """
        Execute the analysis workflow.
        
        Workflow:
        1. Fetch transcripts without analysis from database
        2. Analyze each transcript using LLM
        3. Save analysis results to database
        4. Print summary
        
        Args:
            limit: Maximum number of transcripts to process (default: 50)
            force_reanalyze: If True, re-analyze even if analysis exists (default: False)
            
        Returns:
            Tuple of (analyzed_count, failed_count, skipped_count)
        """
        self._print_banner()
        
        # Fetch transcripts without analysis
        self.console.print("[cyan]Fetching transcripts without analysis...[/cyan]")
        
        if force_reanalyze:
            # Get all completed transcripts
            video_ids = self._get_all_completed_transcripts(limit)
            self.console.print(f"[yellow]Force re-analyze mode: processing {len(video_ids)} transcripts[/yellow]")
        else:
            video_ids = self.database_service.get_videos_without_analysis(limit)
        
        if not video_ids:
            self.console.print("[yellow]No transcripts without analysis found.[/yellow]")
            return 0, 0, 0
        
        total = len(video_ids)
        self.console.print(f"[green]Found {total} transcripts to analyze[/green]\n")
        
        analyzed_count = 0
        failed_count = 0
        skipped_count = 0
        
        for idx, video_id in enumerate(video_ids, 1):
            self.console.print(
                f"[cyan][{idx}/{total}][/cyan] Analyzing: {video_id}"
            )
            
            # Get transcript from database
            transcript = self._get_transcript(video_id)
            if not transcript:
                failed_count += 1
                self.console.print(f"  [red]Failed[/red] (no transcript found)")
                continue
            
            # Process transcript
            success, error = self.analysis_service.process_transcript(transcript)
            
            if not success:
                failed_count += 1
                self.console.print(f"  [red]Failed[/red] ({error})")
            elif error == "already_exists":
                skipped_count += 1
                self.console.print(f"  [yellow]Skipped[/yellow] (already exists)")
            else:
                analyzed_count += 1
                self.console.print(f"  [green]Analyzed[/green]")
        
        # Print summary
        model_name = self.analysis_service.llm_provider.get_model_name()
        self._print_summary(
            processed=total,
            analyzed_count=analyzed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            model_name=model_name
        )
        
        logger.info(
            f"Analysis complete: "
            f"{analyzed_count} analyzed, "
            f"{failed_count} failed, "
            f"{skipped_count} skipped"
        )
        
        return analyzed_count, failed_count, skipped_count
    
    def _get_transcript(self, video_id: str) -> Optional[Transcript]:
        """
        Get transcript from database.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            Transcript model instance or None
        """
        return self.database_service.get_transcript_by_video_id(video_id)
    
    def _get_all_completed_transcripts(self, limit: int) -> list[str]:
        """
        Get all completed transcript video IDs.
        
        Args:
            limit: Maximum number to return
            
        Returns:
            List of video IDs
        """
        # This would query the database for all transcripts with status='completed'
        # For now, using the existing method
        return self.database_service.get_videos_without_analysis(limit)