"""Wikilink and relationship management for knowledge notes."""

from __future__ import annotations

import re
from typing import Any

from src.knowledge.models import KnowledgeNote, Relationship, RelationshipType


class Linker:
    """Detect and manage Obsidian-compatible wikilinks between notes."""

    WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")

    # Section heading used for typed relationships in note content
    RELATIONSHIP_HEADING = "## Relationships"

    def extract_wikilinks(self, note: KnowledgeNote) -> list[str]:
        """Extract all wikilink targets from a note's content and related list.

        Args:
            note: The knowledge note to scan.

        Returns:
            List of wikilink target titles.
        """
        targets = set()
        for match in self.WIKILINK_PATTERN.finditer(note.content):
            targets.add(match.group(1).strip())
        targets.update(note.related)
        return sorted(targets)

    def extract_relationships(self, note: KnowledgeNote) -> list[Relationship]:
        """Extract typed relationships from note content.

        Looks for relationship sections in the note content, e.g.:

        ## Relationships

        - [[Target]] --related_to--> 
        - [[Target]] --derived_from--> Evidence text

        Returns:
            List of Relationship objects.
        """
        relationships: list[Relationship] = []
        content = note.content
        # Find relationship section
        section_match = re.search(r"## Relationships\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        if not section_match:
            return relationships

        section = section_match.group(1)
        for line in section.splitlines():
            line = line.strip()
            if not line.startswith("- ") and not line.startswith("* "):
                continue
            line = line[2:].strip()
            # Pattern: [[Target]] --type--> optional evidence
            match = re.match(r"\[\[([^\]]+)\]\](?:\s*--(\w+)-->)?(?:\s*(.*))?", line)
            if not match:
                continue
            target = match.group(1).strip()
            rel_type_str = match.group(2) or "related_to"
            evidence = match.group(3).strip() if match.group(3) else None
            try:
                rel_type = RelationshipType(rel_type_str)
            except ValueError:
                rel_type = rel_type_str
            relationships.append(Relationship(
                target=target,
                type=rel_type,
                evidence=evidence,
            ))
        return relationships

    def add_related(self, note: KnowledgeNote, related_titles: list[str]) -> KnowledgeNote:
        """Add related note titles to a note, avoiding duplicates.

        Args:
            note: The note to update.
            related_titles: Titles to add as related.

        Returns:
            The updated note.
        """
        existing = set(note.related)
        for title in related_titles:
            if title and title not in existing:
                note.related.append(title)
                existing.add(title)
        return note

    def remove_related(self, note: KnowledgeNote, related_titles: list[str]) -> KnowledgeNote:
        """Remove related note titles from a note.

        Args:
            note: The note to update.
            related_titles: Titles to remove.

        Returns:
            The updated note.
        """
        remove_set = set(related_titles)
        note.related = [t for t in note.related if t not in remove_set]
        return note

    def add_relationship_note(
        self,
        note: KnowledgeNote,
        target: str,
        rel_type: RelationshipType | str,
        evidence: str | None = None,
    ) -> KnowledgeNote:
        """Add a typed relationship section to the note content.

        Args:
            note: The note to update.
            target: Target note title.
            rel_type: Relationship type.
            evidence: Optional evidence text.

        Returns:
            The updated note.
        """
        rel_type_str = rel_type.value if isinstance(rel_type, RelationshipType) else str(rel_type)
        relationship_line = f"- [[{target}]] --{rel_type_str}-->"
        if evidence:
            relationship_line = f"{relationship_line} {evidence}"

        if self.RELATIONSHIP_HEADING not in note.content:
            note.content = f"{note.content.strip()}\n\n{self.RELATIONSHIP_HEADING}\n\n{relationship_line}\n"
        else:
            # Append inside existing relationships section
            section_match = re.search(r"(## Relationships\s*\n)(.*?)(?=\n## |\Z)", note.content, re.DOTALL)
            if section_match:
                section_start, section_body = section_match.groups()
                note.content = (
                    note.content[:section_match.start()]
                    + section_start
                    + section_body.rstrip()
                    + "\n"
                    + relationship_line
                    + "\n"
                    + note.content[section_match.end():]
                )
            else:
                note.content = f"{note.content.strip()}\n{relationship_line}\n"

        # Also add to related list for Obsidian backlink detection
        if target not in note.related:
            note.related.append(target)
        return note
