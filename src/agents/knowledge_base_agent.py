"""Agent that converts extracted patterns into reusable knowledge entries."""

from __future__ import annotations

from typing import Any

from src.core.agent_result import AgentResult
from src.core.base_agent import BaseAgent
from src.core.context import WorkflowContext
from src.database.database_service import DatabaseService
from src.knowledge.knowledge_service import KnowledgeService as ObsidianKnowledgeService
from src.knowledge.models import NoteType
from src.models.knowledge import KnowledgeEntry
from src.services.knowledge_service import KnowledgeService


class KnowledgeBaseAgent(BaseAgent):
    """Persist pattern report signals into queryable strategy knowledge."""

    CATEGORY_KEY_MAP = {
        "Hook": "hooks",
        "Story": "stories",
        "Emotion": "emotions",
        "Title": "titles",
        "Thumbnail": "thumbnail_psychology",
        "Retention": "retention",
    }

    def __init__(
        self,
        database_service: DatabaseService,
        knowledge_service: KnowledgeService,
        obsidian_knowledge_service: ObsidianKnowledgeService | None = None,
    ) -> None:
        super().__init__("KnowledgeBaseAgent")
        self.database_service = database_service
        self.knowledge_service = knowledge_service
        self.obsidian_knowledge_service = obsidian_knowledge_service

    def run(self, context: WorkflowContext) -> AgentResult:
        """Read pattern report from context, build entries, and persist them."""
        self.start()
        report = context.get("pattern_report")
        if not isinstance(report, dict):
            return AgentResult.fail("pattern_report is missing in workflow context")
        entries = self._build_entries(report)
        saved_count = self.knowledge_service.save_many(entries)
        context.set("knowledge_entries", [entry.to_dict() for entry in entries])
        context.set("knowledge_entries_saved", saved_count)
        # Write structured knowledge to Obsidian vault if available
        obsidian_notes = 0
        if self.obsidian_knowledge_service is not None:
            obsidian_notes = self._write_obsidian_notes(report)
            context.set("obsidian_notes_written", obsidian_notes)
        self.finish()
        return AgentResult.ok(
            saved_entries=saved_count,
            obsidian_notes_written=obsidian_notes,
        )

    def _build_entries(self, report: dict[str, Any]) -> list[KnowledgeEntry]:
        """Build knowledge entries from supported report categories."""
        confidence = self._report_confidence(report)
        entries: list[KnowledgeEntry] = []
        for category, key in self.CATEGORY_KEY_MAP.items():
            for entry in self._extract_category_entries(report, key):
                recommendation = self._recommendation(category, entry["pattern"])
                entries.append(KnowledgeEntry(
                    category=category,
                    pattern=entry["pattern"],
                    frequency=entry["frequency"],
                    average_views=entry["average_views"],
                    confidence=round(confidence * (entry["frequency"] / 100), 2),
                    recommendation=recommendation,
                ))
        return entries

    def _extract_category_entries(self, report: dict[str, Any], key: str) -> list[dict[str, float | str]]:
        """Extract normalized pattern entries from dict or list report formats."""
        raw = report.get(key, {})
        if isinstance(raw, dict):
            return [{"pattern": name, "frequency": float(freq), "average_views": 0.0} for name, freq in raw.items()]
        if isinstance(raw, list):
            return [
                {
                    "pattern": str(item.get("pattern", "")),
                    "frequency": float(item.get("percentage", 0.0)),
                    "average_views": float(item.get("average_views", 0.0)),
                }
                for item in raw
                if item.get("pattern")
            ]
        return []

    def _report_confidence(self, report: dict[str, Any]) -> float:
        """Normalize report confidence to percentage scale."""
        raw = report.get("confidence", report.get("average_confidence", 0.0))
        value = float(raw) if isinstance(raw, (int, float)) else 0.0
        return value * 100 if value <= 1 else value

    def _recommendation(self, category: str, pattern: str) -> str:
        """Generate concise recommendation text for knowledge entry."""
        return f"Prefer {pattern.lower()} strategies for strong {category.lower()} outcomes."

    def _write_obsidian_notes(self, report: dict[str, Any]) -> int:
        """Write structured knowledge notes to the Obsidian vault.

        Only persists useful, structured knowledge - not raw AI responses.
        """
        written = 0
        for category, key in self.CATEGORY_KEY_MAP.items():
            raw = report.get(key, {})
            items = []
            if isinstance(raw, dict):
                items = [{"pattern": name, "frequency": float(freq)} for name, freq in raw.items()]
            elif isinstance(raw, list):
                items = [
                    {
                        "pattern": str(item.get("pattern", "")),
                        "frequency": float(item.get("percentage", 0.0)),
                    }
                    for item in raw
                    if item.get("pattern")
                ]
            for item in items:
                pattern = item["pattern"]
                frequency = item["frequency"]
                title = f"{category}: {pattern}"
                content = (
                    f"## Pattern\n\n{pattern}\n\n"
                    f"## Category\n\n{category}\n\n"
                    f"## Frequency\n\n{frequency:.1f}%\n\n"
                    f"## Recommendation\n\n{self._recommendation(category, pattern)}"
                )
                self.obsidian_knowledge_service.create_note(
                    title=title,
                    note_type=NoteType.INSIGHT,
                    content=content,
                    tags=["viral-pattern", category.lower()],
                    confidence=round(self._report_confidence(report) * (frequency / 100), 2),
                    source="pattern-report",
                )
                written += 1
        return written