"""Markdown writer for knowledge notes."""

from __future__ import annotations

from src.knowledge.models import KnowledgeNote


class MarkdownWriter:
    """Serialize KnowledgeNote objects to Markdown text."""

    def write(self, note: KnowledgeNote) -> str:
        """Convert a KnowledgeNote to full Markdown with frontmatter."""
        return note.to_markdown()