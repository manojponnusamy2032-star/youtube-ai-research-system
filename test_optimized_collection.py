"""
Test optimized collection with simulated data.

This script demonstrates the optimized collection workflow
without requiring a real YouTube API key.
"""

import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
from unittest.mock import Mock, patch

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
from src.models.video import Video
from datetime import datetime, timezone

console = Console()


def create_mock_video(video_id: int, keyword: str) -> dict:
    """Create a mock YouTube API response."""
    return {
        "id": f"video_{video_id:03d}",
        "snippet": {
            "title": f"Stickman Animation {video_id} - {keyword.title()} Video",
            "description": f"This is a stickman animation video number {video_id}",
            "channelTitle": f"Stickman Channel {video_id % 5 + 1}",
            "channelId": f"UC{video_id:010d}",
            "publishedAt": "2024-01-15T10:30:00Z",
            "thumbnails": {
                "medium": {"url": f"https://example.com/thumb_{video_id}.jpg"}
            }
        },
        "statistics": {
            "viewCount": str(10000 + video_id * 1000),
            "likeCount": str(500 + video_id * 50),
            "commentCount": str(50 + video_id * 5)
        },
        "contentDetails": {
            "duration": f"PT{2 + video_id % 10}M{30 + video_id % 30}S"
        }
    }


def mock_search_and_get_details(self, keyword: str, max_results: int) -> List[dict]:
    """Mock implementation of search_and_get_details."""
    # Simulate API delay
    time.sleep(0.5)
    
    # Generate mock videos
    return [create_mock_video(i, keyword) for i in range(1, max_results + 1)]


def optimized_collection_test(keyword: str, target_count: int = 100) -> None:
    """
    Test optimized collection with simulated data.
    
    Args:
        keyword: Search keyword
        target_count: Target number of videos to collect (default: 100)
    """
    console.print(Panel(
        Text(f"Optimized Collection Test: {target_count} videos for '{keyword}'", style="bold cyan"),
        border_style="cyan",
        padding=(1, 2)
    ))
    
    # Initialize configuration
    config = get_config(validate=False)
    config.YOUTUBE_API_KEY = "test-key"
    
    # Setup logging
    setup_logger(
        name="yairs",
        level=config.LOG_LEVEL,
        log_file=config.LOG_FILE,
        console_output=False
    )
    
    # Initialize services
    youtube_service = YouTubeService(api_key="test-key")
    database_service = DatabaseService(db_path=":memory:")  # In-memory database for testing
    
    with database_service:
        database_service.create_tables()
        
        # Calculate batches needed (YouTube API max is 50 per request)
        batch_size = 50
        num_batches = (target_count + batch_size - 1) // batch_size
        
        console.print(f"[cyan]Collection Strategy:[/cyan]")
        console.print(f"  Target: {target_count} videos")
        console.print(f"  Batch size: {batch_size} videos per request")
        console.print(f"  Number of batches: {num_batches}")
        console.print()
        
        # Mock the search_and_get_details method
        with patch.object(YouTubeService, 'search_and_get_details', mock_search_and_get_details):
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
                        # Search and get details (mocked)
                        video_items = youtube_service.search_and_get_details(
                            keyword,
                            current_batch_size
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
                        
                        # Small delay to simulate rate limiting
                        if batch_num < num_batches - 1:
                            time.sleep(0.5)
                        
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
            
            # Show sample videos
            console.print("\n[cyan]Sample videos collected:[/cyan]")
            for i in range(1, 4):
                video = database_service.video_exists(f"video_{i:03d}")
                console.print(f"  {i}. video_{i:03d} exists: {video}")


def main():
    """Main entry point."""
    console.print("[bold cyan]YAIRS Optimized Collector - Test Mode[/bold cyan]")
    console.print("[bold cyan]Simulating 100 Stickman Videos Collection[/bold cyan]\n")
    
    try:
        # Run optimized collection test
        optimized_collection_test(
            keyword="stickman",
            target_count=100
        )
        
        console.print("\n[bold green]✓ Test completed successfully![/bold green]")
        console.print("\n[cyan]To collect real videos:[/cyan]")
        console.print("1. Get a YouTube API key from https://console.cloud.google.com/apis/credentials")
        console.print("2. Set the environment variable:")
        console.print("   $env:YOUTUBE_API_KEY = 'your-actual-api-key'")
        console.print("3. Run: python collect_stickman.py")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Collection cancelled by user.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())


if __name__ == "__main__":
    main()