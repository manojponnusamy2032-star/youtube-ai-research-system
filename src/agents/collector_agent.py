"""
Collector Agent for YouTube AI Research System.

This module implements the Collector Agent responsible for searching YouTube
and saving video metadata to the database.
"""

import logging
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.models.video import Video
from src.services.youtube_service import YouTubeService
from src.database.database_service import DatabaseService

logger = logging.getLogger(__name__)


class CollectorAgent:
    """
    Agent responsible for collecting YouTube video metadata.
    
    Searches YouTube using keywords, retrieves video metadata,
    validates with Pydantic models, and saves to SQLite database.
    
    Attributes:
        youtube_service: YouTube API service instance
        database_service: Database service instance
        console: Rich console for formatted output
    """
    
    def __init__(
        self,
        youtube_service: YouTubeService,
        database_service: DatabaseService
    ) -> None:
        """
        Initialize the Collector Agent.
        
        Args:
            youtube_service: YouTube API service instance
            database_service: Database service instance
        """
        self.youtube_service = youtube_service
        self.database_service = database_service
        self.console = Console()
        logger.info("Collector Agent initialized")
    
    def _print_banner(self) -> None:
        """Print the YAIRS Collector Agent banner."""
        banner = Panel(
            Text("YAIRS Collector Agent", style="bold cyan"),
            border_style="cyan",
            padding=(1, 2)
        )
        self.console.print(banner)
        self.console.print()
    
    def _print_summary(
        self,
        keyword: str,
        found: int,
        new: int,
        skipped: int
    ) -> None:
        """
        Print collection summary in a formatted way.
        
        Args:
            keyword: Search keyword used
            found: Number of videos found
            new: Number of new videos inserted
            skipped: Number of duplicate videos skipped
        """
        self.console.print()
        summary_text = (
            f"[bold]Searching keyword:[/bold]\n"
            f"{keyword}\n\n"
            f"[bold]Found:[/bold]\n"
            f"{found} videos\n\n"
            f"[bold]New:[/bold]\n"
            f"{new}\n\n"
            f"[bold]Skipped:[/bold]\n"
            f"{skipped} duplicates\n\n"
            f"[bold green]Database updated successfully.[/bold green]"
        )
        
        summary_panel = Panel(
            summary_text,
            border_style="green",
            padding=(1, 2)
        )
        self.console.print(summary_panel)
    
    def run(self, keyword: str, max_results: int = 50) -> tuple[int, int]:
        """
        Execute the collection workflow.
        
        Workflow:
        1. Search YouTube for videos
        2. Retrieve detailed metadata
        3. Validate with Pydantic models
        4. Save to SQLite database
        5. Print collection summary
        
        Args:
            keyword: Search keyword
            max_results: Maximum number of results to collect (default: 50)
            
        Returns:
            Tuple of (new_count, skipped_count)
            
        Raises:
            ValueError: If keyword is empty or invalid
            RuntimeError: If collection fails
        """
        if not keyword or not keyword.strip():
            raise ValueError("Search keyword cannot be empty")
        
        if max_results < 1 or max_results > 50:
            raise ValueError("max_results must be between 1 and 50")
        
        self._print_banner()
        
        try:
            # Step 1: Search YouTube and get details
            self.console.print(f"[cyan]Searching YouTube for:[/cyan] {keyword}")
            video_items = self.youtube_service.search_and_get_details(
                keyword, max_results, min_views=500_000
            )
            found_count = len(video_items)
            
            if found_count == 0:
                self.console.print("[yellow]No videos found.[/yellow]")
                return 0, 0
            
            self.console.print(f"[green]Found {found_count} videos[/green]")
            
            # Step 2: Parse and validate videos
            self.console.print("[cyan]Validating video metadata...[/cyan]")
            videos: list[Video] = []
            
            for item in video_items:
                try:
                    video = self.youtube_service.parse_video_item(item, keyword)
                    videos.append(video)
                except Exception as e:
                    logger.warning(f"Failed to parse video: {e}")
                    continue
            
            # Step 3: Save to database
            self.console.print("[cyan]Saving to database...[/cyan]")
            new_count, skipped_count = self.database_service.insert_videos_batch(videos)
            
            # Step 4: Print summary
            self._print_summary(keyword, found_count, new_count, skipped_count)
            
            logger.info(
                f"Collection complete: {new_count} new, {skipped_count} skipped"
            )
            
            return new_count, skipped_count
            
        except Exception as e:
            logger.error(f"Collection failed: {e}", exc_info=True)
            self.console.print(f"[red]Error: {e}[/red]")
            raise RuntimeError(f"Collection failed: {e}") from e
    
    def run_batch(self, keywords: list[str], max_results_per_keyword: int = 50) -> tuple[int, int]:
        """
        Run collection for multiple keywords.
        
        Args:
            keywords: List of search keywords
            max_results_per_keyword: Maximum results per keyword
            
        Returns:
            Tuple of (total_new_count, total_skipped_count)
        """
        total_new = 0
        total_skipped = 0
        total_found = 0
        total_keywords = len(keywords)
        expected_max = total_keywords * max_results_per_keyword
        
        self._print_banner()
        
        for keyword in keywords:
            try:
                new, skipped = self.run(keyword, max_results_per_keyword)
                total_new += new
                total_skipped += skipped
                total_found += new + skipped
            except Exception as e:
                logger.error(f"Failed to collect for keyword '{keyword}': {e}")
                self.console.print(
                    f"[red]Failed to collect for '{keyword}': {e}[/red]"
                )
                continue
        
        # Print final summary
        self.console.print()
        final_text = (
            f"[bold]Batch Collection Complete[/bold]\n\n"
            f"Keywords processed: {total_keywords}\n"
            f"Max results per keyword: {max_results_per_keyword}\n"
            f"Expected max results: {expected_max}\n"
            f"Total found (new + skipped): {total_found}\n"
            f"Total new videos: {total_new}\n"
            f"Total skipped: {total_skipped}"
        )
        final_panel = Panel(
            final_text,
            border_style="blue",
            padding=(1, 2)
        )
        self.console.print(final_panel)
        
        return total_new, total_skipped