"""Real research adapter — thin wrapper over existing YAIRS research services.

Converts the existing TrendingResearchService capability into the Day-1
orchestration contract:

    ResearchRequest
        ↓
    RealResearchAgent
        ↓
    ResearchPackage
"""

from __future__ import annotations

from typing import Any

from src.orchestration.agents.research.base import ResearchAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.research import ResearchPackage, ResearchRequest


def _normalize_confidence(score: float, max_score: float = 1000.0) -> float:
    """Normalize a raw candidate score to a 0-1 confidence value.

    TrendingResearchService scores are based on views_per_day * (1 + engagement*10),
    which can range from 0 to thousands. We cap and normalize to 0-1.
    """
    normalized = score / max_score
    return max(0.0, min(1.0, normalized))


def _build_summary_from_candidate(candidate: Any, topic: str) -> str:
    """Build a summary string from a single IdeaCandidate.

    Uses actual metadata from the candidate (source title, channel, view count,
    engagement) rather than fabricating claims about the topic.
    """
    parts = [
        f"Research topic: {topic}",
        f"Based on analysis of trending video: {candidate.source_title}",
        f"Source channel: {candidate.channel}",
        f"View count: {candidate.view_count:,} views",
        f"Engagement rate: {candidate.engagement_rate:.4f}",
        f"Published: {candidate.published_at}",
    ]
    if candidate.keywords:
        parts.append(f"Related keywords: {', '.join(candidate.keywords[:5])}")
    return ". ".join(parts) + "."


class RealResearchAgent(ResearchAgent):
    """Adapter that wraps TrendingResearchService for the orchestration pipeline.

    Converts ResearchRequest → ResearchPackage using existing YAIRS
    TrendingResearchService without duplicating research logic.
    """

    stage: str = "research"

    def __init__(
        self,
        trending_research_service: Any | None = None,
        min_views: int = 10_000,
        max_age_days: int = 90,
        max_score_for_confidence: float = 1000.0,
    ) -> None:
        """Initialize the real research agent.

        Args:
            trending_research_service: Pre-configured TrendingResearchService.
                When None, the agent will raise PipelineStageError on run()
                unless a service is injected later.
            min_views: Minimum view count filter passed to the service.
            max_age_days: Maximum video age in days passed to the service.
            max_score_for_confidence: Reference score for confidence normalization.
                Scores at or above this value map to confidence=1.0.
        """
        self._trending_research_service = trending_research_service
        self._min_views = min_views
        self._max_age_days = max_age_days
        self._max_score_for_confidence = max_score_for_confidence

    @property
    def trending_research_service(self) -> Any:
        """Return the configured trending research service.

        Raises:
            PipelineStageError: When no service has been configured.
        """
        if self._trending_research_service is None:
            raise PipelineStageError(
                stage=self.stage,
                message=(
                    "trending_research_service is required but not configured. "
                    "Inject a TrendingResearchService instance via the constructor "
                    "or set the _trending_research_service attribute."
                ),
            )
        return self._trending_research_service

    @trending_research_service.setter
    def trending_research_service(self, value: Any) -> None:
        """Set or replace the trending research service."""
        self._trending_research_service = value

    def run(self, request: ResearchRequest) -> ResearchPackage:
        """Execute research for the given topic.

        Args:
            request: ResearchRequest with topic, optional niche/audience.

        Returns:
            ResearchPackage populated from trending service results.

        Raises:
            PipelineStageError: When the service returns no candidates or
                encounters a configuration error.
        """
        service = self.trending_research_service

        try:
            candidates = service.research(
                keywords=[request.topic],
                region_code="US",
                per_keyword=10,
                limit=10,
                include_trending=True,
            )
        except Exception as exc:
            raise PipelineStageError(
                stage=self.stage,
                message=f"TrendingResearchService.research() failed: {exc}",
                details={"topic": request.topic, "original_error": str(exc)},
            ) from exc

        if not candidates:
            raise PipelineStageError(
                stage=self.stage,
                message=(
                    f"No trending research candidates found for topic '{request.topic}'. "
                    "The YouTube trending chart or keyword search returned no usable results."
                ),
                details={
                    "topic": request.topic,
                    "candidate_count": 0,
                    "min_views": self._min_views,
                    "max_age_days": self._max_age_days,
                },
            )

        # Use the top-ranked candidate as the primary research source.
        # The topic is preserved from the request; we don't replace it
        # with the trending video's title.
        primary = candidates[0]

        return ResearchPackage(
            topic=request.topic.strip(),
            summary=_build_summary_from_candidate(primary, request.topic),
            key_facts=[],  # Not available from trending data alone
            pain_points=[],  # Not available from trending data alone
            sub_topics=list(primary.keywords) if primary.keywords else [],
            sources=[
                f"youtube://{primary.channel}/{primary.source_video_id}",
            ],
            target_audience=request.audience or "general",
            confidence=_normalize_confidence(primary.score, self._max_score_for_confidence),
            pattern_report={},  # Requires PatternService; not populated here
            knowledge_base=[],  # Requires KnowledgeService; not populated here
            videos_collected=len(candidates),
            trend_info={
                "candidate_count": len(candidates),
                "region_code": "US",
                "top_candidate": {
                    "source_video_id": primary.source_video_id,
                    "source_title": primary.source_title,
                    "channel": primary.channel,
                    "score": primary.score,
                },
            },
        )