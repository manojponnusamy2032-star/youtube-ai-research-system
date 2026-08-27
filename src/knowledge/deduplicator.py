"""Conservative deduplication for knowledge notes."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from src.knowledge.models import KnowledgeNote, normalize_title, slugify
from src.knowledge.repository import KnowledgeRepository


class Deduplicator:
    """Find existing notes that match a candidate without risky false merges."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        """Initialize with repository for lookup."""
        self.repository = repository

    def find_match(self, candidate: KnowledgeNote) -> KnowledgeNote | None:
        """Find an existing note that confidently matches the candidate.

        Matching order (conservative - stops at first hit):
        1. Exact note ID
        2. Normalized title exact match
        3. Slug exact match
        4. Alias exact match
        5. High-confidence normalized title similarity (ratio >= 0.95)
        6. High-confidence slug similarity (ratio >= 0.95)

        Returns:
            The existing KnowledgeNote if a confident match is found, None otherwise.
        """
        # 1. Exact ID
        if candidate.id:
            existing = self.repository.read_note(candidate.id)
            if existing:
                return existing

        # 2. Normalized title exact match
        cand_norm = normalize_title(candidate.title)
        for note in self.repository.list_notes():
            if note.id == candidate.id:
                continue
            if normalize_title(note.title) == cand_norm:
                return note

        # 3. Slug exact match
        cand_slug = slugify(candidate.title)
        for note in self.repository.list_notes():
            if note.id == candidate.id:
                continue
            if note.slug == cand_slug:
                return note

        # 4. Alias exact match
        for note in self.repository.list_notes():
            if note.id == candidate.id:
                continue
            if candidate.title in note.aliases or cand_norm in [normalize_title(a) for a in note.aliases]:
                return note

        # 5. High-confidence normalized title similarity
        for note in self.repository.list_notes():
            if note.id == candidate.id:
                continue
            ratio = SequenceMatcher(None, cand_norm, normalize_title(note.title)).ratio()
            if ratio >= 0.95:
                return note

        # 6. High-confidence slug similarity
        for note in self.repository.list_notes():
            if note.id == candidate.id:
                continue
            ratio = SequenceMatcher(None, cand_slug, note.slug).ratio()
            if ratio >= 0.95:
                return note

        return None

    def find_duplicate_candidates(self) -> list[list[str]]:
        """Find groups of notes that may be duplicates.

        Uses conservative matching - only groups with very high similarity are returned.

        Returns:
            List of title groups where each group may represent duplicates.
        """
        notes = self.repository.list_notes()
        grouped: dict[str, list[str]] = {}

        for note in notes:
            norm = normalize_title(note.title)
            placed = False
            for existing_norm, titles in grouped.items():
                ratio = SequenceMatcher(None, norm, existing_norm).ratio()
                if ratio >= 0.95:
                    titles.append(note.title)
                    placed = True
                    break
            if not placed:
                grouped[norm] = [note.title]

        return [titles for titles in grouped.values() if len(titles) > 1]