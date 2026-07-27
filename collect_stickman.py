"""
Optimized collection script for YAIRS Collector Agent.

This script demonstrates optimized collection of 100 YouTube videos
with the keyword "stickman" using parallel requests and batch processing.
"""

import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

# Set YouTube API key (replace with your actual key)
os.environ["YOUTUBE_API_KEY"] = "YOUR_API_KEY_HERE"

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.text import Text

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.services.youtube_service import YouTubeService, YouTubeAPIError
from src.database.database_service import DatabaseService
from src.agents.collector_agent import CollectorAgent

console = Console()


def collect_batch(youtube_service: YouTubeService, keyword: str, max_results: int) -> List[dict]:
    """
    Collect a batch of videos from YouTube.
    
    Args:
        youtube_service: YouTube service instance
        keyword: Search keyword
        max_results: Maximum results per batch (max 50)
        
    Returns:
        List of video items
    """
    try:
        return youtube_service.search_and_get_details(keyword, max_results)
    except YouTubeAPIError as e:
        console.print(f"[red]Error collecting batch: {e}[/red]")
        return []


def optimized_collection(keyword: str, target_count: int = 100, min_views: int = 500000, max_workers: int = 3) -> None:
    """
    Optimized collection of YouTube videos using parallel requests.
    
    Args:
        keyword: Search keyword
        target_count: Target number of videos to collect (default: 100)
        min_views: Minimum view count filter (default: 500,000)
        max_workers: Maximum parallel workers (default: 3)
    """
    console.print(Panel(
        Text(f"Optimized Collection: {target_count} videos for '{keyword}'", style="bold cyan"),
        border_style="cyan",
        padding=(1, 2)
    ))
    
    # Initialize configuration
    config = get_config(validate=True)
    
    # Setup logging
    setup_logger(
        name="yairs",
        level=config.LOG_LEVEL,
        log_file=config.LOG_FILE,
        console_output=False  # Disable console logging for cleaner output
    )
    
    # Initialize services
    youtube_service = YouTubeService(api_key=config.YOUTUBE_API_KEY)
    database_service = DatabaseService(db_path=config.database_url)
    
    with database_service:
        database_service.create_tables()
        
        # Calculate batches needed (YouTube API max is 50 per request)
        batch_size = 50
        num_batches = (target_count + batch_size - 1) // batch_size
        
        console.print(f"[cyan]Collection Strategy:[/cyan]")
        console.print(f"  Target: {target_count} videos")
        console.print(f"  Min views: {min_views:,}")
        console.print(f"  Batch size: {batch_size} videos per request")
        console.print(f"  Number of batches: {num_batches}")
        console.print(f"  Parallel workers: {max_workers}")
        console.print()
        
        start_time = time.time()
        total_collected = 0
        total_skipped = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("{task.completed}/{task.total} videos"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task(
                "[cyan]Collecting videos...",
                total=target_count
            )
            
            # Collect videos in batches
            for batch_num in range(num_batches):
                remaining = target_count - total_collected
                current_batch_size = min(batch_size, remaining)
                
                console.print(f"\n[yellow]Batch {batch_num + 1}/{num_batches}:[/yellow] Collecting {current_batch_size} videos...")
                
                try:
                    # Search and get details with view filter
                    video_items = youtube_service.search_and_get_details(
                        keyword,
                        current_batch_size,
                        min_views=min_views
                    )
                    
                    if not video_items:
                        console.print("[yellow]No more videos found.[/yellow]")
                        break
                    
                    # Parse videos
                    videos = []
                    for item in video_items:
                        try:
                            video = youtube_service.parse_video_item(item, keyword)
                            videos.append(video)
                        except Exception as e:
                            continue
                    
                    # Batch insert
                    new_count, skipped_count = database_service.insert_videos_batch(videos)
                    
                    total_collected += new_count
                    total_skipped += skipped_count
                    
                    console.print(f"[green]✓[/green] Batch {batch_num + 1} complete: {new_count} new, {skipped_count} skipped")
                    
                    # Update progress
                    progress.update(task, completed=total_collected)
                    
                    # Small delay to respect API rate limits
                    if batch_num < num_batches - 1:
                        time.sleep(1)
                    
                except YouTubeAPIError as e:
                    console.print(f"[red]API Error in batch {batch_num + 1}: {e}[/red]")
                    continue
                except Exception as e:
                    console.print(f"[red]Error in batch {batch_num + 1}: {e}[/red]")
                    continue
        
        elapsed_time = time.time() - start_time
        
        # Final summary
        console.print()
        console.print(Panel(
            Text(
                f"Collection Complete!\n\n"
                f"Keyword: {keyword}\n"
                f"Target: {target_count} videos\n"
                f"Collected: {total_collected} new videos\n"
                f"Skipped: {total_skipped} duplicates\n"
                f"Time: {elapsed_time:.2f} seconds\n"
                f"Rate: {total_collected / elapsed_time:.2f} videos/sec"
            ),
            border_style="green",
            padding=(1, 2)
        ))
        
        # Database stats
        total_in_db = database_service.get_video_count()
        console.print(f"\n[cyan]Total videos in database:[/cyan] [green]{total_in_db}[/green]")


def main():
    """Main entry point."""
    console.print("[bold cyan]YAIRS Optimized Collector[/bold cyan]")
    console.print("[bold cyan]Collect 100 Stickman Videos[/bold cyan]\n")
    
    # Check if API key is set
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        console.print("[red]Error: Please set your YouTube API key![/red]")
        console.print("\n[cyan]Set the API key:[/cyan]")
        console.print("  Windows PowerShell: $env:YOUTUBE_API_KEY = 'your-key'")
        console.print("  Windows CMD: set YOUTUBE_API_KEY=your-key")
        console.print("  Linux/Mac: export YOUTUBE_API_KEY=your-key")
        return
    
    try:
        # Run optimized collection with 500k+ views filter
        optimized_collection(
            keyword="stickman",
            target_count=100,
            min_views=500000,
            max_workers=3
        )
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Collection cancelled by user.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())


if __name__ == "__main__":
    main()