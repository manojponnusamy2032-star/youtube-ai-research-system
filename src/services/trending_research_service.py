"""Trending research service.

Ranks candidate video ideas from YouTube Data API signals (trending chart
and keyword searches) without any paid provider. Ranking is deterministic:
it combines view velocity with engagement rate.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IdeaCandidate:
    """A ranked video idea derived from an existing YouTube video."""

    topic: str
    source_video_id: str
    source_title: str
    channel: str
    view_count: int
    like_count: int
    comment_count: int
    published_at: str
    views_per_day: float
    engagement_rate: float
    score: float
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class TrendingResearchService:
    """Collects and ranks trending video ideas from YouTube signals."""

    def __init__(
        self,
        youtube_service: Any,
        min_views: int = 10_000,
        max_age_days: int = 90,
    ) -> None:
        """Initialize the trending research service.

        Args:
            youtube_service: A YouTubeService instance.
            min_views: Minimum view count for a video to be considered.
            max_age_days: Ignore videos older than this many days.
        """
        if youtube_service is None:
            raise ValueError("youtube_service is required")
        if min_views < 0:
            raise ValueError("min_views cannot be negative")
        if max_age_days <= 0:
            raise ValueError("max_age_days must be positive")

        self.youtube_service = youtube_service
        self.min_views = min_views
        self.max_age_days = max_age_days

    def research(
        self,
        keywords: list[str] | None = None,
        region_code: str = "US",
        per_keyword: int = 10,
        limit: int = 10,
    ) -> list[IdeaCandidate]:
        """Collect trending and keyword videos, then rank them as ideas.

        Args:
            keywords: Optional seed keywords to search in addition to the
                trending chart.
            region_code: Region for the trending chart and searches.
            per_keyword: Results requested per keyword search.
            limit: Maximum number of ranked ideas returned.

        Returns:
            Ranked list of IdeaCandidate, highest score first.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")

        items: dict[str, dict[str, Any]] = {}

        for item in self._safe_trending(region_code):
            video_id = item.get("id")
            if isinstance(video_id, str):
                items[video_id] = item

        for keyword in keywords or []:
            for item in self._safe_search(keyword, per_keyword):
                video_id = item.get("id")
                if isinstance(video_id, str):
                    items.setdefault(video_id, item)

        candidates = [
            candidate
            for item in items.values()
            if (candidate := self._build_candidate(item)) is not None
        ]
        candidates.sort(key=lambda c: (-c.score, c.source_video_id))
        return candidates[:limit]

    def _safe_trending(self, region_code: str) -> list[dict[str, Any]]:
        """Fetch the trending chart, tolerating API failures."""
        try:
            return self.youtube_service.get_trending_videos(region_code=region_code)
        except Exception as error:  # noqa: BLE001 - research must not hard-fail
            logger.warning(f"Trending chart unavailable: {error}")
            return []

    def _safe_search(self, keyword: str, per_keyword: int) -> list[dict[str, Any]]:
        """Search a keyword and fetch details, tolerating API failures."""
        try:
            return self.youtube_service.search_and_get_details(
                keyword, max_results=per_keyword
            )
        except Exception as error:  # noqa: BLE001 - research must not hard-fail
            logger.warning(f"Search failed for '{keyword}': {error}")
            return []

    def _build_candidate(self, item: dict[str, Any]) -> IdeaCandidate | None:
        """Convert an API video item into a scored candidate.

        Returns None when the item is malformed or filtered out.
        """
        snippet = item.get("snippet")
        if not isinstance(snippet, dict):
            return None

        statistics = item.get("statistics") or {}
        view_count = self._as_int(statistics.get("viewCount"))
        if view_count < self.min_views:
            return None

        age_days = self._age_days(snippet.get("publishedAt", ""))
        if age_days is None or age_days > self.max_age_days:
            return None

        like_count = self._as_int(statistics.get("likeCount"))
        comment_count = self._as_int(statistics.get("commentCount"))
        views_per_day = round(view_count / max(age_days, 1.0), 2)
        engagement_rate = round((like_count + comment_count) / max(view_count, 1), 5)
        score = round(views_per_day * (1.0 + engagement_rate * 10.0), 2)

        title = str(snippet.get("title", "")).strip()
        return IdeaCandidate(
            topic=title,
            source_video_id=str(item.get("id", "")),
            source_title=title,
            channel=str(snippet.get("channelTitle", "")),
            view_count=view_count,
            like_count=like_count,
            comment_count=comment_count,
            published_at=str(snippet.get("publishedAt", "")),
            views_per_day=views_per_day,
            engagement_rate=engagement_rate,
            score=score,
            keywords=self._extract_keywords(snippet),
        )

    @staticmethod
    def _extract_keywords(snippet: dict[str, Any]) -> list[str]:
        """Return the video's tags, falling back to title words."""
        tags = snippet.get("tags")
        if isinstance(tags, list) and tags:
            return [str(tag) for tag in tags[:10]]

        title = str(snippet.get("title", ""))
        words = [word.strip("#|-,.!?").lower() for word in title.split()]
        return [word for word in words if len(word) > 3][:10]

    @staticmethod
    def _as_int(value: Any) -> int:
        """Parse an API counter into an int, defaulting to zero."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _age_days(published_at: str) -> float | None:
        """Return the age of a published timestamp in days."""
        if not published_at:
            return None
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - published
        return max(delta.total_seconds() / 86400.0, 0.0)
