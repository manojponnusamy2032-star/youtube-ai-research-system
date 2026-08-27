"""Vault indexer for discovering notes, tags, links, and orphans."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.knowledge.linker import Linker
from src.knowledge.models import KnowledgeNote, RelationshipType, VaultIndex
from src.knowledge.repository import KnowledgeRepository


class Indexer:
    """Build a VaultIndex from all notes in the vault."""

    def __init__(self, repository: KnowledgeRepository, linker: Linker | None = None) -> None:
        """Initialize indexer with repository and optional linker."""
        self.repository = repository
        self.linker = linker or Linker()

    def index(self) -> VaultIndex:
        """Build a complete index of the vault.

        Returns:
            VaultIndex with notes, types, tags, wikilinks, backlinks, orphans, and graph.
        """
        notes = self.repository.list_notes()
        note_dicts = [note.to_dict() for note in notes]
        note_types: Counter[str] = Counter()
        tags: Counter[str] = Counter()
        wikilinks: dict[str, list[str]] = {}
        backlinks: dict[str, list[str]] = {}
        graph: dict[str, list[dict[str, Any]]] = {}
        all_titles = {note.title for note in notes}

        for note in notes:
            note_types[note.type.value] += 1
            for tag in note.tags:
                tags[tag] += 1
            links = self.linker.extract_wikilinks(note)
            wikilinks[note.title] = links
            for target in links:
                backlinks.setdefault(target, []).append(note.title)

            # Build relationship graph from typed relationships
            relationships = self.linker.extract_relationships(note)
            if relationships:
                graph[note.id] = [
                    {
                        "target": rel.target,
                        "type": rel.type.value if isinstance(rel.type, RelationshipType) else str(rel.type),
                        "confidence": rel.confidence,
                        "evidence": rel.evidence,
                    }
                    for rel in relationships
                ]

        # Find orphan notes (no incoming or outgoing links)
        linked_titles = set()
        for links in wikilinks.values():
            linked_titles.update(links)
        orphan_notes = [
            title
            for title in all_titles
            if title not in linked_titles and not wikilinks.get(title)
        ]

        return VaultIndex(
            notes=note_dicts,
            note_types=dict(note_types),
            tags=dict(tags),
            wikilinks=wikilinks,
            backlinks=backlinks,
            orphan_notes=sorted(orphan_notes),
            graph=graph,
        )
