"""
Auto-Publish Runner.

Two commands:

    research  Rank trending video ideas from YouTube Data API signals.
    publish   Render a video plan locally and optionally upload it.

Both commands print JSON so an automation can consume the output directly.
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, VideoPlan  # noqa: E402
from src.services.scene_video_renderer import FORMATS  # noqa: E402
from src.services.trending_research_service import TrendingResearchService  # noqa: E402
from src.services.youtube_service import YouTubeService  # noqa: E402


def run_research(args: argparse.Namespace) -> int:
    """Print ranked trending idea candidates as JSON."""
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print(json.dumps({"status": "failed", "error": "YOUTUBE_API_KEY is not set"}))
        return 1

    youtube_service = YouTubeService(api_key)
    try:
        service = TrendingResearchService(youtube_service)
        ideas = service.research(
            keywords=args.keyword,
            region_code=args.region,
            limit=args.limit,
            include_trending=args.include_trending or not args.keyword,
        )
    finally:
        youtube_service.close()

    print(
        json.dumps(
            {"status": "completed", "ideas": [idea.to_dict() for idea in ideas]},
            indent=2,
        )
    )
    return 0


def run_publish(args: argparse.Namespace) -> int:
    """Render a plan and optionally upload the result."""
    plan = VideoPlan.from_file(args.plan)
    if args.format:
        plan.video_format = args.format
    if args.visibility:
        plan.privacy_status = args.visibility

    pipeline = AutoPublishPipeline(output_directory=args.output_dir)
    result = pipeline.run(plan, upload=args.upload)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "completed" else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(description="YouTube auto-publish pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    research = subparsers.add_parser("research", help="Rank trending video ideas")
    research.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Seed keyword to search (repeatable)",
    )
    research.add_argument(
        "--include-trending",
        action="store_true",
        help="Also rank the global trending chart when keywords are given",
    )
    research.add_argument("--region", default="US", help="Region code (default: US)")
    research.add_argument("--limit", type=int, default=10, help="Number of ideas")
    research.set_defaults(handler=run_research)

    publish = subparsers.add_parser("publish", help="Render and optionally upload")
    publish.add_argument("--plan", required=True, help="Path to a plan JSON file")
    publish.add_argument(
        "--format", choices=sorted(FORMATS), help="Override the plan video format"
    )
    publish.add_argument(
        "--visibility",
        choices=["public", "unlisted", "private"],
        help="Override the plan privacy status",
    )
    publish.add_argument(
        "--output-dir", default="output/publish", help="Working directory"
    )
    publish.add_argument(
        "--upload", action="store_true", help="Upload the rendered video to YouTube"
    )
    publish.set_defaults(handler=run_publish)

    return parser


def main() -> int:
    """Entry point."""
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
