"""Central service for the Knowledge Brain subsystem."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.knowledge.config import KnowledgeConfig
from src.knowledge.indexer import Indexer
from src.knowledge.linker import Linker
from src.knowledge.models import (
    KnowledgeNote,
    NoteSearchResult,
    NoteType,
    VaultIndex,
)
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.search import KnowledgeSearch


class KnowledgeService:
    """High-level operations for creating, updating, linking, and searching notes."""

    def __init__(
        self,
        config: KnowledgeConfig | None = None,
        repository: KnowledgeRepository | None = None,
    ) -> None:
        """Initialize the knowledge service.

        Args:
            config: Optional vault configuration. If None, uses default.
            repository: Optional repository. If None, creates one from config.
        """
        self.config = config or KnowledgeConfig()
        self.repository = repository or KnowledgeRepository(self.config)
        self.linker = Linker()
        self.indexer = Indexer(self.repository, self.linker)
        self.search = KnowledgeSearch(self.repository)

    # ------------------------------------------------------------------
    # Note CRUD
    # ------------------------------------------------------------------

    def create_note(
        self,
        title: str,
        note_type: NoteType | str,
        content: str,
        *,
        tags: list[str] | None = None,
        source: str = "generated",
        status: str | None = None,
        confidence: float | None = None,
        project: str | None = None,
        related: list[str] | None = None,
        aliases: list[str] | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        source_video_ids: list[str] | None = None,
        generated_by: str | None = None,
        extra: dict[str, Any] | None = None,
        note_id: str | None = None,
    ) -> KnowledgeNote:
        """Create a new knowledge note.

        If a note with the same title already exists, it is updated instead
        of creating a duplicate (idempotency).

        Args:
            title: Note title.
            note_type: Type of note (concept, project, research, etc.).
            content: Markdown content body.
            tags: Optional list of tags.
            source: Source identifier (default: "generated").
            status: Optional status (e.g., "accepted", "active").
            confidence: Optional confidence score.
            project: Optional project name.
            related: Optional list of related note titles.
            extra: Optional extra frontmatter fields.
            note_id: Optional stable ID. If None, generated.

        Returns:
            The created or updated KnowledgeNote.
        """
        target_type = note_type if isinstance(note_type, NoteType) else NoteType(note_type)
        now = datetime.now(timezone.utc).isoformat()

        # Check for existing note by title (idempotency)
        existing = self.repository.find_by_title(title)
        if existing:
            existing.content = content
            existing.type = target_type
            existing.tags = tags or existing.tags
            existing.source = source
            existing.status = status or existing.status
            existing.confidence = confidence if confidence is not None else existing.confidence
            existing.project = project or existing.project
            existing.related = related or existing.related
            if aliases:
                existing.aliases = list(set(existing.aliases) | set(aliases))
            existing.source_type = source_type or existing.source_type
            existing.source_id = source_id or existing.source_id
            if source_video_ids:
                existing.source_video_ids = list(set(existing.source_video_ids) | set(source_video_ids))
            existing.generated_by = generated_by or existing.generated_by
            existing.extra = extra or existing.extra
            existing.updated_at = now
            self.repository.save_note(existing)
            return existing

        note = KnowledgeNote(
            id=note_id or f"knowledge-{uuid.uuid4().hex[:8]}",
            type=target_type,
            title=title,
            content=content,
            tags=tags or [],
            source=source,
            status=status,
            confidence=confidence,
            project=project,
            related=related or [],
            aliases=aliases or [],
            source_type=source_type,
            source_id=source_id,
            source_video_ids=source_video_ids or [],
            generated_by=generated_by,
            extra=extra or {},
            created_at=now,
            updated_at=now,
        )
        self.repository.save_note(note)
        return note

    def update_note(self, note_id: str, **changes: Any) -> KnowledgeNote | None:
        """Update an existing note by ID.

        Args:
            note_id: The note ID to update.
            **changes: Fields to update (title, content, tags, etc.).

        Returns:
            The updated note, or None if not found.
        """
        note = self.repository.read_note(note_id)
        if not note:
            return None
        for key, value in changes.items():
            if hasattr(note, key):
                setattr(note, key, value)
        note.updated_at = datetime.now(timezone.utc).isoformat()
        self.repository.save_note(note)
        return note

    def get_note(self, note_id: str) -> KnowledgeNote | None:
        """Get a note by ID.

        Args:
            note_id: The note ID to retrieve.

        Returns:
            The KnowledgeNote, or None if not found.
        """
        return self.repository.read_note(note_id)

    def get_note_by_title(self, title: str) -> KnowledgeNote | None:
        """Get a note by its title.

        Args:
            title: The note title to look up.

        Returns:
            The KnowledgeNote, or None if not found.
        """
        return self.repository.find_by_title(title)

    def delete_note(self, note_id: str) -> bool:
        """Delete a note by ID.

        Args:
            note_id: The note ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        return self.repository.delete_note(note_id)

    def list_notes(self) -> list[KnowledgeNote]:
        """List all notes in the vault.

        Returns:
            List of all KnowledgeNote objects.
        """
        return self.repository.list_notes()

    # ------------------------------------------------------------------
    # Linking
    # ------------------------------------------------------------------

    def link_notes(self, source_title: str, target_titles: list[str]) -> KnowledgeNote | None:
        """Add wikilinks from a source note to target notes.

        Args:
            source_title: Title of the source note.
            target_titles: Titles of notes to link to.

        Returns:
            The updated source note, or None if not found.
        """
        note = self.repository.find_by_title(source_title)
        if not note:
            return None
        self.linker.add_related(note, target_titles)
        note.updated_at = datetime.now(timezone.utc).isoformat()
        self.repository.save_note(note)
        return note

    # ------------------------------------------------------------------
    # Search & Index
    # ------------------------------------------------------------------

    def search_notes(
        self,
        query: str | None = None,
        *,
        note_type: NoteType | str | None = None,
        tag: str | None = None,
        project: str | None = None,
        limit: int = 20,
    ) -> list[NoteSearchResult]:
        """Search notes with optional filters.

        Args:
            query: Free-text search across title and content.
            note_type: Filter by note type.
            tag: Filter by tag.
            project: Filter by project name.
            limit: Maximum number of results.

        Returns:
            List of NoteSearchResult objects.
        """
        return self.search.search(
            query,
            note_type=note_type,
            tag=tag,
            project=project,
            limit=limit,
        )

    def index_vault(self) -> VaultIndex:
        """Build and return a complete index of the vault.

        Returns:
            VaultIndex with notes, types, tags, links, backlinks, and orphans.
        """
        return self.indexer.index()

    def update_note_confidence(self, note_id: str, new_confidence: float) -> KnowledgeNote | None:
        """Update the confidence of a note and adjust its visibility.

        Supports knowledge evolution: if new research supports an existing insight,
        update the confidence rather than creating a duplicate.

        Args:
            note_id: The note ID to update.
            new_confidence: New confidence score (0.0 - 1.0).

        Returns:
            The updated KnowledgeNote, or None if not found.
        """
        note = self.repository.read_note(note_id)
        if not note:
            return None
        old_confidence = note.confidence
        note.confidence = new_confidence
        note.updated_at = datetime.now(timezone.utc).isoformat()
        # If confidence crosses threshold, adjust tags
        if new_confidence >= 0.90 and (old_confidence is None or old_confidence < 0.90):
            # Remove from low-confidence tracking if it was there
            note.tags = [t for t in note.tags if t != "low-confidence"]
        elif new_confidence < 0.70 and (old_confidence is None or old_confidence >= 0.70):
            if "low-confidence" not in note.tags:
                note.tags.append("low-confidence")
        self.repository.save_note(note)
        return note

    def update_note_evidence(self, note_id: str, new_evidence: str) -> KnowledgeNote | None:
        """Append new evidence to a note, supporting knowledge evolution.

        If new research supports an existing insight, update the note with
        new evidence and updated confidence rather than creating a duplicate.

        Args:
            note_id: The note ID to update.
            new_evidence: Evidence text to append.

        Returns:
            The updated KnowledgeNote, or None if not found.
        """
        note = self.repository.read_note(note_id)
        if not note:
            return None
        if new_evidence and new_evidence not in note.content:
            note.content = f"{note.content.rstrip()}\n\n{new_evidence}"
        note.updated_at = datetime.now(timezone.utc).isoformat()
        self.repository.save_note(note)
        return note

    def _evidence_marker_for_note(self, note: KnowledgeNote) -> str | None:
        """Generate a compact evidence block for a note's provenance."""
        source_id = note.source_id or "unknown"
        video_ids = note.source_video_ids or []
        lines = ["> **Evidence source:**"]
        vid_line = ",".join(video_ids[:5]) if video_ids else "unknown"
        lines.append(f"> - Batch: `{source_id}` | Videos: `{vid_line}`")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Specialized capture methods
    # ------------------------------------------------------------------

    def capture_insight(
        self,
        title: str,
        content: str,
        *,
        tags: list[str] | None = None,
        confidence: float | None = None,
        project: str | None = None,
        related: list[str] | None = None,
    ) -> KnowledgeNote:
        """Capture a reusable insight as a knowledge note.

        Args:
            title: Insight title.
            content: Insight content.
            tags: Optional tags.
            confidence: Optional confidence score.
            project: Optional project name.
            related: Optional related note titles.

        Returns:
            The created insight note.
        """
        return self.create_note(
            title=title,
            note_type=NoteType.INSIGHT,
            content=content,
            tags=tags or ["insight"],
            confidence=confidence,
            project=project,
            related=related,
        )

    def capture_decision(
        self,
        title: str,
        context: str,
        decision: str,
        reason: str,
        *,
        alternatives: list[str] | None = None,
        consequences: list[str] | None = None,
        status: str = "accepted",
        tags: list[str] | None = None,
        project: str | None = None,
        related: list[str] | None = None,
    ) -> KnowledgeNote:
        """Capture an architecture/technical decision.

        Args:
            title: Decision title.
            context: Background context.
            decision: The decision made.
            reason: Why this decision was made.
            alternatives: Alternatives considered.
            consequences: Expected consequences.
            status: Decision status (default: "accepted").
            tags: Optional tags.
            project: Optional project name.
            related: Optional related note titles.

        Returns:
            The created decision note.
        """
        content_parts = [
            "## Context",
            "",
            context,
            "",
            "## Decision",
            "",
            decision,
            "",
            "## Reason",
            "",
            reason,
        ]
        if alternatives:
            content_parts.extend(["", "## Alternatives Considered", ""])
            for alt in alternatives:
                content_parts.append(f"- {alt}")
        if consequences:
            content_parts.extend(["", "## Consequences", ""])
            for consequence in consequences:
                content_parts.append(f"- {consequence}")
        return self.create_note(
            title=title,
            note_type=NoteType.DECISION,
            content="\n".join(content_parts),
            tags=tags or ["decision"],
            status=status,
            project=project,
            related=related,
        )

    def capture_lesson(
        self,
        title: str,
        problem: str,
        root_cause: str,
        solution: str,
        *,
        prevention: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        related: list[str] | None = None,
    ) -> KnowledgeNote:
        """Capture a lesson learned.

        Args:
            title: Lesson title.
            problem: The problem encountered.
            root_cause: Root cause of the problem.
            solution: How it was solved.
            prevention: How to prevent it in the future.
            tags: Optional tags.
            project: Optional project name.
            related: Optional related note titles.

        Returns:
            The created lesson note.
        """
        content_parts = [
            "## Problem",
            "",
            problem,
            "",
            "## Root Cause",
            "",
            root_cause,
            "",
            "## Solution",
            "",
            solution,
        ]
        if prevention:
            content_parts.extend(["", "## Prevention", "", prevention])
        return self.create_note(
            title=title,
            note_type=NoteType.LESSON,
            content="\n".join(content_parts),
            tags=tags or ["lesson"],
            project=project,
            related=related,
        )

    def capture_research(
        self,
        title: str,
        topic: str,
        findings: str,
        *,
        source: str = "generated",
        confidence: float | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        related: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> KnowledgeNote:
        """Capture research findings as a knowledge note.

        Args:
            title: Research note title.
            topic: The research topic.
            findings: Research findings content.
            source: Source identifier.
            confidence: Optional confidence score.
            tags: Optional tags.
            project: Optional project name.
            related: Optional related note titles.
            extra: Optional extra frontmatter fields.

        Returns:
            The created research note.
        """
        content_parts = [
            f"## Topic",
            "",
            topic,
            "",
            "## Findings",
            "",
            findings,
        ]
        return self.create_note(
            title=title,
            note_type=NoteType.RESEARCH,
            content="\n".join(content_parts),
            tags=tags or ["research"],
            source=source,
            confidence=confidence,
            project=project,
            related=related,
            extra=extra,
        )

    def capture_project(
        self,
        title: str,
        purpose: str,
        *,
        status: str = "active",
        architecture: str | None = None,
        decisions: list[str] | None = None,
        related_concepts: list[str] | None = None,
        related_research: list[str] | None = None,
        known_problems: list[str] | None = None,
        lessons: list[str] | None = None,
        next_steps: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeNote:
        """Capture a project overview note.

        Args:
            title: Project title.
            purpose: Project purpose.
            status: Project status (default: "active").
            architecture: Architecture description.
            decisions: List of decision titles.
            related_concepts: Related concept titles.
            related_research: Related research titles.
            known_problems: Known problems.
            lessons: Lesson titles.
            next_steps: Next steps.
            tags: Optional tags.

        Returns:
            The created project note.
        """
        content_parts = [
            "## Purpose",
            "",
            purpose,
            "",
            "## Current Status",
            "",
            status,
        ]
        if architecture:
            content_parts.extend(["", "## Architecture", "", architecture])
        if decisions:
            content_parts.extend(["", "## Important Decisions", ""])
            for decision in decisions:
                content_parts.append(f"- [[{decision}]]")
        if related_concepts:
            content_parts.extend(["", "## Related Concepts", ""])
            for concept in related_concepts:
                content_parts.append(f"- [[{concept}]]")
        if related_research:
            content_parts.extend(["", "## Related Research", ""])
            for research in related_research:
                content_parts.append(f"- [[{research}]]")
        if known_problems:
            content_parts.extend(["", "## Known Problems", ""])
            for problem in known_problems:
                content_parts.append(f"- {problem}")
        if lessons:
            content_parts.extend(["", "## Lessons Learned", ""])
            for lesson in lessons:
                content_parts.append(f"- [[{lesson}]]")
        if next_steps:
            content_parts.extend(["", "## Next Steps", ""])
            for step in next_steps:
                content_parts.append(f"- {step}")
        related = list(set((decisions or []) + (related_concepts or []) + (related_research or []) + (lessons or [])))
        return self.create_note(
            title=title,
            note_type=NoteType.PROJECT,
            content="\n".join(content_parts),
            tags=tags or ["project"],
            status=status,
            related=related,
        )

    def health_check(self) -> dict[str, Any]:
        """Run a comprehensive health check on the knowledge vault.

        Identifies orphan notes, missing provenance, malformed frontmatter,
        broken wikilinks, duplicate candidates, low-confidence notes,
        notes without relationships, stale index, and conflicting knowledge.

        Returns:
            Dict with structured health check results.
        """
        from src.knowledge.evaluation import KnowledgeEvaluator
        evaluator = KnowledgeEvaluator(self)
        return evaluator.health_check().to_dict()
