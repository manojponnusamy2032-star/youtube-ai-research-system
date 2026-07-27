"""
Demo script for YAIRS Collector Agent.

This script demonstrates the Collector Agent functionality
without requiring a real YouTube API key.
"""

import os
import sys
from pathlib import Path

# Set a dummy API key for demonstration
os.environ["YOUTUBE_API_KEY"] = "demo-key-for-testing"

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def demo_video_model():
    """Demonstrate Video Pydantic model."""
    console.print("\n[bold cyan]═══ Demo 1: Video Model ═══[/bold cyan]\n")
    
    from datetime import datetime, timezone
    from src.models.video import Video
    
    # Create a sample video
    video = Video(
        video_id="dQw4w9WgXcQ",
        title="Rick Astley - Never Gonna Give You Up",
        description="The official video for 'Never Gonna Give You Up'",
        channel="Rick Astley",
        channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
        published_at=datetime(2009, 10, 25, 15, 30, 0, tzinfo=timezone.utc),
        duration="PT3M33S",
        view_count=1400000000,
        like_count=15000000,
        comment_count=5000000,
        thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
        video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        search_keyword="music"
    )
    
    console.print("[green]✓[/green] Created Video model:")
    console.print(f"  Title: {video.title}")
    console.print(f"  Channel: {video.channel}")
    console.print(f"  Views: {video.view_count:,}")
    console.print(f"  Duration: {video.duration}")
    console.print(f"  Published: {video.published_at.strftime('%Y-%m-%d')}")


def demo_database():
    """Demonstrate database operations."""
    console.print("\n[bold cyan]═══ Demo 2: Database Service ═══[/bold cyan]\n")
    
    import tempfile
    from src.database.database_service import DatabaseService
    from src.models.video import Video
    from datetime import datetime, timezone
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        with DatabaseService(db_path) as db:
            # Create tables
            db.create_tables()
            console.print("[green]✓[/green] Database tables created")
            
            # Insert sample videos
            videos = [
                Video(
                    video_id=f"vid{i}",
                    title=f"Sample Video {i}",
                    description=f"Description {i}",
                    channel=f"Channel {i}",
                    channel_id=f"UC{i:011d}",
                    published_at=datetime.now(timezone.utc),
                    duration="PT10M",
                    view_count=1000 * i,
                    like_count=100 * i,
                    comment_count=50 * i,
                    thumbnail_url="https://example.com/thumb.jpg",
                    video_url=f"https://youtube.com/watch?v=vid{i}",
                    search_keyword="python"
                )
                for i in range(1, 4)
            ]
            
            inserted, skipped = db.insert_videos_batch(videos)
            console.print(f"[green]✓[/green] Inserted {inserted} videos, skipped {skipped}")
            
            # Check duplicates
            console.print(f"[green]✓[/green] Total videos in DB: {db.get_video_count()}")
            
            # Try inserting duplicate
            result = db.insert_video(videos[0])
            console.print(f"[green]✓[/green] Duplicate detection works: {not result}")
    
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


def demo_youtube_service():
    """Demonstrate YouTube service parsing."""
    console.print("\n[bold cyan]═══ Demo 3: YouTube Service ═══[/bold cyan]\n")
    
    from src.services.youtube_service import YouTubeService
    
    service = YouTubeService(api_key="demo-key")
    
    # Mock API response
    mock_item = {
        "id": "abc123xyz",
        "snippet": {
            "title": "Python Tutorial for Beginners",
            "description": "Learn Python programming in this comprehensive tutorial",
            "channelTitle": "Programming with Mosh",
            "channelId": "UCWv7vMbMWH4-V0ZXdmDpPBA",
            "publishedAt": "2024-01-15T10:30:00Z",
            "thumbnails": {
                "medium": {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg"}
            }
        },
        "statistics": {
            "viewCount": "2500000",
            "likeCount": "85000",
            "commentCount": "4200"
        },
        "contentDetails": {
            "duration": "PT1H15M30S"
        }
    }
    
    video = service.parse_video_item(mock_item, "python tutorial")
    
    console.print("[green]✓[/green] Parsed YouTube API response:")
    console.print(f"  Video ID: {video.video_id}")
    console.print(f"  Title: {video.title}")
    console.print(f"  Channel: {video.channel}")
    console.print(f"  Views: {video.view_count:,}")
    console.print(f"  Likes: {video.like_count:,}")
    console.print(f"  Duration: {video.duration}")
    console.print(f"  Search Keyword: {video.search_keyword}")


def demo_collector_agent():
    """Demonstrate Collector Agent workflow."""
    console.print("\n[bold cyan]═══ Demo 4: Collector Agent ═══[/bold cyan]\n")
    
    from unittest.mock import Mock, patch
    from src.services.youtube_service import YouTubeService
    from src.database.database_service import DatabaseService
    from src.agents.collector_agent import CollectorAgent
    from src.models.video import Video
    from datetime import datetime, timezone
    
    # Create mock services
    youtube_service = Mock(spec=YouTubeService)
    database_service = Mock(spec=DatabaseService)
    
    # Mock responses
    mock_video_item = {
        "id": "test123",
        "snippet": {
            "title": "Test Video",
            "description": "Test description",
            "channelTitle": "Test Channel",
            "channelId": "UC123",
            "publishedAt": "2024-01-01T00:00:00Z",
            "thumbnails": {"medium": {"url": "https://example.com/thumb.jpg"}}
        },
        "statistics": {
            "viewCount": "1000",
            "likeCount": "100",
            "commentCount": "50"
        },
        "contentDetails": {
            "duration": "PT10M30S"
        }
    }
    
    youtube_service.search_and_get_details.return_value = [mock_video_item]
    youtube_service.parse_video_item.return_value = Video(
        video_id="test123",
        title="Test Video",
        description="Test description",
        channel="Test Channel",
        channel_id="UC123",
        published_at=datetime.now(timezone.utc),
        duration="PT10M30S",
        view_count=1000,
        like_count=100,
        comment_count=50,
        thumbnail_url="https://example.com/thumb.jpg",
        video_url="https://youtube.com/watch?v=test123",
        search_keyword="python"
    )
    
    database_service.insert_videos_batch.return_value = (1, 0)
    
    # Create and run agent
    agent = CollectorAgent(youtube_service, database_service)
    
    console.print("[green]✓[/green] Collector Agent initialized")
    console.print("[green]✓[/green] Workflow demonstration:")
    console.print("  1. Search YouTube for videos")
    console.print("  2. Retrieve detailed metadata")
    console.print("  3. Validate with Pydantic")
    console.print("  4. Save to SQLite database")
    console.print("  5. Print collection summary")
    
    # Run the agent
    new_count, skipped_count = agent.run("python", 10)
    
    console.print(f"\n[green]✓[/green] Collection complete!")
    console.print(f"  New videos: {new_count}")
    console.print(f"  Skipped: {skipped_count}")


def main():
    """Run all demonstrations."""
    console.print(Panel(
        Text("YAIRS Collector Agent - Demo", style="bold cyan"),
        border_style="cyan",
        padding=(1, 2)
    ))
    
    try:
        demo_video_model()
        demo_database()
        demo_youtube_service()
        demo_collector_agent()
        
        console.print("\n[bold green]═══ All Demos Completed Successfully! ═══[/bold green]\n")
        
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())


if __name__ == "__main__":
    main()