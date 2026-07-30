"""
Main entry point for YouTube AI Research System.

This module provides the CLI interface for running the Collector Agent.
"""

import sys
from pathlib import Path

# Add project root and src to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import logging
from rich.console import Console
from rich.prompt import Prompt

from src.core.bootstrap import create_manager

from src.utils.config import config
from src.utils.logger import setup_logger
from src.services.youtube_service import YouTubeService, YouTubeAPIError
from src.database.database_service import DatabaseService
from src.agents.collector_agent import CollectorAgent


console = Console()


def initialize_services() -> tuple[YouTubeService, DatabaseService]:
    """
    Initialize and configure all required services.
    
    Returns:
        Tuple of (YouTubeService, DatabaseService)
        
    Raises:
        SystemExit: If initialization fails
    """
    try:
        # Setup logging
        setup_logger(
            name="yairs",
            level=config.LOG_LEVEL,
            log_file=config.LOG_FILE,
            console_output=True
        )
        
        logger = logging.getLogger("yairs.main")
        logger.info("Initializing YAIRS Collector Agent...")
        
        # Initialize YouTube service
        youtube_service = YouTubeService(api_key=config.YOUTUBE_API_KEY)
        logger.info("YouTube service initialized")
        
        # Initialize database service
        database_service = DatabaseService(db_path=config.database_url)
        database_service.connect()
        database_service.create_tables()
        logger.info("Database service initialized")
        
        return youtube_service, database_service
        
    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Initialization failed: {e}[/red]")
        raise SystemExit(1)


def run_single_collection(youtube_service: YouTubeService, database_service: DatabaseService) -> None:
    """Run collection for a single keyword."""
    try:
        # Get keyword from user
        keyword = Prompt.ask("\n[cyan]Enter search keyword[/cyan]")
        
        if not keyword or not keyword.strip():
            console.print("[yellow]Keyword cannot be empty.[/yellow]")
            return
        
        # Get max results
        max_results = Prompt.ask(
            "[cyan]Max results[/cyan]",
            default=str(config.DEFAULT_MAX_RESULTS)
        )
        
        try:
            max_results = int(max_results)
            if not 1 <= max_results <= 50:
                console.print("[yellow]Max results must be between 1 and 50. Using default.[/yellow]")
                max_results = config.DEFAULT_MAX_RESULTS
        except ValueError:
            console.print("[yellow]Invalid number. Using default.[/yellow]")
            max_results = config.DEFAULT_MAX_RESULTS
        
        # Create and run collector agent
        agent = CollectorAgent(youtube_service, database_service)
        new_count, skipped_count = agent.run(keyword.strip(), max_results)
        
        console.print(f"\n[green]Collection complete![/green]")
        console.print(f"New videos: {new_count}")
        console.print(f"Skipped: {skipped_count}")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Collection cancelled by user.[/yellow]")
    except YouTubeAPIError as e:
        console.print(f"[red]YouTube API error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def run_batch_collection(youtube_service: YouTubeService, database_service: DatabaseService) -> None:
    """Run collection for multiple keywords."""
    try:
        console.print("\n[cyan]Batch Collection Mode[/cyan]")
        console.print("Enter keywords (one per line, empty line to finish):\n")
        
        keywords = []
        while True:
            keyword = Prompt.ask(f"Keyword {len(keywords) + 1}", default="")
            
            if not keyword or not keyword.strip():
                break
            
            keywords.append(keyword.strip())
        
        if not keywords:
            console.print("[yellow]No keywords provided.[/yellow]")
            return
        
        # Get max results
        max_results = Prompt.ask(
            "\n[cyan]Max results per keyword[/cyan]",
            default=str(config.DEFAULT_MAX_RESULTS)
        )
        
        try:
            max_results = int(max_results)
            if not 1 <= max_results <= 50:
                console.print("[yellow]Max results must be between 1 and 50. Using default.[/yellow]")
                max_results = config.DEFAULT_MAX_RESULTS
        except ValueError:
            console.print("[yellow]Invalid number. Using default.[/yellow]")
            max_results = config.DEFAULT_MAX_RESULTS
        
        # Create and run collector agent
        agent = CollectorAgent(youtube_service, database_service)
        new_count, skipped_count = agent.run_batch(keywords, max_results)
        
        console.print(f"\n[green]Batch collection complete![/green]")
        console.print(f"Total new videos: {new_count}")
        console.print(f"Total skipped: {skipped_count}")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Collection cancelled by user.[/yellow]")
    except YouTubeAPIError as e:
        console.print(f"[red]YouTube API error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def show_database_stats(database_service: DatabaseService) -> None:
    """Show database statistics."""
    try:
        count = database_service.get_video_count()
        console.print(f"\n[cyan]Database Statistics:[/cyan]")
        console.print(f"Total videos in database: [green]{count}[/green]")
    except Exception as e:
        console.print(f"[red]Error fetching stats: {e}[/red]")


def main() -> None:
    """Main application entry point."""
    console.print("[bold cyan]YouTube AI Research System (YAIRS)[/bold cyan]")
    console.print("[bold cyan]Collector Agent v1.0[/bold cyan]\n")
    
    # Initialize services
    youtube_service, database_service = initialize_services()
    
    try:
        while True:
            console.print("\n[bold]Menu:[/bold]")
            console.print("1. Collect videos (single keyword)")
            console.print("2. Collect videos (batch keywords)")
            console.print("3. Show database statistics")
            console.print("4. Exit")
            
            choice = Prompt.ask("\n[cyan]Select option[/cyan]", choices=["1", "2", "3", "4"], default="1")
            
            if choice == "1":
                run_single_collection(youtube_service, database_service)
            elif choice == "2":
                run_batch_collection(youtube_service, database_service)
            elif choice == "3":
                show_database_stats(database_service)
            elif choice == "4":
                console.print("\n[green]Goodbye![/green]")
                break
        
    finally:
        # Cleanup
        database_service.disconnect()
        youtube_service.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Application terminated by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        sys.exit(1)