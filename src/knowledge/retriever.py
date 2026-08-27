"""Knowledge retrieval service for the Knowledge Brain subsystem.

Provides ranked retrieval of knowledge notes with:
- Transparent scoring (title, tags, content, project, confidence, provenance)
- Graph expansion through wikilinks and typed relationships
- Context building for AI agents
- Conflict detection (contradicts relationships)
- Source traceability (every result preserves provenance)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.knowledge.indexer import Indexer
from src.knowledge.linker import Linker
from src.knowledge.models import (
    KnowledgeNote,
    NoteType,
    RelationshipType,
    VaultIndex,
    normalize_title,
    slugify,
)
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.search import KnowledgeSearch


# ---------------------------------------------------------------------------
# Scoring weights (documented, deterministic, transparent)
# ---------------------------------------------------------------------------

SCORE_EXACT_TITLE = 100.0
SCORE_TITLE_TOKEN = 40.0
SCORE_TAG_MATCH = 30.0
SCORE_CONTENT_MATCH = 20.0
SCORE_RELATED_NOTE = 15.0
SCORE_SAME_PROJECT = 15.0
SCORE_HIGH_CONFIDENCE = 10.0
SCORE_SOURCE_AVAILABLE = 10.0
SCORE_ALIAS_MATCH = 25.0
SCORE_TYPE_MATCH = 5.0

# Graph expansion limits
MAX_GRAPH_EXPANSION = 5
MAX_CONTEXT_NOTES = 10
MAX_CONTEXT_CHARS = 4000


@dataclass
class RetrievedKnowledge:
    """A single retrieved knowledge item with full provenance."""

    note_id: str
    title: str
    note_type: NoteType
    content: str
    score: float
    confidence: float | None = None
    source: str = "generated"
    project: str | None = None
    tags: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    source_video_ids: list[str] = field(default_factory=list)
    source_id: str | None = None
    source_type: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    match_reasons: list[str] = field(default_factory=list)
    expanded_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "note_id": self.note_id,
            "title": self.title,
            "note_type": self.note_type.value,
            "content": self.content,
            "score": self.score,
            "confidence": self.confidence,
            "source": self.source,
            "project": self.project,
            "tags": self.tags,
            "related": self.related,
            "source_video_ids": self.source_video_ids,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "match_reasons": self.match_reasons,
            "expanded_from": self.expanded_from,
        }


@dataclass
class KnowledgeContext:
    """A context bundle for an AI agent."""

    query: str
    relevant_knowledge: list[RetrievedKnowledge] = field(default_factory=list)
    evidence: list[RetrievedKnowledge] = field(default_factory=list)
    lessons: list[RetrievedKnowledge] = field(default_factory=list)
    decisions: list[RetrievedKnowledge] = field(default_factory=list)
    project_context: list[RetrievedKnowledge] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "query": self.query,
            "relevant_knowledge": [k.to_dict() for k in self.relevant_knowledge],
            "evidence": [k.to_dict() for k in self.evidence],
            "lessons": [k.to_dict() for k in self.lessons],
            "decisions": [k.to_dict() for k in self.decisions],
            "project_context": [k.to_dict() for k in self.project_context],
            "conflicts": self.conflicts,
            "truncated": self.truncated,
        }

    def to_markdown(self, max_chars: int | None = MAX_CONTEXT_CHARS) -> str:
        """Render the context as a compact Markdown block for agent prompts."""
        parts = ["## Knowledge Context", ""]
        if self.relevant_knowledge:
            parts.append("### Relevant Knowledge")
            for item in self.relevant_knowledge:
                parts.append(f"- [[{item.title}]] (score: {item.score:.1f}, confidence: {item.confidence if item.confidence is not None else 'N/A'})")
        if self.evidence:
            parts.append("")
            parts.append("### Evidence")
            for item in self.evidence:
                parts.append(f"- [[{item.title}]] (source: {item.source})")
        if self.lessons:
            parts.append("")
            parts.append("### Lessons")
            for item in self.lessons:
                parts.append(f"- [[{item.title}]]")
        if self.decisions:
            parts.append("")
            parts.append("### Decisions")
            for item in self.decisions:
                parts.append(f"- [[{item.title}]]")
        if self.project_context:
            parts.append("")
            parts.append("### Project Context")
            for item in self.project_context:
                parts.append(f"- [[{item.title}]]")
        if self.conflicts:
            parts.append("")
            parts.append("### Potential Conflicts")
            for conflict in self.conflicts:
                parts.append(f"- **{conflict['source_title']}** (conf: {conflict['source_confidence']})")
                parts.append(f"  contradicts **{conflict['target_title']}** (conf: {conflict['target_confidence']})")
        if self.truncated:
            parts.append("")
            parts.append("> *Context truncated to fit token limits.*")
        markdown = "\n".join(parts)
        if max_chars is None or len(markdown) <= max_chars:
            return markdown
        if max_chars <= 0:
            return ""
        marker = "\n> *Context truncated to fit token limits.*"
        if max_chars <= len(marker):
            return markdown[:max_chars]
        return markdown[: max_chars - len(marker)] + marker


class KnowledgeRetriever:
    """Retrieve relevant knowledge from the Obsidian vault.

    Uses deterministic local retrieval with transparent scoring.
    No vector database required - designed so semantic retrieval can be
    plugged in later via the same interface.
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        search: KnowledgeSearch | None = None,
        indexer: Indexer | None = None,
        linker: Linker | None = None,
    ) -> None:
        """Initialize retriever with repository and optional components."""
        self.repository = repository
        self.search = search or KnowledgeSearch(repository)
        self.linker = linker or Linker()
        self.indexer = indexer or Indexer(repository, self.linker)
        self._index_cache: VaultIndex | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str | None = None,
        *,
        note_type: NoteType | str | None = None,
        tag: str | None = None,
        project: str | None = None,
        limit: int = 10,
        expand_graph: bool = True,
        min_confidence: float | None = None,
    ) -> list[RetrievedKnowledge]:
        """Retrieve relevant knowledge notes with ranked scoring.

        Args:
            query: Free-text query.
            note_type: Filter by note type.
            tag: Filter by tag.
            project: Filter by project.
            limit: Maximum number of results.
            expand_graph: Whether to expand through relationships.
            min_confidence: Minimum confidence threshold (0.0-1.0).

        Returns:
            List of RetrievedKnowledge objects sorted by score descending.
        """
        # Score all notes directly using the retriever's token-based scoring
        # rather than relying on KnowledgeSearch's phrase matching, which
        # would miss multi-token queries.
        query_tokens = set(re.findall(r"\w+", (query or "").lower()))

        retrieved: list[RetrievedKnowledge] = []
        for note in self.repository.list_notes():
            # Apply filters
            if note_type is not None:
                target_type = note_type if isinstance(note_type, NoteType) else NoteType(note_type)
                if note.type != target_type:
                    continue
            if tag and tag not in note.tags:
                continue
            if project and note.project != project:
                continue
            if min_confidence is not None and note.confidence is not None and note.confidence < min_confidence:
                continue

            item = self._score_note(note, query, 0.0)

            # Only include items that matched something when a query is provided
            if query and not item.match_reasons:
                continue

            retrieved.append(item)

        # Sort by score descending
        retrieved.sort(key=lambda r: r.score, reverse=True)

        # Graph expansion
        if expand_graph and retrieved:
            retrieved = self._expand_graph(retrieved, limit)

        return retrieved[:limit]

    def retrieve_related(self, note_id: str, *, limit: int = 5) -> list[RetrievedKnowledge]:
        """Retrieve notes related to a given note.

        Uses wikilinks, backlinks, and typed relationships.

        Args:
            note_id: The note ID to find related notes for.
            limit: Maximum number of related notes.

        Returns:
            List of RetrievedKnowledge items.
        """
        note = self.repository.read_note(note_id)
        if not note:
            return []

        index = self._get_index()
        related_titles = set(note.related)

        # Add backlinks
        for title, backlinks in index.backlinks.items():
            if title == note.title:
                related_titles.update(backlinks)

        # Add wikilinks from content
        related_titles.update(self.linker.extract_wikilinks(note))

        # Add graph relationships
        if note.id in index.graph:
            for rel in index.graph[note.id]:
                related_titles.add(rel["target"])

        # Fetch notes
        results: list[RetrievedKnowledge] = []
        for title in related_titles:
            related_note = self.repository.find_by_title(title)
            if related_note and related_note.id != note_id:
                item = self._score_note(related_note, note.title, 0.0)
                item.match_reasons.append("related")
                results.append(item)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def retrieve_backlinks(self, note_id: str, *, limit: int = 5) -> list[RetrievedKnowledge]:
        """Retrieve notes that link to a given note.

        Args:
            note_id: The note ID to find backlinks for.
            limit: Maximum number of backlinks.

        Returns:
            List of RetrievedKnowledge items.
        """
        note = self.repository.read_note(note_id)
        if not note:
            return []

        index = self._get_index()
        backlink_titles = index.backlinks.get(note.title, [])

        results: list[RetrievedKnowledge] = []
        for title in backlink_titles:
            backlink_note = self.repository.find_by_title(title)
            if backlink_note:
                item = self._score_note(backlink_note, note.title, 0.0)
                item.match_reasons.append("backlink")
                results.append(item)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def retrieve_project(self, project: str, *, limit: int = 10) -> list[RetrievedKnowledge]:
        """Retrieve all knowledge associated with a project.

        Args:
            project: Project name.
            limit: Maximum number of results.

        Returns:
            List of RetrievedKnowledge items.
        """
        return self.retrieve(
            project=project,
            limit=limit,
            expand_graph=False,
        )

    def retrieve_by_type(self, note_type: NoteType | str, *, limit: int = 10) -> list[RetrievedKnowledge]:
        """Retrieve notes of a specific type.

        Args:
            note_type: The note type to filter by.
            limit: Maximum number of results.

        Returns:
            List of RetrievedKnowledge items.
        """
        return self.retrieve(
            note_type=note_type,
            limit=limit,
            expand_graph=False,
        )

    def retrieve_by_tags(self, tags: list[str], *, limit: int = 10) -> list[RetrievedKnowledge]:
        """Retrieve notes matching any of the given tags.

        Args:
            tags: List of tags to match.
            limit: Maximum number of results.

        Returns:
            List of RetrievedKnowledge items.
        """
        results: list[RetrievedKnowledge] = []
        for note in self.repository.list_notes():
            if any(tag in note.tags for tag in tags):
                item = self._score_note(note, "", 0.0)
                item.match_reasons.append("tag")
                results.append(item)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def build_context(
        self,
        query: str,
        *,
        project: str | None = None,
        max_notes: int = MAX_CONTEXT_NOTES,
        max_chars: int = MAX_CONTEXT_CHARS,
        include_evidence: bool = True,
        include_lessons: bool = True,
        include_decisions: bool = True,
        include_project: bool = True,
        detect_conflicts: bool = True,
    ) -> KnowledgeContext:
        """Build a context bundle for an AI agent.

        Args:
            query: The agent's task/query.
            project: Optional project to scope context.
            max_notes: Maximum number of relevant notes.
            max_chars: Maximum total context characters.
            include_evidence: Whether to include research evidence.
            include_lessons: Whether to include lessons.
            include_decisions: Whether to include decisions.
            include_project: Whether to include project context.
            detect_conflicts: Whether to detect contradictions.

        Returns:
            KnowledgeContext with categorized knowledge.
        """
        # Retrieve relevant knowledge
        relevant = self.retrieve(
            query,
            project=project,
            limit=max_notes,
            expand_graph=True,
        )

        # Categorize
        evidence: list[RetrievedKnowledge] = []
        lessons: list[RetrievedKnowledge] = []
        decisions: list[RetrievedKnowledge] = []
        project_context: list[RetrievedKnowledge] = []

        for item in relevant:
            if item.note_type == NoteType.RESEARCH and include_evidence:
                evidence.append(item)
            elif item.note_type == NoteType.LESSON and include_lessons:
                lessons.append(item)
            elif item.note_type == NoteType.DECISION and include_decisions:
                decisions.append(item)
            elif item.note_type == NoteType.PROJECT and include_project:
                project_context.append(item)

        # Detect conflicts
        conflicts: list[dict[str, Any]] = []
        if detect_conflicts:
            conflicts = self._detect_conflicts(relevant)

        # Build context
        context = KnowledgeContext(
            query=query,
            relevant_knowledge=relevant,
            evidence=evidence,
            lessons=lessons,
            decisions=decisions,
            project_context=project_context,
            conflicts=conflicts,
        )

        # Truncate by actual rendered size, not just item count.
        # Keep trimming the largest buckets until the final markdown fits the budget.
        while len(context.to_markdown(max_chars=None)) > max_chars:
            context.truncated = True

            buckets: list[tuple[str, list[RetrievedKnowledge], int]] = [
                ("relevant_knowledge", context.relevant_knowledge, max(1, max_notes // 2)),
                ("evidence", context.evidence, max(1, len(context.evidence) // 2)),
                ("lessons", context.lessons, max(1, len(context.lessons) // 2)),
                ("decisions", context.decisions, max(1, len(context.decisions) // 2)),
                ("project_context", context.project_context, max(1, len(context.project_context) // 2)),
            ]

            trimmed_any = False
            for attr_name, items, target_size in buckets:
                if len(items) > target_size:
                    setattr(context, attr_name, items[:target_size])
                    trimmed_any = True

            if not trimmed_any:
                break

        return context

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_note(self, note: KnowledgeNote, query: str | None, base_score: float) -> RetrievedKnowledge:
        """Score a note against a query using transparent weights.

        Scoring model (documented):
        - exact title match: +100
        - title token match: +40 per token
        - alias match: +25
        - tag match: +30 per tag
        - content match: +20
        - same project: +15
        - high confidence: +10
        - source available: +10
        - type match: +10

        Note: `high_confidence` and `source` are boosts only - they do not
        qualify a note as a match. A note must match the query through title,
        tags, or content to be returned for a query-based retrieval.
        """
        score = base_score
        reasons: list[str] = []

        if query:
            q = query.lower().strip()
            title_lower = note.title.lower()
            normalized_q = normalize_title(query)
            normalized_title = normalize_title(note.title)

            # Exact title match
            if normalized_title == normalized_q:
                score += SCORE_EXACT_TITLE
                reasons.append("exact_title")

            # Title token matches
            query_tokens = set(re.findall(r"\w+", q))
            title_tokens = set(re.findall(r"\w+", title_lower))
            matched_tokens = query_tokens & title_tokens
            if matched_tokens:
                score += SCORE_TITLE_TOKEN * min(len(matched_tokens), 3)
                reasons.append(f"title_tokens:{','.join(sorted(matched_tokens)[:3])}")

            # Alias match
            for alias in note.aliases:
                if normalize_title(alias) == normalized_q:
                    score += SCORE_ALIAS_MATCH
                    reasons.append("alias")
                    break

            # Content match
            if q in note.content.lower():
                score += SCORE_CONTENT_MATCH
                reasons.append("content")

        # Tag match
        if query:
            for tag in note.tags:
                if tag.lower() in query.lower():
                    score += SCORE_TAG_MATCH
                    reasons.append(f"tag:{tag}")
                    break

        # Same project boost
        if query and note.project and note.project.lower() in query.lower():
            score += SCORE_SAME_PROJECT
            reasons.append("project")

        # Confidence boost (only qualifies when there's already a match reason)
        if reasons and note.confidence is not None and note.confidence >= 0.90:
            score += SCORE_HIGH_CONFIDENCE
            reasons.append("high_confidence")

        # Source available boost (only qualifies when there's already a match reason)
        if reasons and note.source and note.source != "generated":
            score += SCORE_SOURCE_AVAILABLE
            reasons.append("source")

        return RetrievedKnowledge(
            note_id=note.id,
            title=note.title,
            note_type=note.type,
            content=note.content,
            score=score,
            confidence=note.confidence,
            source=note.source,
            project=note.project,
            tags=note.tags,
            related=note.related,
            source_video_ids=note.source_video_ids,
            source_id=note.source_id,
            source_type=note.source_type,
            created_at=note.created_at,
            updated_at=note.updated_at,
            match_reasons=reasons,
        )

    # ------------------------------------------------------------------
    # Graph expansion
    # ------------------------------------------------------------------

    def _expand_graph(self, results: list[RetrievedKnowledge], max_expansion: int = MAX_GRAPH_EXPANSION) -> list[RetrievedKnowledge]:
        """Expand results through wikilinks and typed relationships.

        After finding the strongest direct matches, add related notes
        that are connected via relationships. Limit expansion to prevent
        context explosion.
        """
        # Rebuild the index fresh to ensure links created after the last
        # index build are reflected in the expansion.
        self._index_cache = self.indexer.index()
        index = self._index_cache
        expanded: list[RetrievedKnowledge] = list(results)
        seen_titles = {r.title for r in results}
        added = 0

        for result in results:
            if added >= max_expansion:
                break

            # Find the note in the index
            note = self.repository.read_note(result.note_id)
            if not note:
                continue

            # Get related titles from wikilinks, related, and graph
            related_titles = set(note.related)
            related_titles.update(self.linker.extract_wikilinks(note))
            if note.id in index.graph:
                for rel in index.graph[note.id]:
                    related_titles.add(rel["target"])

            # Add backlinks
            for title, backlinks in index.backlinks.items():
                if title == note.title:
                    related_titles.update(backlinks)

            for title in related_titles:
                if title in seen_titles:
                    continue
                related_note = self.repository.find_by_title(title)
                if not related_note:
                    continue
                item = self._score_note(related_note, "", 0.0)
                item.score = result.score * 0.5  # Related notes get half the source score
                item.expanded_from = result.title
                item.match_reasons.append("graph_expansion")
                expanded.append(item)
                seen_titles.add(title)
                added += 1
                if added >= max_expansion:
                    break

        # Re-sort with expanded items
        expanded.sort(key=lambda r: r.score, reverse=True)
        return expanded

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflicts(self, items: list[RetrievedKnowledge]) -> list[dict[str, Any]]:
        """Detect contradictions between retrieved notes.

        Uses the `contradicts` relationship type from the knowledge graph.
        """
        conflicts: list[dict[str, Any]] = []
        index = self._get_index()
        item_by_title = {item.title: item for item in items}

        for item in items:
            note = self.repository.read_note(item.note_id)
            if not note:
                continue
            if note.id not in index.graph:
                continue
            for rel in index.graph[note.id]:
                if rel["type"] == RelationshipType.CONTRADICTS.value:
                    target = item_by_title.get(rel["target"])
                    if target:
                        conflicts.append({
                            "source_title": item.title,
                            "source_confidence": item.confidence,
                            "target_title": target.title,
                            "target_confidence": target.confidence,
                            "relationship": "contradicts",
                        })
        return conflicts

    # ------------------------------------------------------------------
    # Index caching
    # ------------------------------------------------------------------

    def _get_index(self) -> VaultIndex:
        """Get the vault index, caching it for performance."""
        if self._index_cache is None:
            self._index_cache = self.indexer.index()
        return self._index_cache

    def invalidate_cache(self) -> None:
        """Invalidate the cached index (call after writes)."""
        self._index_cache = None
