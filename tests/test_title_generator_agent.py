"""Tests for title generator agent behavior and context integration."""

from __future__ import annotations

from src.agents.title_generator_agent import TitleGeneratorAgent
from src.core.context import WorkflowContext
from src.database.database_service import DatabaseService
from src.models.title import TitleCandidate


class TitleServiceStub:
    """Stub title service returning deterministic candidates."""

    def generate_titles(self, topic, niche=None, audience=None, trend_data=None, count=20):
        return [
            TitleCandidate(
                title=f"{topic} Title {index + 1}",
                pattern_used="Curiosity",
                emotion="Curiosity",
                title_formula="How I ...",
                estimated_ctr=8.5,
                confidence=90.0 - index * 0.1,
                reason="Based on dominant curiosity patterns.",
            )
            for index in range(count)
        ]


def test_agent_generates_titles_and_updates_context() -> None:
    context = WorkflowContext({
        "title_topic": "AI growth",
        "niche": "education",
        "audience": "new creators",
        "trend_data": ["AI Shorts"],
        "title_count": 20,
    })
    agent = TitleGeneratorAgent(TitleServiceStub(), DatabaseService(":memory:"))

    result = agent.run(context)

    assert result.success is True
    assert result.data["count"] == 20
    assert len(result.data["titles"]) == 20
    assert context.get("generated_titles_count") == 20
    assert len(context.get("generated_titles")) == 20


def test_agent_fails_without_topic() -> None:
    context = WorkflowContext({})
    agent = TitleGeneratorAgent(TitleServiceStub(), DatabaseService(":memory:"))

    result = agent.run(context)

    assert result.success is False
    assert "topic" in result.message.lower()
