"""Workflow report models for full pipeline orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StageReport:
    """Execution status and runtime for one workflow stage."""

    success: bool = False
    duration: float = 0.0


@dataclass
class WorkflowMetrics:
    """Aggregated counters produced by all pipeline stages."""

    videos_collected: int = 0
    transcripts_downloaded: int = 0
    analyses_completed: int = 0
    patterns_extracted: int = 0
    knowledge_entries_created: int = 0
    titles_generated: int = 0
    content_packages_generated: int = 0


@dataclass
class WorkflowReport:
    """Structured workflow execution report."""

    started_at: str
    finished_at: str
    duration_seconds: float
    collector: StageReport = field(default_factory=StageReport)
    transcript: StageReport = field(default_factory=StageReport)
    analysis: StageReport = field(default_factory=StageReport)
    pattern: StageReport = field(default_factory=StageReport)
    knowledge: StageReport = field(default_factory=StageReport)
    title: StageReport = field(default_factory=StageReport)
    content_generation: StageReport = field(default_factory=StageReport)
    metrics: WorkflowMetrics = field(default_factory=WorkflowMetrics)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dictionary for external consumers."""
        return asdict(self)
