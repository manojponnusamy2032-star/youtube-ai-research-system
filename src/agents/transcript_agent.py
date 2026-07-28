"""
Transcript Agent for YouTube AI Research System.

This module implements the Transcript Agent responsible for downloading
and storing transcripts for collected videos using a fallback chain.
"""

import logging
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.models.transcript import TranscriptMethod
from src.services.transcript_service import TranscriptService
from src.database.database_service import DatabaseService

logger = logging.getLogger(__name__)


class TranscriptAgent:
    """
    Agent responsible for downloading video transcripts.
    
    Fetches videos without transcripts from the database, retrieves
    transcripts using the TranscriptService fallback chain, and stores
    results with method tracking.
    
    Attributes:
        transcript_service: TranscriptService instance
        database_service: DatabaseService instance
        console: Rich console for formatted output
    """
    
    def __init__(
        self,
        transcript_service: TranscriptService,
        database_service: DatabaseService
    ) -> None:
        """
        Initialize the Transcript Agent.
        
        Args:
            transcript_service: TranscriptService instance
            database_service: DatabaseService instance
        """
        self.transcript_service = transcript_service
        self.database_service = database_service
        self.console = Console()
        logger.info("Transcript Agent initialized")
    
    def _print_banner(self) -> None:
        """Print the YAIRS Transcript Agent banner."""
        banner = Panel(
            Text("YAIRS Transcript Agent", style="bold cyan"),
            border_style="cyan",
            padding=(1, 2)
        )
        self.console.print(banner)
        self.console.print()
    
    def _print_summary(
        self,
        processed: int,
        youtube_api_count: int,
        ytdlp_count: int,
        whisper_count: int,
        failed_count: int
    ) -> None:
        """
        Print a formatted summary of transcript processing.
        
        Args:
            processed: Total videos processed
            youtube_api_count: Retrieved via youtube-transcript-api
            ytdlp_count: Retrieved via yt-dlp captions
            whisper_count: Retrieved via Whisper
            failed_count: Failed to retrieve
        """
        self.console.print()
        summary_text = (
            f"[bold]Videos processed:[/bold]\n"
            f"{processed}\n\n"
            f"[bold]Retrieved ({TranscriptMethod.YOUTUBE_API.value}):[/bold]\n"
            f"{youtube_api_count}\n\n"
            f"[bold]Retrieved ({TranscriptMethod.YTDLP_CAPTIONS.value}):[/bold]\n"
            f"{ytdlp_count}\n\n"
            f"[bold]Whisper:[/bold]\n"
            f"{whisper_count}\n\n"
            f"[bold]Failed:[/bold]\n"
            f"{failed_count}\n\n"
            f"[bold green]Database updated.[/bold green]"
        )
        
        summary_panel = Panel(
            summary_text,
            border_style="green",
            padding=(1, 2)
        )
        self.console.print(summary_panel)
    
    def run(self, limit: int = 50) -> tuple[int, int, int, int]:
        """
        Execute the transcript collection workflow.
        
        Workflow:
        1. Fetch videos without transcripts from database
        2. Retrieve transcript for each video using fallback chain
        3. Save transcript to database
        4. Print summary
        
        Args:
            limit: Maximum number of videos to process (default: 50)
            
        Returns:
            Tuple of (youtube_api_count, ytdlp_count, whisper_count, failed_count)
        """
        self._print_banner()
        
        # Fetch videos without transcripts
        self.console.print("[cyan]Fetching videos without transcripts...[/cyan]")
        video_ids = self.database_service.get_videos_without_transcripts(limit)
        
        if not video_ids:
            self.console.print("[yellow]No videos without transcripts found.[/yellow]")
            return 0, 0, 0, 0
        
        total = len(video_ids)
        self.console.print(f"[green]Found {total} videos to process[/green]\n")
        
        youtube_api_count = 0
        ytdlp_count = 0
        whisper_count = 0
        failed_count = 0
        
        for idx, video_id in enumerate(video_ids, 1):
            self.console.print(
                f"[cyan][{idx}/{total}][/cyan] Processing: {video_id}"
            )
            
            success, method_or_error = self.transcript_service.process_video(video_id)
            
            if not success:
                failed_count += 1
                self.console.print(f"  [red]Failed[/red]")
            elif method_or_error == TranscriptMethod.YOUTUBE_API.value:
                youtube_api_count += 1
                self.console.print(f"  [green]OK[/green] (youtube-api)")
            elif method_or_error == TranscriptMethod.YTDLP_CAPTIONS.value:
                ytdlp_count += 1
                self.console.print(f"  [green]OK[/green] (yt-dlp captions)")
            elif method_or_error == TranscriptMethod.WHISPER.value:
                whisper_count += 1
                self.console.print(f"  [green]OK[/green] (whisper)")
            elif method_or_error == "already_exists":
                # Count as retrieved via the method it was originally stored with
                youtube_api_count += 1
                self.console.print(f"  [yellow]Already exists[/yellow]")
        
        # Print summary
        self._print_summary(
            processed=total,
            youtube_api_count=youtube_api_count,
            ytdlp_count=ytdlp_count,
            whisper_count=whisper_count,
            failed_count=failed_count
        )
        
        logger.info(
            f"Transcript collection complete: "
            f"{youtube_api_count} youtube-api, "
            f"{ytdlp_count} yt-dlp, "
            f"{whisper_count} whisper, "
            f"{failed_count} failed"
        )
        
        return youtube_api_count, ytdlp_count, whisper_count, failed_count