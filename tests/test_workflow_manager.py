"""Unit tests for workflow orchestration manager agent."""

from __future__ import annotations

from src.agents.workflow_manager_agent import WorkflowManagerAgent
from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext


class CollectorStub:
    def __init__(self, result=(3, 1), should_fail: bool = False) -> None:
        self.result = result
        self.should_fail = should_fail
        self.called = False

    def run(self, keyword: str, max_results: int = 50):
        self.called = True
        if self.should_fail:
            raise RuntimeError("collector failed")
        return self.result


class TranscriptStub:
    def __init__(self, result=(2, 1, 0, 0), should_fail: bool = False) -> None:
        self.result = result
        self.should_fail = should_fail
        self.called = False

    def run(self, limit: int = 50):
        self.called = True
        if self.should_fail:
            raise RuntimeError("transcript failed")
        return self.result


class AnalysisStub:
    def __init__(self, result=(2, 0, 0), should_fail: bool = False) -> None:
        self.result = result
        self.should_fail = should_fail
        self.called = False

    def run(self, limit: int = 50, force_reanalyze: bool = False):
        self.called = True
        if self.should_fail:
            raise RuntimeError("analysis failed")
        return self.result


class PatternStub:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.called = False
        self.context_ids: list[int] = []

    def run(self, context: WorkflowContext) -> AgentResult:
        self.called = True
        self.context_ids.append(id(context))
        if self.should_fail:
            return AgentResult.fail("pattern failed")
        report = {
            "hooks": {"Curiosity": 68.0},
            "stories": {"Problem-Solution": 72.0},
            "emotions": {"Fear": 21.0},
            "titles": {"How To": 55.0},
            "thumbnail_psychology": {"Mystery": 43.0},
            "retention": {"Open Loop": 61.0},
        }
        context.set("pattern_report", report)
        return AgentResult.ok(report=report)


class KnowledgeStub:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.called = False
        self.received_pattern_report = False
        self.context_ids: list[int] = []

    def run(self, context: WorkflowContext) -> AgentResult:
        self.called = True
        self.context_ids.append(id(context))
        self.received_pattern_report = context.has("pattern_report")
        if self.should_fail:
            return AgentResult.fail("knowledge failed")
        context.set("knowledge_entries_saved", 6)
        return AgentResult.ok(saved_entries=6)


class TitleStub:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.called = False

    def run(self, context: WorkflowContext) -> AgentResult:
        self.called = True
        if self.should_fail:
            return AgentResult.fail("title failed")
        context.set("generated_titles_count", 20)
        return AgentResult.ok(count=20, titles=[{"title": "Example"}])


def _build_manager(
    collector: CollectorStub,
    transcript: TranscriptStub,
    analysis: AnalysisStub,
    pattern: PatternStub,
    knowledge: KnowledgeStub,
    title: TitleStub | None = None,
) -> WorkflowManagerAgent:
    return WorkflowManagerAgent(
        collector_agent=collector,
        transcript_agent=transcript,
        analysis_agent=analysis,
        pattern_extractor_agent=pattern,
        knowledge_base_agent=knowledge,
        title_generator_agent=title,
    )


def test_successful_workflow() -> None:
    context = WorkflowContext({"keyword": "ai automation", "limit": 10})
    manager = _build_manager(CollectorStub(), TranscriptStub(), AnalysisStub(), PatternStub(), KnowledgeStub())

    result = manager.run(context)
    report = result.data["report"]

    assert result.success is True
    assert report["collector"]["success"] is True
    assert report["transcript"]["success"] is True
    assert report["analysis"]["success"] is True
    assert report["pattern"]["success"] is True
    assert report["knowledge"]["success"] is True
    assert report["metrics"]["videos_collected"] == 3
    assert report["metrics"]["transcripts_downloaded"] == 3
    assert report["metrics"]["analyses_completed"] == 2
    assert report["metrics"]["patterns_extracted"] == 6
    assert report["metrics"]["knowledge_entries_created"] == 6
    assert report["metrics"]["titles_generated"] == 0


def test_failed_workflow_stops_on_unrecoverable_error() -> None:
    collector = CollectorStub()
    transcript = TranscriptStub(should_fail=True)
    analysis = AnalysisStub()
    pattern = PatternStub()
    knowledge = KnowledgeStub()
    context = WorkflowContext({"keyword": "ai"})
    manager = _build_manager(collector, transcript, analysis, pattern, knowledge)

    result = manager.run(context)
    report = result.data["report"]

    assert result.success is False
    assert report["collector"]["success"] is True
    assert report["transcript"]["success"] is False
    assert report["analysis"]["success"] is False
    assert analysis.called is False
    assert pattern.called is False
    assert knowledge.called is False


def test_partial_failure_continues_when_recoverable() -> None:
    collector = CollectorStub()
    transcript = TranscriptStub()
    analysis = AnalysisStub(should_fail=True)
    pattern = PatternStub()
    knowledge = KnowledgeStub()
    context = WorkflowContext({"keyword": "ai", "continue_on_error": True})
    manager = _build_manager(collector, transcript, analysis, pattern, knowledge)

    result = manager.run(context)
    report = result.data["report"]

    assert result.success is False
    assert report["analysis"]["success"] is False
    assert report["pattern"]["success"] is True
    assert report["knowledge"]["success"] is True
    assert pattern.called is True
    assert knowledge.called is True


def test_context_propagation_between_pattern_and_knowledge() -> None:
    pattern = PatternStub()
    knowledge = KnowledgeStub()
    context = WorkflowContext({"keyword": "ai", "limit": 5})
    manager = _build_manager(CollectorStub(), TranscriptStub(), AnalysisStub(), pattern, knowledge)

    result = manager.run(context)

    assert result.success is True
    assert len(pattern.context_ids) == 1
    assert len(knowledge.context_ids) == 1
    assert pattern.context_ids[0] == knowledge.context_ids[0]
    assert knowledge.received_pattern_report is True


def test_optional_title_stage_runs_when_enabled() -> None:
    title = TitleStub()
    context = WorkflowContext({"keyword": "ai", "run_title_generation": True, "title_topic": "AI growth"})
    manager = _build_manager(CollectorStub(), TranscriptStub(), AnalysisStub(), PatternStub(), KnowledgeStub(), title)

    result = manager.run(context)
    report = result.data["report"]

    assert result.success is True
    assert title.called is True
    assert report["title"]["success"] is True
    assert report["metrics"]["titles_generated"] == 20
