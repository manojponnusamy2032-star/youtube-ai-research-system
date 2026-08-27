"""Repository for reading and writing knowledge notes to the vault."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.knowledge.config import KnowledgeConfig
from src.knowledge.models import KnowledgeNote, NoteMetadata, NoteType, slugify


class KnowledgeRepository:
    """Filesystem repository for knowledge notes in the Obsidian vault."""

    def __init__(self, config: KnowledgeConfig) -> None:
        """Initialize repository with vault configuration."""
        self.config = config
        self.config.ensure_vault()

    def save_note(self, note: KnowledgeNote) -> Path:
        """Write a note to the vault, creating parent directories.

        Args:
            note: The knowledge note to save.

        Returns:
            The absolute path where the note was written.
        """
        folder = self.config.folder_for(note.folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / note.filename
        path.write_text(note.to_markdown(), encoding="utf-8")
        return path

    def read_note(self, note_id: str) -> KnowledgeNote | None:
        """Read a note by its ID.

        Args:
            note_id: The note ID to look up.

        Returns:
            The KnowledgeNote if found, None otherwise.
        """
        for path in self._iter_markdown_files():
            note = self._parse_file(path)
            if note and note.id == note_id:
                return note
        return None

    def find_by_slug(self, slug: str) -> KnowledgeNote | None:
        """Find a note by its filename slug.

        Args:
            slug: The slug (filename without .md) to look up.

        Returns:
            The KnowledgeNote if found, None otherwise.
        """
        for path in self._iter_markdown_files():
            if path.stem == slug:
                return self._parse_file(path)
        return None

    def find_by_title(self, title: str) -> KnowledgeNote | None:
        """Find a note by its title.

        Args:
            title: The note title to look up.

        Returns:
            The KnowledgeNote if found, None otherwise.
        """
        target_slug = slugify(title)
        for path in self._iter_markdown_files():
            note = self._parse_file(path)
            if note and note.slug == target_slug:
                return note
        # Also check aliases
        for path in self._iter_markdown_files():
            note = self._parse_file(path)
            if note and title in note.aliases:
                return note
        return None

    def delete_note(self, note_id: str) -> bool:
        """Delete a note by its ID.

        Args:
            note_id: The note ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        for path in self._iter_markdown_files():
            note = self._parse_file(path)
            if note and note.id == note_id:
                path.unlink()
                return True
        return False

    def list_notes(self) -> list[KnowledgeNote]:
        """List all notes in the vault.

        Returns:
            List of all KnowledgeNote objects in the vault.
        """
        notes = []
        for path in self._iter_markdown_files():
            note = self._parse_file(path)
            if note:
                notes.append(note)
        return notes

    def _iter_markdown_files(self) -> list[Path]:
        """Iterate over all .md files in the vault."""
        if not self.config.vault_path.exists():
            return []
        return sorted(self.config.vault_path.rglob("*.md"))

    def _parse_file(self, path: Path) -> KnowledgeNote | None:
        """Parse a markdown file into a KnowledgeNote."""
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        metadata = NoteMetadata.from_frontmatter(text)
        if not metadata:
            return None
        # Extract content after frontmatter
        end = text.find("\n---", 3)
        if end == -1:
            content = text
        else:
            content = text[end + 4 :].strip()
        # Remove leading H1 title if present
        content = re.sub(rf"^#\s+{re.escape(metadata.title)}\s*\n?", "", content, count=1)
        return KnowledgeNote(
            id=metadata.id,
            type=metadata.type,
            title=metadata.title,
            content=content.strip(),
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
