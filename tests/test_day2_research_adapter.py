"""Tests for the Day-2A Real Research Adapter."""
from __future__ import annotations
from typing import Any
import pytest
from src.adapters.research.yairs import RealResearchAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.research import ResearchPackage, ResearchRequest


class FakeTrendingResearchService:
    def __init__(self, candidates=None, raise_exc=False):
        self._candidates = candidates or []
        self._raise = raise_exc
        self.calls = 0
        self.last_kwargs = None

    def research(self, keywords=None, region_code="US", per_keyword=10, limit=10, include_trending=True):
        self.calls += 1
        self.last_kwargs = {"keywords": keywords, "region_code": region_code}
        if self._raise:
            raise RuntimeError("Research failed")
        return self._candidates


def _make_candidate(**kwargs):
    defaults = {
        "topic": "Test Video", "source_video_id": "vid123", "source_title": "Test Title",
        "channel": "Test Channel", "view_count": 100000, "like_count": 1000,
        "comment_count": 100, "published_at": "2024-01-01T00:00:00Z",
        "views_per_day": 1000.0, "engagement_rate": 0.05, "score": 500.0,
        "keywords": ["test", "keywords"],
    }
    defaults.update(kwargs)
    return type("FakeCandidate", (), defaults)()


def test_returns_research_package():
    svc = FakeTrendingResearchService(candidates=[_make_candidate()])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="AI Learning"))
    assert isinstance(result, ResearchPackage)


def test_topic_preserved():
    svc = FakeTrendingResearchService(candidates=[_make_candidate()])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="AI Learning"))
    assert result.topic == "AI Learning"


def test_audience_preserved():
    svc = FakeTrendingResearchService(candidates=[_make_candidate()])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="Test", audience="developers"))
    assert result.target_audience == "developers"


def test_sources_mapped():
    svc = FakeTrendingResearchService(candidates=[_make_candidate(source_video_id="vid123", channel="MyChannel")])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="Test"))
    assert "youtube://MyChannel/vid123" in result.sources


def test_videos_collected():
    svc = FakeTrendingResearchService(candidates=[_make_candidate(), _make_candidate()])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="Test"))
    assert result.videos_collected == 2


def test_confidence_in_range():
    svc = FakeTrendingResearchService(candidates=[_make_candidate(score=500.0)])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="Test"))
    assert 0.0 <= result.confidence <= 1.0


def test_sub_topics_from_keywords():
    svc = FakeTrendingResearchService(candidates=[_make_candidate(keywords=["ai", "learning"])])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="Test"))
    assert result.sub_topics == ["ai", "learning"]


def test_key_facts_empty():
    svc = FakeTrendingResearchService(candidates=[_make_candidate()])
    result = RealResearchAgent(trending_research_service=svc).run(ResearchRequest(topic="Test"))
    assert result.key_facts == []


def test_empty_candidates_raises():
    svc = FakeTrendingResearchService(candidates=[])
    agent = RealResearchAgent(trending_research_service=svc)
    with pytest.raises(PipelineStageError) as exc_info:
        agent.run(ResearchRequest(topic="Test"))
    assert "No trending research candidates found" in str(exc_info.value)


def test_service_failure_raises():
    svc = FakeTrendingResearchService(raise_exc=True)
    agent = RealResearchAgent(trending_research_service=svc)
    with pytest.raises(PipelineStageError) as exc_info:
        agent.run(ResearchRequest(topic="Test"))
    assert "TrendingResearchService.research() failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_missing_service_raises():
    agent = RealResearchAgent(trending_research_service=None)
    with pytest.raises(PipelineStageError):
        agent.run(ResearchRequest(topic="Test"))


def test_service_called_with_topic():
    svc = FakeTrendingResearchService(candidates=[_make_candidate()])
    agent = RealResearchAgent(trending_research_service=svc)
    agent.run(ResearchRequest(topic="My Topic"))
    assert svc.calls == 1
    assert svc.last_kwargs["keywords"] == ["My Topic"]
