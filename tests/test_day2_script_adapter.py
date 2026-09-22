"""Tests for the Day-2 Script Adapter."""
from __future__ import annotations
from typing import Any
import pytest
from src.adapters.script.yairs import RealScriptAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.strategy import StrategyPackage
from src.orchestration.schemas.script import ScriptPackage, ScriptSection


class FakeContentService:
    def __init__(self, script=None, raise_exc=False):
        self._script = script or {
            "intro": "Welcome to this video about AI Learning.",
            "sections": [
                {"heading": "Introduction", "content": "This is the first section narration.", "duration_seconds": 10},
                {"heading": "Main Point", "content": "This is the second section with more content.", "duration_seconds": 15},
            ],
            "cta": "Subscribe for more content.",
            "estimated_duration_minutes": 5,
            "scenes": [{"scene_number": 1, "narration": "Scene 1 narration"}],
        }
        self._raise = raise_exc
        self.calls = 0

    def generate_script(self, **kwargs):
        self.calls += 1
        if self._raise:
            raise RuntimeError("Script gen failed")
        return self._script


def _make_strategy(**overrides):
    defaults = {
        "topic": "AI Learning", "angle": "Test angle", "narrative_outline": ["outline1"],
        "key_messages": ["msg1"], "emotional_triggers": ["curiosity"], "hook_idea": "Test hook",
        "call_to_action": "Subscribe", "target_audience": "developers", "confidence": 0.8,
        "best_title": {"title": "My AI Title", "confidence": 85.0},
        "hook": {"script": "Hook script text", "hook_type": "Curiosity"},
        "generated_titles": [{"title": "T1"}], "pattern_report": {"hooks": {}},
        "knowledge_base": [{"pattern": "p1"}], "trend_info": {"candidate_count": 5},
    }
    defaults.update(overrides)
    return StrategyPackage(**defaults)


def test_returns_script_package():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert isinstance(result, ScriptPackage)

def test_topic_preserved():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert result.topic == "AI Learning"

def test_title_from_best_title():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy(best_title={"title": "Custom Title", "confidence": 90.0}))
    assert result.title == "Custom Title"

def test_hook_from_strategy():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy(hook={"script": "My hook text"}))
    assert result.hook == "My hook text"

def test_sections_created():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert len(result.sections) == 2
    assert all(isinstance(s, ScriptSection) for s in result.sections)

def test_section_headings():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert result.sections[0].heading == "Introduction"

def test_section_narration():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert result.sections[0].narration == "This is the first section narration."

def test_total_duration():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert result.total_duration_seconds == 25

def test_cta_preserved():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert result.call_to_action == "Subscribe for more content."

def test_intro_preserved():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert result.intro == "Welcome to this video about AI Learning."

def test_section_payloads_preserved():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert len(result.section_payloads) == 2

def test_scene_payloads_preserved():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert len(result.scene_payloads) == 1

def test_estimated_duration():
    result = RealScriptAgent(content_generation_service=FakeContentService()).run(_make_strategy())
    assert result.estimated_duration_minutes == 5

def test_missing_service_raises():
    agent = RealScriptAgent(content_generation_service=None)
    with pytest.raises(PipelineStageError):
        agent.run(_make_strategy())

def test_service_failure_raises():
    agent = RealScriptAgent(content_generation_service=FakeContentService(raise_exc=True))
    with pytest.raises(PipelineStageError) as exc_info:
        agent.run(_make_strategy())
    assert "generate_script" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)

def test_malformed_response_raises():
    agent = RealScriptAgent(content_generation_service=FakeContentService(script={"no_sections": True}))
    with pytest.raises(PipelineStageError):
        agent.run(_make_strategy())

def test_empty_sections_raises():
    agent = RealScriptAgent(content_generation_service=FakeContentService(script={"sections": []}))
    with pytest.raises(PipelineStageError):
        agent.run(_make_strategy())

def test_service_called():
    svc = FakeContentService()
    RealScriptAgent(content_generation_service=svc).run(_make_strategy())
    assert svc.calls == 1
