"""Data models for the Knowledge Brain subsystem."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class NoteType(str, Enum):
    """Supported knowledge note types."""

    CONCEPT = "concept"
    PROJECT = "project"
    RESEARCH = "research"
    INSIGHT = "insight"
    DECISION = "decision"
    LESSON = "lesson"
    SOURCE = "source"

    @property
    def folder(self) -> str:
        """Return the vault folder for this note type."""
        mapping = {
            NoteType.CONCEPT: "02_Knowledge",
            NoteType.PROJECT: "01_Projects",
            NoteType.RESEARCH: "03_Research",
            NoteType.INSIGHT: "04_Insights",
            NoteType.DECISION: "05_Decisions",
            NoteType.LESSON: "06_Lessons",
            NoteType.SOURCE: "07_Sources",
        }
        return mapping[self]


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

class RelationshipType(str, Enum):
    """Supported relationship types between knowledge notes."""

    RELATED_TO = "related_to"
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    PART_OF = "part_of"
    IMPLEMENTS = "implements"
    CAUSED_BY = "caused_by"
    LEARNED_FROM = "learned_from"
    USED_BY = "used_by"


@dataclass
class Relationship:
    """A typed relationship from one knowledge note to another."""

    target: str
    type: RelationshipType | str
    confidence: float | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "target": self.target,
            "type": self.type.value if isinstance(self.type, RelationshipType) else str(self.type),
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class NoteMetadata:
    """YAML frontmatter metadata for a knowledge note."""

    id: str
    type: NoteType
    title: str
    created_at: str
    updated_at: str
    tags: list[str] = field(default_factory=list)
    source: str = "generated"
    status: str | None = None
    confidence: float | None = None
    project: str | None = None
    related: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_type: str | None = None
    source_id: str | None = None
    source_video_ids: list[str] = field(default_factory=list)
    generated_by: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_frontmatter(self) -> str:
        """Serialize metadata to YAML frontmatter string."""
        lines = ["---"]
        lines.append(f"id: {self.id}")
        lines.append(f"type: {self.type.value}")
        lines.append(f"title: {self.title}")
        lines.append(f"created_at: {self.created_at}")
        lines.append(f"updated_at: {self.updated_at}")
        if self.tags:
            lines.append("tags:")
            for tag in self.tags:
                lines.append(f"  - {tag}")
        lines.append(f"source: {self.source}")
        if self.status:
            lines.append(f"status: {self.status}")
        if self.confidence is not None:
            lines.append(f"confidence: {self.confidence}")
        if self.project:
            lines.append(f"project: {self.project}")
        if self.aliases:
            lines.append("aliases:")
            for alias in self.aliases:
                lines.append(f"  - {alias}")
        if self.related:
            lines.append("related:")
            for item in self.related:
                lines.append(f"  - {item}")
        if self.source_type:
            lines.append(f"source_type: {self.source_type}")
        if self.source_id:
            lines.append(f"source_id: {self.source_id}")
        if self.source_video_ids:
            lines.append("source_video_ids:")
            for vid in self.source_video_ids:
                lines.append(f"  - {vid}")
        if self.generated_by:
            lines.append(f"generated_by: {self.generated_by}")
        for key, value in self.extra.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)

    @classmethod
    def from_frontmatter(cls, text: str) -> "NoteMetadata | None":
        """Parse YAML frontmatter from markdown text."""
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end == -1:
            return None
        raw = text[3:end].strip()
        data: dict[str, Any] = {}
        current_key: str | None = None
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("- "):
                if current_key:
                    data.setdefault(current_key, []).append(line[2:].strip())
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                current_key = key.strip()
                value = value.strip()
                if value:
                    data[current_key] = value
                else:
                    data[current_key] = []
        note_type = data.get("type", "concept")
        try:
            note_type = NoteType(note_type)
        except ValueError:
            note_type = NoteType.CONCEPT

        # Known keys that should not go into extra
        known_keys = {
            "id", "type", "title", "created_at", "updated_at", "tags", "source",
            "status", "confidence", "project", "related", "aliases",
            "source_type", "source_id", "source_video_ids", "generated_by",
        }
        extra = {
            k: v for k, v in data.items()
            if k not in known_keys and k not in ("extra",)
        }
        # If an "extra" key itself is present, merge it
        if "extra" in data and isinstance(data["extra"], dict):
            extra.update(data["extra"])

        return cls(
            id=str(data.get("id", "")),
            type=note_type,
            title=str(data.get("title", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            tags=[str(t) for t in data.get("tags", [])],
            source=str(data.get("source", "generated")),
            status=str(data["status"]) if data.get("status") else None,
            confidence=float(data["confidence"]) if data.get("confidence") else None,
            project=str(data["project"]) if data.get("project") else None,
            related=[str(r) for r in data.get("related", [])],
            aliases=[str(a) for a in data.get("aliases", [])],
            source_type=str(data["source_type"]) if data.get("source_type") else None,
            source_id=str(data["source_id"]) if data.get("source_id") else None,
            source_video_ids=[str(v) for v in data.get("source_video_ids", [])],
            generated_by=str(data["generated_by"]) if data.get("generated_by") else None,
            extra=extra,
        )


@dataclass
class KnowledgeNote:
    """A single knowledge note stored as Markdown in the vault."""

    id: str
    type: NoteType
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    source: str = "generated"
    status: str | None = None
    confidence: float | None = None
    project: str | None = None
    related: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_type: str | None = None
    source_id: str | None = None
    source_video_ids: list[str] = field(default_factory=list)
    generated_by: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def slug(self) -> str:
        """Return a filesystem-safe slug for this note."""
        return slugify(self.title)

    @property
    def filename(self) -> str:
        """Return the markdown filename for this note."""
        return f"{self.slug}.md"

    @property
    def folder(self) -> str:
        """Return the vault folder for this note."""
        return self.type.folder

    def to_markdown(self) -> str:
        """Serialize the note to full Markdown with frontmatter."""
        metadata = NoteMetadata(
            id=self.id,
            type=self.type,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            tags=self.tags,
            source=self.source,
            status=self.status,
            confidence=self.confidence,
            project=self.project,
            related=self.related,
            aliases=self.aliases,
            source_type=self.source_type,
            source_id=self.source_id,
            source_video_ids=self.source_video_ids,
            generated_by=self.generated_by,
            extra=self.extra,
        )
        parts = [metadata.to_frontmatter(), "", f"# {self.title}", "", self.content.strip()]
        if self.related:
            parts.extend(["", "## Related", ""])
            for item in self.related:
                parts.append(f"- [[{item}]]")
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "slug": self.slug,
            "filename": self.filename,
            "folder": self.folder,
            "tags": self.tags,
            "source": self.source,
            "status": self.status,
            "confidence": self.confidence,
            "project": self.project,
            "related": self.related,
            "aliases": self.aliases,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_video_ids": self.source_video_ids,
            "generated_by": self.generated_by,
            "extra": self.extra,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class NoteSearchResult:
    """A single search result from the vault."""

    note_id: str
    title: str
    type: NoteType
    path: str
    snippet: str
    score: float
    tags: list[str] = field(default_factory=list)
    project: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "note_id": self.note_id,
            "title": self.title,
            "type": self.type.value,
            "path": self.path,
            "snippet": self.snippet,
            "score": self.score,
            "tags": self.tags,
            "project": self.project,
        }


@dataclass
class GraphIndex:
    """Knowledge graph index derived from the vault."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    orphan_notes: list[str] = field(default_factory=list)
    heavily_connected: list[dict[str, Any]] = field(default_factory=list)
    notes_without_sources: list[str] = field(default_factory=list)
    low_confidence_notes: list[dict[str, Any]] = field(default_factory=list)
    duplicate_candidates: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "orphan_notes": self.orphan_notes,
            "heavily_connected": self.heavily_connected,
            "notes_without_sources": self.notes_without_sources,
            "low_confidence_notes": self.low_confidence_notes,
            "duplicate_candidates": self.duplicate_candidates,
        }


@dataclass
class VaultIndex:
    """Index of all notes in the vault."""

    notes: list[dict[str, Any]] = field(default_factory=list)
    note_types: dict[str, int] = field(default_factory=dict)
    tags: dict[str, int] = field(default_factory=dict)
    wikilinks: dict[str, list[str]] = field(default_factory=dict)
    backlinks: dict[str, list[str]] = field(default_factory=dict)
    orphan_notes: list[str] = field(default_factory=list)
    graph: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "notes": self.notes,
            "note_types": self.note_types,
            "tags": self.tags,
            "wikilinks": self.wikilinks,
            "backlinks": self.backlinks,
            "orphan_notes": self.orphan_notes,
            "graph": self.graph,
            "generated_at": self.generated_at,
        }


def slugify(text: str) -> str:
    """Convert arbitrary text into a filesystem-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def normalize_title(title: str) -> str:
    """Normalize a title for deduplication matching.

    Lowercases, collapses whitespace, removes punctuation.
    """
    normalized = re.sub(r"[^\w\s]", " ", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized