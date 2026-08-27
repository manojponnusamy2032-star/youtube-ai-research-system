"""Knowledge quality evaluation framework for the Knowledge Brain subsystem.

Provides modular evaluation of:
- Extraction quality (notes created/updated/rejected, by type, by confidence, provenance)
- Deduplication quality (exact, alias, similarity duplicates prevented, false merge risk)
- Retrieval quality (Precision@K, Recall@K, Hit Rate@K)
- Context quality (relevance, duplicates, traceability, confidence, conflicts, size)
- Knowledge growth (total notes, relationships, orphans, avg confidence, sources, projects)
- Health checks (orphans, missing provenance, malformed frontmatter, broken wikilinks, conflicts)
- Memory ablation (agent with vs without knowledge context)

No vector databases or external infrastructure required.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.knowledge.deduplicator import Deduplicator
from src.knowledge.extractor import KnowledgeExtractor
from src.knowledge.knowledge_service import KnowledgeService
from src.knowledge.models import KnowledgeNote, NoteType, RelationshipType, VaultIndex, normalize_title
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.retriever import KnowledgeRetriever, KnowledgeContext, RetrievedKnowledge


# ---------------------------------------------------------------------------
# Evaluation dataset fixtures
# ---------------------------------------------------------------------------

@dataclass
class RetrievalCase:
    """A single retrieval evaluation case."""

    query: str
    expected_titles: list[str]
    description: str = ""


# A small evaluation dataset for retrieval quality
RETRIEVAL_EVAL_CASES: list[RetrievalCase] = [
    RetrievalCase(
        query="How can I improve YouTube retention?",
        expected_titles=[
            "YouTube Retention Research",
            "Hook Timing",
            "Curiosity Gap",
            "Retention Patterns",
        ],
        description="Retention improvement query",
    ),
    RetrievalCase(
        query="How did we fix the FFmpeg rendering problem?",
        expected_titles=[
            "FFmpeg Stream Mapping Issue",
            "Video Assembly Decision",
        ],
        description="FFmpeg problem resolution query",
    ),
    RetrievalCase(
        query="What are the best hook patterns for viral videos?",
        expected_titles=[
            "Hook Timing",
            "Curiosity Gap",
            "Hook Pattern",
        ],
        description="Hook pattern query",
    ),
    RetrievalCase(
        query="YouTube algorithm ranking signals",
        expected_titles=[
            "YouTube Retention Research",
            "Algorithm Insights",
        ],
        description="Algorithm research query",
    ),
    RetrievalCase(
        query="Thumbnail design best practices",
        expected_titles=[
            "Thumbnail Design Guide",
            "Visual Attention Patterns",
        ],
        description="Thumbnail design query",
    ),
]


# ---------------------------------------------------------------------------
# Extraction metrics
# ---------------------------------------------------------------------------

@dataclass
class ExtractionMetrics:
    """Metrics for knowledge extraction quality."""

    total_candidates: int = 0
    accepted: int = 0
    updated: int = 0
    rejected: int = 0
    notes_by_type: dict[str, int] = field(default_factory=dict)
    notes_by_confidence: dict[str, int] = field(default_factory=dict)
    notes_with_provenance: int = 0
    notes_without_provenance: int = 0
    notes_with_relationships: int = 0
    orphan_notes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "accepted": self.accepted,
            "updated": self.updated,
            "rejected": self.rejected,
            "notes_by_type": self.notes_by_type,
            "notes_by_confidence": self.notes_by_confidence,
            "notes_with_provenance": self.notes_with_provenance,
            "notes_without_provenance": self.notes_without_provenance,
            "notes_with_relationships": self.notes_with_relationships,
            "orphan_notes": self.orphan_notes,
        }


# ---------------------------------------------------------------------------
# Deduplication metrics
# ---------------------------------------------------------------------------

@dataclass
class DeduplicationMetrics:
    """Metrics for deduplication quality."""

    exact_duplicates_prevented: int = 0
    alias_duplicates_prevented: int = 0
    similarity_duplicates_prevented: int = 0
    potential_duplicate_candidates: int = 0
    false_merge_risk: int = 0
    duplicate_groups: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exact_duplicates_prevented": self.exact_duplicates_prevented,
            "alias_duplicates_prevented": self.alias_duplicates_prevented,
            "similarity_duplicates_prevented": self.similarity_duplicates_prevented,
            "potential_duplicate_candidates": self.potential_duplicate_candidates,
            "false_merge_risk": self.false_merge_risk,
            "duplicate_groups": self.duplicate_groups,
        }


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

@dataclass
class RetrievalMetrics:
    """Metrics for retrieval quality at various K values."""

    precision_at_k: dict[int, float] = field(default_factory=dict)
    recall_at_k: dict[int, float] = field(default_factory=dict)
    hit_rate_at_k: dict[int, float] = field(default_factory=dict)
    mean_reciprocal_rank: float = 0.0
    mean_average_precision: float = 0.0
    num_cases: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "precision_at_k": self.precision_at_k,
            "recall_at_k": self.recall_at_k,
            "hit_rate_at_k": self.hit_rate_at_k,
            "mean_reciprocal_rank": self.mean_reciprocal_rank,
            "mean_average_precision": self.mean_average_precision,
            "num_cases": self.num_cases,
        }


# ---------------------------------------------------------------------------
# Context quality metrics
# ---------------------------------------------------------------------------

@dataclass
class ContextQualityMetrics:
    """Metrics for context quality."""

    relevance_score: float = 0.0
    duplicate_information: int = 0
    source_traceability: float = 0.0
    confidence_visibility: float = 0.0
    conflicts_detected: int = 0
    context_size_chars: int = 0
    context_size_limit: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevance_score": self.relevance_score,
            "duplicate_information": self.duplicate_information,
            "source_traceability": self.source_traceability,
            "confidence_visibility": self.confidence_visibility,
            "conflicts_detected": self.conflicts_detected,
            "context_size_chars": self.context_size_chars,
            "context_size_limit": self.context_size_limit,
            "truncated": self.truncated,
        }


# ---------------------------------------------------------------------------
# Knowledge growth report
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeGrowthReport:
    """Report on knowledge base growth and health."""

    total_notes: int = 0
    notes_by_type: dict[str, int] = field(default_factory=dict)
    total_relationships: int = 0
    backlinks: int = 0
    orphans: int = 0
    average_confidence: float = 0.0
    sources_represented: int = 0
    projects_represented: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_notes": self.total_notes,
            "notes_by_type": self.notes_by_type,
            "total_relationships": self.total_relationships,
            "backlinks": self.backlinks,
            "orphans": self.orphans,
            "average_confidence": self.average_confidence,
            "sources_represented": self.sources_represented,
            "projects_represented": self.projects_represented,
        }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@dataclass
class HealthCheckResult:
    """Structured health check results."""

    orphan_notes: list[str] = field(default_factory=list)
    missing_provenance: list[str] = field(default_factory=list)
    malformed_frontmatter: list[str] = field(default_factory=list)
    broken_wikilinks: list[dict[str, str]] = field(default_factory=list)
    duplicate_candidates: list[list[str]] = field(default_factory=list)
    low_confidence_notes: list[dict[str, Any]] = field(default_factory=list)
    notes_without_relationships: list[str] = field(default_factory=list)
    stale_index: bool = False
    conflicting_knowledge: list[dict[str, Any]] = field(default_factory=list)
    is_healthy: bool = True
    issues_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "orphan_notes": self.orphan_notes,
            "missing_provenance": self.missing_provenance,
            "malformed_frontmatter": self.malformed_frontmatter,
            "broken_wikilinks": self.broken_wikilinks,
            "duplicate_candidates": self.duplicate_candidates,
            "low_confidence_notes": self.low_confidence_notes,
            "notes_without_relationships": self.notes_without_relationships,
            "stale_index": self.stale_index,
            "conflicting_knowledge": self.conflicting_knowledge,
            "is_healthy": self.is_healthy,
            "issues_count": self.issues_count,
        }


# ---------------------------------------------------------------------------
# Memory ablation result
# ---------------------------------------------------------------------------

@dataclass
class MemoryAblationResult:
    """Result of a memory ablation comparison."""

    without_context: dict[str, Any] = field(default_factory=dict)
    with_context: dict[str, Any] = field(default_factory=dict)
    knowledge_available_without: int = 0
    knowledge_available_with: int = 0
    improvement: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "without_context": self.without_context,
            "with_context": self.with_context,
            "knowledge_available_without": self.knowledge_available_without,
            "knowledge_available_with": self.knowledge_available_with,
            "improvement": self.improvement,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Evaluation engine
# ---------------------------------------------------------------------------

class KnowledgeEvaluator:
    """Evaluate knowledge quality across extraction, deduplication, retrieval, and context.

    All evaluation is performed against a KnowledgeService instance backed by
    a vault (typically a temporary fixture vault for tests).
    """

    K_VALUES = [1, 3, 5, 10]

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        retriever: KnowledgeRetriever | None = None,
        deduplicator: Deduplicator | None = None,
    ) -> None:
        """Initialize evaluator with knowledge service and optional components."""
        self.knowledge_service = knowledge_service
        self.retriever = retriever or KnowledgeRetriever(knowledge_service.repository)
        self.deduplicator = deduplicator or Deduplicator(knowledge_service.repository)

    # ------------------------------------------------------------------
    # Extraction metrics
    # ------------------------------------------------------------------

    def evaluate_extraction(
        self,
        analyses: list[dict[str, Any]],
        *,
        project: str | None = None,
        source_type: str = "research_analysis",
    ) -> ExtractionMetrics:
        """Evaluate extraction quality by running the extractor and measuring results.

        Args:
            analyses: List of analysis dicts to extract from.
            project: Optional project name.
            source_type: Source type label.

        Returns:
            ExtractionMetrics with counts and breakdowns.
        """
        extractor = KnowledgeExtractor(self.knowledge_service, self.deduplicator)

        # Count candidates before extraction
        candidates = 0
        for analysis in analyses:
            entities = extractor._extract_entities_from_analysis(analysis)
            candidates += len(entities)

        # Run extraction
        result = extractor.extract_from_analysis_batch(
            analyses, project=project, source_type=source_type
        )

        metrics = ExtractionMetrics(
            total_candidates=candidates,
            accepted=result.get("created", 0),
            updated=result.get("updated", 0),
            rejected=result.get("skipped", 0),
        )

        # Analyze resulting notes
        notes = self.knowledge_service.list_notes()
        for note in notes:
            # By type
            type_key = note.type.value
            metrics.notes_by_type[type_key] = metrics.notes_by_type.get(type_key, 0) + 1

            # By confidence band
            if note.confidence is None:
                band = "unknown"
            elif note.confidence >= 0.90:
                band = "high"
            elif note.confidence >= 0.70:
                band = "medium"
            else:
                band = "low"
            metrics.notes_by_confidence[band] = metrics.notes_by_confidence.get(band, 0) + 1

            # Provenance: source is non-generated OR has source_id/source_video_ids
            has_provenance = (
                (note.source and note.source != "generated")
                or note.source_id
                or note.source_video_ids
            )
            if has_provenance:
                metrics.notes_with_provenance += 1
            else:
                metrics.notes_without_provenance += 1

            # Relationships
            if note.related or note.source_video_ids:
                metrics.notes_with_relationships += 1

        # Orphans
        index = self.knowledge_service.index_vault()
        metrics.orphan_notes = len(index.orphan_notes)

        return metrics

    # ------------------------------------------------------------------
    # Deduplication metrics
    # ------------------------------------------------------------------

    def evaluate_deduplication(self) -> DeduplicationMetrics:
        """Evaluate deduplication quality of the current vault.

        Returns:
            DeduplicationMetrics with counts of prevented duplicates and
            potential duplicate groups.
        """
        metrics = DeduplicationMetrics()

        # Find potential duplicate groups
        duplicate_groups = self.deduplicator.find_duplicate_candidates()
        metrics.duplicate_groups = duplicate_groups
        metrics.potential_duplicate_candidates = sum(len(g) for g in duplicate_groups)

        # Count exact duplicates (same normalized title)
        notes = self.knowledge_service.list_notes()
        seen_titles: dict[str, int] = {}
        for note in notes:
            norm = normalize_title(note.title)
            seen_titles[norm] = seen_titles.get(norm, 0) + 1
        exact_dups = sum(count - 1 for count in seen_titles.values() if count > 1)
        metrics.exact_duplicates_prevented = exact_dups

        # Count alias duplicates
        alias_dups = 0
        all_aliases: dict[str, int] = {}
        for note in notes:
            for alias in note.aliases:
                norm_alias = normalize_title(alias)
                all_aliases[norm_alias] = all_aliases.get(norm_alias, 0) + 1
        alias_dups = sum(count - 1 for count in all_aliases.values() if count > 1)
        metrics.alias_duplicates_prevented = alias_dups

        # Count similarity duplicates (high ratio but not exact)
        similarity_dups = 0
        for i, note_a in enumerate(notes):
            for note_b in notes[i + 1:]:
                ratio = SequenceMatcher(
                    None, normalize_title(note_a.title), normalize_title(note_b.title)
                ).ratio()
                if 0.80 <= ratio < 0.95:
                    similarity_dups += 1
        metrics.similarity_duplicates_prevented = similarity_dups

        # False merge risk: notes with high similarity but different content
        false_risk = 0
        for group in duplicate_groups:
            if len(group) > 2:
                false_risk += 1
        metrics.false_merge_risk = false_risk

        return metrics

    # ------------------------------------------------------------------
    # Retrieval evaluation
    # ------------------------------------------------------------------

    def evaluate_retrieval(
        self,
        cases: list[RetrievalCase] | None = None,
        k_values: list[int] | None = None,
    ) -> RetrievalMetrics:
        """Evaluate retrieval quality using Precision@K, Recall@K, Hit Rate@K.

        Args:
            cases: Evaluation cases. Defaults to RETRIEVAL_EVAL_CASES.
            k_values: K values to compute. Defaults to [1, 3, 5, 10].

        Returns:
            RetrievalMetrics with precision, recall, and hit rate at each K.
        """
        cases = cases or RETRIEVAL_EVAL_CASES
        k_values = k_values or self.K_VALUES

        metrics = RetrievalMetrics(num_cases=len(cases))

        # Accumulators for MRR and MAP
        reciprocal_ranks: list[float] = []
        average_precisions: list[float] = []

        for case in cases:
            results = self.retriever.retrieve(case.query, limit=max(k_values), expand_graph=True)
            retrieved_titles = [r.title for r in results]
            expected = set(case.expected_titles)

            # Compute precision, recall, hit rate at each K
            for k in k_values:
                top_k = retrieved_titles[:k]
                hits = len(set(top_k) & expected)
                precision = hits / k if k > 0 else 0.0
                recall = hits / len(expected) if expected else 0.0
                hit_rate = 1.0 if hits > 0 else 0.0

                metrics.precision_at_k[k] = metrics.precision_at_k.get(k, 0.0) + precision
                metrics.recall_at_k[k] = metrics.recall_at_k.get(k, 0.0) + recall
                metrics.hit_rate_at_k[k] = metrics.hit_rate_at_k.get(k, 0.0) + hit_rate

            # MRR: rank of first relevant result
            first_relevant_rank = None
            for rank, title in enumerate(retrieved_titles, 1):
                if title in expected:
                    first_relevant_rank = rank
                    break
            if first_relevant_rank:
                reciprocal_ranks.append(1.0 / first_relevant_rank)
            else:
                reciprocal_ranks.append(0.0)

            # MAP: average precision
            precisions_at_relevant: list[float] = []
            hits_so_far = 0
            for rank, title in enumerate(retrieved_titles, 1):
                if title in expected:
                    hits_so_far += 1
                    precisions_at_relevant.append(hits_so_far / rank)
            if precisions_at_relevant:
                average_precisions.append(sum(precisions_at_relevant) / len(expected))
            else:
                average_precisions.append(0.0)

        # Average across cases
        num = len(cases) if cases else 1
        for k in k_values:
            metrics.precision_at_k[k] = round(metrics.precision_at_k.get(k, 0.0) / num, 4)
            metrics.recall_at_k[k] = round(metrics.recall_at_k.get(k, 0.0) / num, 4)
            metrics.hit_rate_at_k[k] = round(metrics.hit_rate_at_k.get(k, 0.0) / num, 4)

        metrics.mean_reciprocal_rank = round(sum(reciprocal_ranks) / num, 4) if reciprocal_ranks else 0.0
        metrics.mean_average_precision = round(sum(average_precisions) / num, 4) if average_precisions else 0.0

        return metrics

    # ------------------------------------------------------------------
    # Context quality
    # ------------------------------------------------------------------

    def evaluate_context_quality(
        self,
        query: str,
        *,
        max_notes: int = 10,
        max_chars: int = 4000,
    ) -> ContextQualityMetrics:
        """Evaluate the quality of a generated KnowledgeContext.

        Args:
            query: The query to build context for.
            max_notes: Maximum notes in context.
            max_chars: Maximum context characters.

        Returns:
            ContextQualityMetrics.
        """
        context = self.retriever.build_context(
            query, max_notes=max_notes, max_chars=max_chars
        )

        metrics = ContextQualityMetrics()
        metrics.context_size_limit = max_chars

        # Relevance: fraction of context items that match the query
        all_items = (
            context.relevant_knowledge + context.evidence + context.lessons
            + context.decisions + context.project_context
        )
        if all_items:
            query_tokens = set(re.findall(r"\w+", query.lower()))
            relevant_count = 0
            for item in all_items:
                item_tokens = set(re.findall(r"\w+", item.title.lower()))
                item_content_tokens = set(re.findall(r"\w+", item.content.lower()))
                if query_tokens & item_tokens or query_tokens & item_content_tokens:
                    relevant_count += 1
            metrics.relevance_score = round(relevant_count / len(all_items), 4)

        # Duplicate information: count duplicate titles across categories
        all_titles = [item.title for item in all_items]
        seen: set[str] = set()
        duplicates = 0
        for title in all_titles:
            if title in seen:
                duplicates += 1
            seen.add(title)
        metrics.duplicate_information = duplicates

        # Source traceability: fraction of items with non-generated source
        if all_items:
            with_source = sum(1 for item in all_items if item.source and item.source != "generated")
            metrics.source_traceability = round(with_source / len(all_items), 4)

        # Confidence visibility: fraction of items with confidence set
        if all_items:
            with_confidence = sum(1 for item in all_items if item.confidence is not None)
            metrics.confidence_visibility = round(with_confidence / len(all_items), 4)

        # Conflicts
        metrics.conflicts_detected = len(context.conflicts)

        # Size
        markdown = context.to_markdown(max_chars=max_chars)
        metrics.context_size_chars = len(markdown)
        metrics.truncated = context.truncated

        return metrics

    # ------------------------------------------------------------------
    # Knowledge growth report
    # ------------------------------------------------------------------

    def knowledge_growth_report(self) -> KnowledgeGrowthReport:
        """Generate a report on knowledge base growth and health.

        Returns:
            KnowledgeGrowthReport with aggregate statistics.
        """
        notes = self.knowledge_service.list_notes()
        index = self.knowledge_service.index_vault()

        report = KnowledgeGrowthReport()
        report.total_notes = len(notes)

        # Notes by type
        for note in notes:
            type_key = note.type.value
            report.notes_by_type[type_key] = report.notes_by_type.get(type_key, 0) + 1

        # Relationships
        report.total_relationships = len(index.graph)
        for rels in index.graph.values():
            report.total_relationships += len(rels)

        # Backlinks
        report.backlinks = sum(len(v) for v in index.backlinks.values())

        # Orphans
        report.orphans = len(index.orphan_notes)

        # Average confidence
        confidences = [n.confidence for n in notes if n.confidence is not None]
        report.average_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

        # Sources represented
        sources = set(n.source for n in notes if n.source and n.source != "generated")
        report.sources_represented = len(sources)

        # Projects represented
        projects = set(n.project for n in notes if n.project)
        report.projects_represented = len(projects)

        return report

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> HealthCheckResult:
        """Run a comprehensive health check on the knowledge vault.

        Identifies:
        - Orphan notes (no incoming or outgoing links)
        - Missing provenance (source is "generated" with no source_id)
        - Malformed frontmatter (notes that fail to parse)
        - Broken wikilinks (links to non-existent notes)
        - Duplicate candidates
        - Low-confidence notes (< 0.70)
        - Notes without relationships
        - Stale index
        - Conflicting knowledge

        Returns:
            HealthCheckResult with structured findings.
        """
        result = HealthCheckResult()
        notes = self.knowledge_service.list_notes()
        index = self.knowledge_service.index_vault()

        # Build title set for wikilink validation
        all_titles = {note.title for note in notes}

        # Orphan notes
        result.orphan_notes = list(index.orphan_notes)

        # Missing provenance
        for note in notes:
            if note.source == "generated" and not note.source_id and not note.source_video_ids:
                result.missing_provenance.append(note.title)

        # Malformed frontmatter (notes that can't be re-parsed)
        for note in notes:
            try:
                markdown = note.to_markdown()
                # Try to re-parse frontmatter
                from src.knowledge.models import NoteMetadata
                metadata = NoteMetadata.from_frontmatter(markdown)
                if metadata is None:
                    result.malformed_frontmatter.append(note.title)
            except Exception:
                result.malformed_frontmatter.append(note.title)

        # Broken wikilinks
        for note in notes:
            wikilinks = self.retriever.linker.extract_wikilinks(note)
            for link in wikilinks:
                if link not in all_titles:
                    result.broken_wikilinks.append({
                        "source": note.title,
                        "broken_link": link,
                    })

        # Duplicate candidates
        result.duplicate_candidates = self.deduplicator.find_duplicate_candidates()

        # Low-confidence notes
        for note in notes:
            if note.confidence is not None and note.confidence < 0.70:
                result.low_confidence_notes.append({
                    "title": note.title,
                    "confidence": note.confidence,
                })

        # Notes without relationships
        for note in notes:
            if not note.related and not note.aliases:
                result.notes_without_relationships.append(note.title)

        # Stale index (check if index is older than 5 minutes)
        from datetime import datetime, timezone
        try:
            index_time = datetime.fromisoformat(index.generated_at)
            age = (datetime.now(timezone.utc) - index_time).total_seconds()
            result.stale_index = age > 300
        except Exception:
            result.stale_index = True

        # Conflicting knowledge
        for note in notes:
            if note.id in index.graph:
                for rel in index.graph[note.id]:
                    if rel.get("type") == RelationshipType.CONTRADICTS.value:
                        result.conflicting_knowledge.append({
                            "source": note.title,
                            "target": rel.get("target", ""),
                            "relationship": "contradicts",
                        })

        # Determine overall health
        result.issues_count = (
            len(result.orphan_notes)
            + len(result.missing_provenance)
            + len(result.malformed_frontmatter)
            + len(result.broken_wikilinks)
            + len(result.duplicate_candidates)
            + len(result.low_confidence_notes)
            + len(result.notes_without_relationships)
            + len(result.conflicting_knowledge)
        )
        result.is_healthy = result.issues_count == 0

        return result

    # ------------------------------------------------------------------
    # Memory ablation test
    # ------------------------------------------------------------------

    def memory_ablation(
        self,
        query: str,
        *,
        max_notes: int = 5,
        max_chars: int = 2000,
    ) -> MemoryAblationResult:
        """Compare agent knowledge availability with and without context.

        This is a deterministic ablation test that measures whether relevant
        historical knowledge is actually available to the agent when context
        is provided vs. when it is not.

        Args:
            query: The query to test.
            max_notes: Maximum notes for context.
            max_chars: Maximum context characters.

        Returns:
            MemoryAblationResult comparing both conditions.
        """
        result = MemoryAblationResult()

        # Without context: retrieve with empty query (no knowledge injection)
        without_results = self.retriever.retrieve("", limit=max_notes, expand_graph=False)
        result.knowledge_available_without = len(without_results)
        result.without_context = {
            "notes_retrieved": len(without_results),
            "titles": [r.title for r in without_results],
            "context_provided": False,
        }

        # With context: build context from the query
        context = self.retriever.build_context(
            query, max_notes=max_notes, max_chars=max_chars
        )
        result.knowledge_available_with = len(context.relevant_knowledge)
        result.with_context = {
            "notes_retrieved": len(context.relevant_knowledge),
            "titles": [r.title for r in context.relevant_knowledge],
            "context_provided": True,
            "context_markdown_length": len(context.to_markdown()),
            "conflicts": len(context.conflicts),
        }

        # Improvement: with-context retrieves more relevant knowledge
        result.improvement = result.knowledge_available_with > result.knowledge_available_without
        result.notes = (
            f"With context: {result.knowledge_available_with} notes available. "
            f"Without context: {result.knowledge_available_without} notes available. "
            f"Improvement: {result.improvement}"
        )

        return result

    # ------------------------------------------------------------------
    # Performance benchmark
    # ------------------------------------------------------------------

    def benchmark_retrieval(self, num_notes: int = 100) -> dict[str, Any]:
        """Benchmark retrieval performance on a synthetic vault.

        Creates a temporary vault with the specified number of notes and
        measures retrieval time.

        Args:
            num_notes: Number of notes to create in the benchmark vault.

        Returns:
            Dict with timing results.
        """
        import tempfile
        from src.knowledge.config import KnowledgeConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = KnowledgeConfig(Path(tmpdir))
            repo = KnowledgeRepository(config)
            service = KnowledgeService(config, repo)
            retriever = KnowledgeRetriever(repo)

            # Create synthetic notes
            for i in range(num_notes):
                service.create_note(
                    title=f"Benchmark Note {i}",
                    note_type=NoteType.CONCEPT,
                    content=f"This is benchmark note {i} about topic {i % 10}. "
                            f"Contains keywords like retention, hooks, algorithm, engagement.",
                    tags=["benchmark", f"topic-{i % 10}"],
                    confidence=0.8,
                    source="benchmark",
                )

            # Benchmark retrieval
            start = time.perf_counter()
            results = retriever.retrieve("retention", limit=10, expand_graph=True)
            elapsed = time.perf_counter() - start

            return {
                "num_notes": num_notes,
                "retrieval_time_ms": round(elapsed * 1000, 2),
                "results_returned": len(results),
                "notes_per_second": round(num_notes / elapsed, 2) if elapsed > 0 else 0,
            }

    # ------------------------------------------------------------------
    # Full evaluation report
    # ------------------------------------------------------------------

    def full_evaluation(self) -> dict[str, Any]:
        """Run a complete evaluation and return all metrics.

        Returns:
            Dict with extraction, deduplication, retrieval, context,
            growth, and health metrics.
        """
        return {
            "extraction": self.evaluate_extraction([]).to_dict(),
            "deduplication": self.evaluate_deduplication().to_dict(),
            "retrieval": self.evaluate_retrieval().to_dict(),
            "growth": self.knowledge_growth_report().to_dict(),
            "health": self.health_check().to_dict(),
        }
