"""Tests for TrendingResearchService and YouTubeService.get_trending_videos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.services.trending_research_service import TrendingResearchService
from src.services.youtube_service import YouTubeService


def _video(
    video_id: str,
    views: int,
    likes: int = 0,
    comments: int = 0,
    age_days: int = 1,
    title: str = "How to build an AI agent",
) -> dict[str, Any]:
    """Build a YouTube API video item."""
    published = datetime.now(timezone.utc) - timedelta(days=age_days)
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "channelTitle": "Test Channel",
            "publishedAt": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "statistics": {
            "viewCount": str(views),
            "likeCount": str(likes),
            "commentCount": str(comments),
        },
    }


class _FakeYouTubeService:
    """Minimal YouTubeService stand-in."""

    def __init__(self, trending: list[dict[str, Any]]) -> None:
        self.trending = trending
        self.search_calls: list[str] = []

    def get_trending_videos(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.trending

    def search_and_get_details(
        self, keyword: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self.search_calls.append(keyword)
        return []


def test_research_ranks_by_velocity_and_engagement() -> None:
    """Higher velocity and engagement rank first."""
    service = TrendingResearchService(
        _FakeYouTubeService(
            [
                _video("slow", views=100_000, likes=100, age_days=50),
                _video("fast", views=500_000, likes=50_000, comments=5_000, age_days=2),
            ]
        )
    )

    ideas = service.research(limit=5)

    assert [idea.source_video_id for idea in ideas] == ["fast", "slow"]
    assert ideas[0].score > ideas[1].score


def test_research_filters_low_view_and_stale_videos() -> None:
    """Videos below the view floor or past the age limit are dropped."""
    service = TrendingResearchService(
        _FakeYouTubeService(
            [
                _video("tiny", views=10),
                _video("stale", views=1_000_000, age_days=400),
                _video("keep", views=200_000, likes=1_000),
            ]
        ),
        min_views=10_000,
        max_age_days=90,
    )

    ideas = service.research(limit=5)

    assert [idea.source_video_id for idea in ideas] == ["keep"]


def test_research_respects_limit_and_searches_keywords() -> None:
    """Keyword searches are issued and the limit is honoured."""
    fake = _FakeYouTubeService(
        [_video(f"v{index}", views=100_000) for index in range(5)]
    )
    service = TrendingResearchService(fake)

    ideas = service.research(keywords=["ai agents", "automation"], limit=2)

    assert len(ideas) == 2
    assert fake.search_calls == ["ai agents", "automation"]


def test_research_can_exclude_the_trending_chart() -> None:
    """Niche runs keep only keyword search results."""
    fake = _FakeYouTubeService([_video("chart", views=1_000_000, likes=100_000)])
    fake.search_and_get_details = MagicMock(
        return_value=[_video("niche", views=50_000, likes=1_000)]
    )
    service = TrendingResearchService(fake)

    ideas = service.research(keywords=["ai agents"], limit=5, include_trending=False)

    assert [idea.source_video_id for idea in ideas] == ["niche"]


def test_research_tolerates_api_errors() -> None:
    """A failing API call does not abort the research run."""
    fake = _FakeYouTubeService([_video("keep", views=100_000)])
    fake.search_and_get_details = MagicMock(side_effect=RuntimeError("quota"))
    service = TrendingResearchService(fake)

    ideas = service.research(keywords=["ai"], limit=5)

    assert [idea.source_video_id for idea in ideas] == ["keep"]


def test_get_trending_videos_builds_expected_request() -> None:
    """The trending call targets the mostPopular chart."""
    service = YouTubeService("test-key")
    service._make_request = MagicMock(return_value={"items": [_video("a", 1)]})

    items = service.get_trending_videos(
        region_code="IN", category_id="28", max_results=5
    )

    assert len(items) == 1
    endpoint, params = service._make_request.call_args[0]
    assert endpoint == "videos"
    assert params["chart"] == "mostPopular"
    assert params["regionCode"] == "IN"
    assert params["videoCategoryId"] == "28"
    assert params["maxResults"] == 5


@pytest.mark.parametrize("max_results", [0, 51])
def test_get_trending_videos_validates_max_results(max_results: int) -> None:
    """Out-of-range result counts are rejected."""
    service = YouTubeService("test-key")

    with pytest.raises(ValueError):
        service.get_trending_videos(max_results=max_results)


def test_get_trending_videos_validates_region() -> None:
    """An empty region code is rejected."""
    service = YouTubeService("test-key")

    with pytest.raises(ValueError):
        service.get_trending_videos(region_code="  ")
