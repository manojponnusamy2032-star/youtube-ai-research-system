"""Tests for the Day-2B Real Strategy Adapter."""
from __future__ import annotations
from typing import Any
import pytest
from src.adapters.strategy.yairs import RealStrategyAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.research import ResearchPackage
from src.orchestration.schemas.strategy import StrategyPackage


class FakeTitleService:
    def __init__(self, titles=None, best=None, raise_gen=False, raise_sel=False):
        self._titles = titles or []
        self._best = best if best is not None else {"title": "Test Title", "confidence": 80.0}
        self._raise_gen = raise_gen
        self._raise_sel = raise_sel
        self.gen_calls = 0
        self.last_gen_kwargs = None

    def generate_titles(self, topic, niche=None, audience=None, trend_data=None, count=20):
        self.gen_calls += 1
        self.last_gen_kwargs = {"topic": topic, "niche": niche, "audience": audience}
        if self._raise_gen:
            raise RuntimeError("Title gen failed")
        return self._titles

    def select_best_title(self, titles, topic):
        if self._raise_sel:
            raise RuntimeError("Select failed")
        return self._best


class FakeContentService:
    def __init__(self, hook=None, raise_hook=False):
        self._hook = hook or {"script": "Test hook script", "hook_type": "Curiosity", "retention_score": 75.0}
        self._raise_hook = raise_hook
        self.hook_calls = 0
        self.last_hook_kwargs = None

    def generate_hook(self, **kwargs):
        self.hook_calls += 1
        self.last_hook_kwargs = kwargs
        if self._raise_hook:
            raise RuntimeError("Hook gen failed")
        return self._hook


def _make_research(**overrides):
    defaults = {
        "topic": "AI Learning Strategies", "summary": "Test", "key_facts": ["f1"],
        "pain_points": ["p1"], "sub_topics": ["s1"], "sources": ["src1"],
        "target_audience": "developers", "confidence": 0.8,
        "pattern_report": {"hooks": {"Curiosity": 50.0}}, "knowledge_base": [{"pattern": "test"}],
        "videos_collected": 5, "trend_info": {"candidate_count": 5},
    }
    defaults.update(overrides)
    return ResearchPackage(**defaults)


def _make_agent(titles=None, best=None, hook=None, raise_gen=False, raise_sel=False, raise_hook=False):
    if titles is None:
        titles = [{"title": "Default Test Title", "confidence": 80.0, "pattern_used": "Curiosity"}]
    if best is None:
        best = titles[0] if titles else {"title": "Default Test Title", "confidence": 80.0}
    return RealStrategyAgent(
        title_generation_service=FakeTitleService(titles=titles, best=best, raise_gen=raise_gen, raise_sel=raise_sel),
        content_generation_service=FakeContentService(hook=hook, raise_hook=raise_hook),
    )


class TestSuccessfulGeneration:
    def test_returns_strategy_package(self):
        assert isinstance(_make_agent().run(_make_research()), StrategyPackage)

    def test_topic_preserved(self):
        assert _make_agent().run(_make_research()).topic == "AI Learning Strategies"

    def test_target_audience_preserved(self):
        assert _make_agent().run(_make_research()).target_audience == "developers"

    def test_angle_populated(self):
        result = _make_agent().run(_make_research())
        assert result.angle and "AI Learning Strategies" in result.angle

    def test_hook_idea_populated(self):
        result = _make_agent(hook={"script": "My hook", "hook_type": "Curiosity", "retention_score": 75.0}).run(_make_research())
        assert result.hook_idea == "My hook"

    def test_best_title_preserved(self):
        best = {"title": "My Best Title", "confidence": 85.0}
        result = _make_agent(titles=[best], best=best).run(_make_research())
        assert result.best_title.get("title") == "My Best Title"

    def test_hook_dict_preserved(self):
        hook = {"script": "Hook text", "hook_type": "Shock", "retention_score": 80.0}
        result = _make_agent(hook=hook).run(_make_research())
        assert result.hook.get("script") == "Hook text"
        assert result.hook.get("hook_type") == "Shock"

    def test_generated_titles_preserved(self):
        result = _make_agent(titles=[{"title": "T1"}, {"title": "T2"}]).run(_make_research())
        assert len(result.generated_titles) == 2

    def test_pattern_report_preserved(self):
        result = _make_agent().run(_make_research())
        assert result.pattern_report.get("hooks", {}).get("Curiosity") == 50.0

    def test_knowledge_base_preserved(self):
        result = _make_agent().run(_make_research())
        assert len(result.knowledge_base) == 1

    def test_confidence_in_range(self):
        result = _make_agent().run(_make_research())
        assert 0.0 <= result.confidence <= 1.0

    def test_narrative_outline_populated(self):
        result = _make_agent().run(_make_research())
        assert len(result.narrative_outline) > 0

    def test_key_messages_populated(self):
        result = _make_agent().run(_make_research())
        assert len(result.key_messages) > 0

    def test_emotional_triggers_populated(self):
        result = _make_agent(hook={"script": "Hook", "hook_type": "Curiosity", "retention_score": 75.0}).run(_make_research())
        assert len(result.emotional_triggers) > 0

    def test_call_to_action_populated(self):
        result = _make_agent().run(_make_research())
        assert bool(result.call_to_action)


class TestServiceCalls:
    def test_generate_titles_called(self):
        ts = FakeTitleService(titles=[{"title": "T", "confidence": 80.0}])
        cs = FakeContentService()
        agent = RealStrategyAgent(title_generation_service=ts, content_generation_service=cs)
        agent.run(_make_research())
        assert ts.gen_calls == 1

    def test_topic_passed_to_titles(self):
        ts = FakeTitleService(titles=[{"title": "T", "confidence": 80.0}])
        cs = FakeContentService()
        agent = RealStrategyAgent(title_generation_service=ts, content_generation_service=cs)
        agent.run(_make_research())
        assert ts.last_gen_kwargs["topic"] == "AI Learning Strategies"

    def test_audience_passed_to_titles(self):
        ts = FakeTitleService(titles=[{"title": "T", "confidence": 80.0}])
        cs = FakeContentService()
        agent = RealStrategyAgent(title_generation_service=ts, content_generation_service=cs)
        agent.run(_make_research())
        assert ts.last_gen_kwargs["audience"] == "developers"

    def test_hook_called(self):
        ts = FakeTitleService(titles=[{"title": "T", "confidence": 80.0}])
        cs = FakeContentService()
        agent = RealStrategyAgent(title_generation_service=ts, content_generation_service=cs)
        agent.run(_make_research())
        assert cs.hook_calls == 1

    def test_topic_passed_to_hook(self):
        ts = FakeTitleService(titles=[{"title": "T", "confidence": 80.0}])
        cs = FakeContentService()
        agent = RealStrategyAgent(title_generation_service=ts, content_generation_service=cs)
        agent.run(_make_research())
        assert cs.last_hook_kwargs["topic"] == "AI Learning Strategies"


class TestMissingServices:
    def test_missing_title_service_raises(self):
        agent = RealStrategyAgent(title_generation_service=None, content_generation_service=FakeContentService())
        with pytest.raises(PipelineStageError) as exc_info:
            agent.run(_make_research())
        assert exc_info.value.stage == "strategy"

    def test_missing_content_service_raises(self):
        agent = RealStrategyAgent(title_generation_service=FakeTitleService(), content_generation_service=None)
        with pytest.raises(PipelineStageError) as exc_info:
            agent.run(_make_research())
        assert exc_info.value.stage == "strategy"


class TestServiceFailures:
    def test_title_generation_failure_raises(self):
        agent = _make_agent(raise_gen=True)
        with pytest.raises(PipelineStageError) as exc_info:
            agent.run(_make_research())
        assert "generate_titles" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_hook_generation_failure_raises(self):
        agent = _make_agent(raise_hook=True)
        with pytest.raises(PipelineStageError) as exc_info:
            agent.run(_make_research())
        assert "generate_hook" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_empty_titles_raises(self):
        agent = _make_agent(titles=[])
        with pytest.raises(PipelineStageError):
            agent.run(_make_research())

    def test_invalid_best_title_raises(self):
        best = {"title": "Valid", "confidence": 80.0}
        agent = _make_agent(titles=[best], best={"no_title": "oops"})
        with pytest.raises(PipelineStageError):
            agent.run(_make_research())


class TestConfidenceBounds:
    @pytest.mark.parametrize("score", [0.0, 50.0, 100.0, 150.0])
    def test_confidence_in_range(self, score):
        best = {"title": "T", "confidence": score}
        result = _make_agent(titles=[best], best=best).run(_make_research())
        assert 0.0 <= result.confidence <= 1.0