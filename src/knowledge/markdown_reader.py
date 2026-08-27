"""Markdown reader for knowledge notes."""

from __future__ import annotations

from pathlib import Path

from src.knowledge.models import KnowledgeNote, NoteMetadata


class MarkdownReader:
    """Parse Markdown files into KnowledgeNote objects."""

    def read(self, path: Path) -> KnowledgeNote | None:
        """Read and parse a markdown file into a KnowledgeNote.

        Args:
            path: Path to the markdown file.

        Returns:
            KnowledgeNote if the file has valid frontmatter, None otherwise.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        metadata = NoteMetadata.from_frontmatter(text)
        if not metadata:
            return None
        end = text.find("\n---", 3)
        content = text[end + 4 :].strip() if end != -1 else text
        return KnowledgeNote(
            id=metadata.id,
            type=metadata.type,
            title=metadata.title,
            content=content,
            tags=metadata.tags,
            source=metadata.source,
            status=metadata.status,
            confidence=metadata.confidence,
            project=metadata.project,
            related=metadata.related,
            aliases=metadata.aliases,
            source_type=metadata.source_type,
            source_id=metadata.source_id,
            source_video_ids=metadata.source_video_ids,
            generated_by=metadata.generated_by,
            extra=metadata.extra,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )
