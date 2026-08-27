"""Local full-text search over the knowledge vault."""

from __future__ import annotations

import re
from typing import Any

from src.knowledge.models import KnowledgeNote, NoteSearchResult, NoteType
from src.knowledge.repository import KnowledgeRepository


class KnowledgeSearch:
    """Search knowledge notes by title, content, tags, type, and project."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        """Initialize search with repository."""
        self.repository = repository

    def search(
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
        notes = self.repository.list_notes()
        results: list[NoteSearchResult] = []

        for note in notes:
            if note_type is not None:
                target_type = note_type if isinstance(note_type, NoteType) else NoteType(note_type)
                if note.type != target_type:
                    continue
            if tag and tag not in note.tags:
                continue
            if project and note.project != project:
                continue

            score = 0.0
            snippet = ""
            if query:
                q = query.lower()
                title_lower = note.title.lower()
                content_lower = note.content.lower()
                if q in title_lower:
                    score += 10.0
                if q in content_lower:
                    score += 5.0
                    snippet = self._make_snippet(note.content, q)
                if not score:
                    continue
            else:
                score = 1.0
                snippet = note.content[:200]

            results.append(
                NoteSearchResult(
                    note_id=note.id,
                    title=note.title,
                    type=note.type,
                    path=f"{note.folder}/{note.filename}",
                    snippet=snippet,
                    score=score,
                    tags=note.tags,
                    project=note.project,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _make_snippet(self, content: str, query: str, context_chars: int = 100) -> str:
        """Create a snippet around the first query match."""
        idx = content.lower().find(query)
        if idx == -1:
            return content[:200]
        start = max(0, idx - context_chars)
        end = min(len(content), idx + len(query) + context_chars)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(content) else ""
        return f"{prefix}{content[start:end].strip()}{suffix}"