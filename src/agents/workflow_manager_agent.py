"""Workflow manager agent for orchestrating the complete research pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.models.workflow_report import StageReport, WorkflowMetrics, WorkflowReport


class WorkflowManagerAgent(BaseAgent):
    """Execute all research agents sequentially with shared context."""

    def __init__(
        self,
        collector_agent: Any,
        transcript_agent: Any,
        analysis_agent: Any,
        pattern_extractor_agent: Any,
        knowledge_base_agent: Any,
        title_generator_agent: Any | None = None,
        content_generation_manager: Any | None = None,
    ) -> None:
        super().__init__("WorkflowManagerAgent")
        self.collector_agent = collector_agent
        self.transcript_agent = transcript_agent
        self.analysis_agent = analysis_agent
        self.pattern_extractor_agent = pattern_extractor_agent
        self.knowledge_base_agent = knowledge_base_agent
        self.title_generator_agent = title_generator_agent
        self.content_generation_manager = content_generation_manager

    def run(self, context: WorkflowContext) -> AgentResult:
        """Run full workflow and return summary with stage timings and metrics."""
        self.start()
        started_at = datetime.now(timezone.utc)
        continue_on_error = bool(context.get("continue_on_error", False))
        metrics = WorkflowMetrics()
        stages = self._build_stage_calls(context, metrics)
        stage_reports, has_failures = self._execute_stages(stages, continue_on_error, context)
        finished_at = datetime.now(timezone.utc)
        report = WorkflowReport(
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=round((finished_at - started_at).total_seconds(), 3),
            collector=stage_reports["collector"],
            transcript=stage_reports["transcript"],
            analysis=stage_reports["analysis"],
            pattern=stage_reports["pattern"],
            knowledge=stage_reports["knowledge"],
            title=stage_reports.get("title", StageReport()),
            content_generation=stage_reports.get("content_generation", StageReport()),
            metrics=metrics,
        )
        self.finish()
        if has_failures:
            return AgentResult(success=False, message="Workflow completed with failures", data={"report": report.to_dict()})
        return AgentResult.ok(report=report.to_dict())

    def _build_stage_calls(
        self, context: WorkflowContext, metrics: WorkflowMetrics
    ) -> list[tuple[str, Callable[[], Any], Callable[[Any, WorkflowContext], None]]]:
        """Create stage execution plan and metric updaters."""
        return [
            ("collector", lambda: self.collector_agent.run(context.get("keyword", ""), context.get("max_results", 50)), self._apply_collector_metrics(metrics)),
            ("transcript", lambda: self.transcript_agent.run(context.get("limit", 50)), self._apply_transcript_metrics(metrics)),
            ("analysis", lambda: self.analysis_agent.run(context.get("limit", 50), context.get("force_reanalyze", False)), self._apply_analysis_metrics(metrics)),
            ("pattern", lambda: self.pattern_extractor_agent.run(context), self._apply_pattern_metrics(metrics)),
            ("knowledge", lambda: self.knowledge_base_agent.run(context), self._apply_knowledge_metrics(metrics)),
        ] + self._optional_title_stage(context, metrics) + self._optional_content_stage(context, metrics)

    def _optional_title_stage(
        self,
        context: WorkflowContext,
        metrics: WorkflowMetrics,
    ) -> list[tuple[str, Callable[[], Any], Callable[[Any, WorkflowContext], None]]]:
        """Return optional title stage if enabled and configured."""
        should_run = bool(context.get("run_title_generation", False) or context.get("run_content_generation", False))
        if not should_run or self.title_generator_agent is None:
            return []
        return [("title", lambda: self.title_generator_agent.run(context), self._apply_title_metrics(metrics))]

    def _optional_content_stage(
        self,
        context: WorkflowContext,
        metrics: WorkflowMetrics,
    ) -> list[tuple[str, Callable[[], Any], Callable[[Any, WorkflowContext], None]]]:
        """Return optional content generation stage when enabled."""
        should_run = bool(context.get("run_content_generation", False))
        if not should_run or self.content_generation_manager is None:
            return []
        return [("content_generation", lambda: self.content_generation_manager.run(context), self._apply_content_metrics(metrics))]

    def _execute_stages(
        self,
        stages: list[tuple[str, Callable[[], Any], Callable[[Any, WorkflowContext], None]]],
        continue_on_error: bool,
        context: WorkflowContext,
    ) -> tuple[dict[str, StageReport], bool]:
        """Execute each stage and apply stop/continue behavior on failures."""
        reports = {name: StageReport() for name, _, _ in stages}
        has_failures = False
        for name, call, update_metrics in stages:
            stage_start = perf_counter()
            try:
                result = call()
                reports[name] = StageReport(success=self._result_success(result), duration=round(perf_counter() - stage_start, 3))
                update_metrics(result, context)
                context.set(f"{name}_result", result)
            except Exception as error:
                has_failures = True
                reports[name] = StageReport(success=False, duration=round(perf_counter() - stage_start, 3))
                context.set(f"{name}_error", str(error))
                if not continue_on_error:
                    break
            if not reports[name].success:
                has_failures = True
                if not continue_on_error:
                    break
        return reports, has_failures

    def _result_success(self, result: Any) -> bool:
        """Determine stage success across tuple and AgentResult return types."""
        if isinstance(result, AgentResult):
            return bool(result.success)
        return True

    def _apply_collector_metrics(self, metrics: WorkflowMetrics) -> Callable[[Any, WorkflowContext], None]:
        """Build collector metric updater."""
        def updater(result: Any, _context: WorkflowContext) -> None:
            if isinstance(result, tuple) and len(result) >= 1:
                metrics.videos_collected = int(result[0])
            elif isinstance(result, AgentResult):
                metrics.videos_collected = int(result.data.get("videos_collected", 0))
        return updater

    def _apply_transcript_metrics(self, metrics: WorkflowMetrics) -> Callable[[Any, WorkflowContext], None]:
        """Build transcript metric updater."""
        def updater(result: Any, _context: WorkflowContext) -> None:
            if isinstance(result, tuple) and len(result) >= 3:
                metrics.transcripts_downloaded = int(result[0]) + int(result[1]) + int(result[2])
            elif isinstance(result, AgentResult):
                metrics.transcripts_downloaded = int(result.data.get("transcripts_downloaded", 0))
        return updater

    def _apply_analysis_metrics(self, metrics: WorkflowMetrics) -> Callable[[Any, WorkflowContext], None]:
        """Build analysis metric updater."""
        def updater(result: Any, _context: WorkflowContext) -> None:
            if isinstance(result, tuple) and len(result) >= 1:
                metrics.analyses_completed = int(result[0])
            elif isinstance(result, AgentResult):
                metrics.analyses_completed = int(result.data.get("analyses_completed", 0))
        return updater

    def _apply_pattern_metrics(self, metrics: WorkflowMetrics) -> Callable[[Any, WorkflowContext], None]:
        """Build pattern metric updater."""
        def updater(result: Any, context: WorkflowContext) -> None:
            report = result.data.get("report") if isinstance(result, AgentResult) else context.get("pattern_report", {})
            metrics.patterns_extracted = self._count_patterns(report if isinstance(report, dict) else {})
        return updater

    def _apply_knowledge_metrics(self, metrics: WorkflowMetrics) -> Callable[[Any, WorkflowContext], None]:
        """Build knowledge metric updater."""
        def updater(result: Any, context: WorkflowContext) -> None:
            if isinstance(result, AgentResult):
                metrics.knowledge_entries_created = int(result.data.get("saved_entries", 0))
            elif context.has("knowledge_entries_saved"):
                metrics.knowledge_entries_created = int(context.get("knowledge_entries_saved", 0))
        return updater

    def _apply_title_metrics(self, metrics: WorkflowMetrics) -> Callable[[Any, WorkflowContext], None]:
        """Build title metric updater."""
        def updater(result: Any, context: WorkflowContext) -> None:
            if isinstance(result, AgentResult):
                metrics.titles_generated = int(result.data.get("count", 0))
            elif context.has("generated_titles_count"):
                metrics.titles_generated = int(context.get("generated_titles_count", 0))
        return updater

    def _apply_content_metrics(self, metrics: WorkflowMetrics) -> Callable[[Any, WorkflowContext], None]:
        """Build content package metric updater."""
        def updater(result: Any, context: WorkflowContext) -> None:
            if isinstance(result, AgentResult):
                metrics.content_packages_generated = int(result.data.get("count", 0))
            elif context.has("content_package_count"):
                metrics.content_packages_generated = int(context.get("content_package_count", 0))
        return updater

    def _count_patterns(self, report: dict[str, Any]) -> int:
        """Count total unique extracted patterns across report categories."""
        keys = ("hooks", "stories", "emotions", "titles", "thumbnail_psychology", "retention")
        total = 0
        for key in keys:
            value = report.get(key, {})
            if isinstance(value, dict):
                total += len(value)
            elif isinstance(value, list):
                total += len([item for item in value if isinstance(item, dict) and item.get("pattern")])
        return total
