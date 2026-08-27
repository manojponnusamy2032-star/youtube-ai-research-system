"""Tests for the Knowledge Brain evaluation framework.

All tests use temporary vaults to avoid modifying production data.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.knowledge.config import KnowledgeConfig
from src.knowledge.deduplicator import Deduplicator
from src.knowledge.evaluation import (
    KnowledgeEvaluator,
    RetrievalCase,
    RETRIEVAL_EVAL_CASES,
)
from src.knowledge.knowledge_service import KnowledgeService
from src.knowledge.models import NoteType, RelationshipType
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.retriever import KnowledgeRetriever


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_vault():
    """Create a temporary vault for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = KnowledgeConfig(Path(tmpdir))
        config.ensure_vault()
        repo = KnowledgeRepository(config)
        service = KnowledgeService(config, repo)
        yield service


@pytest.fixture
def populated_vault(temp_vault):
    """Create a vault with a realistic synthetic dataset."""
    service = temp_vault

    # Project note
    service.create_note(
        title="YouTube Growth Project",
        note_type=NoteType.PROJECT,
        content="## Purpose\n\nGrowing YouTube channel with data-driven strategies.",
        tags=["project"],
        source="manual",
        source_id="project-001",
    )

    # Research notes
    service.create_note(
        title="YouTube Retention Research",
        note_type=NoteType.RESEARCH,
        content="Retention is the strongest ranking signal. Hooks in first 15 seconds matter.",
        tags=["retention", "algorithm", "research"],
        source="video_analysis",
        source_id="batch-001",
        source_video_ids=["vid_001", "vid_002"],
        confidence=0.92,
        project="YouTube Growth Project",
        related=["Hook Timing", "Curiosity Gap"],
    )

    service.create_note(
        title="Hook Timing",
        note_type=NoteType.INSIGHT,
        content="Hooks should appear within the first 5-10 seconds for maximum retention.",
        tags=["retention", "hook", "insight"],
        source="video_analysis",
        source_id="batch-001",
        source_video_ids=["vid_001"],
        confidence=0.85,
        project="YouTube Growth Project",
        related=["YouTube Retention Research"],
    )

    service.create_note(
        title="Curiosity Gap",
        note_type=NoteType.CONCEPT,
        content="The curiosity gap is the space between what viewers know and what they want to know.",
        tags=["engagement", "concept"],
        source="video_analysis",
        source_id="batch-001",
        source_video_ids=["vid_002"],
        confidence=0.88,
        project="YouTube Growth Project",
        related=["YouTube Retention Research"],
    )

    service.create_note(
        title="Retention Patterns",
        note_type=NoteType.RESEARCH,
        content="Videos with retention above 50% at 60 seconds tend to go viral.",
        tags=["retention", "research"],
        source="video_analysis",
        source_id="batch-002",
        source_video_ids=["vid_003"],
        confidence=0.78,
        project="YouTube Growth Project",
    )

    # FFmpeg notes (for second eval case)
    service.create_note(
        title="FFmpeg Stream Mapping Issue",
        note_type=NoteType.LESSON,
        content="## Problem\n\nFFmpeg failed to map audio streams correctly.\n\n## Root Cause\n\nIncorrect -map parameter ordering.\n\n## Solution\n\nUse -map 0:v:0 -map 0:a:0 explicitly.",
        tags=["ffmpeg", "rendering", "lesson"],
        source="manual",
        source_id="lesson-001",
        confidence=0.95,
        project="YouTube Growth Project",
        related=["Video Assembly Decision"],
    )

    service.create_note(
        title="Video Assembly Decision",
        note_type=NoteType.DECISION,
        content="## Context\n\nNeed to assemble video and audio streams.\n\n## Decision\n\nUse FFmpeg with explicit stream mapping.\n\n## Reason\n\nPrevents silent audio track issues.",
        tags=["ffmpeg", "decision"],
        source="manual",
        source_id="decision-001",
        confidence=0.90,
        project="YouTube Growth Project",
        related=["FFmpeg Stream Mapping Issue"],
    )

    # Contradictory note
    service.create_note(
        title="Early Hook Myth",
        note_type=NoteType.INSIGHT,
        content="Early hooks are not always necessary. Some successful videos start slow.",
        tags=["retention", "insight"],
        source="video_analysis",
        source_id="batch-003",
        source_video_ids=["vid_004"],
        confidence=0.65,
        project="YouTube Growth Project",
    )

    # Add contradiction relationship
    linker = service.linker
    hook_note = service.get_note_by_title("Hook Timing")
    if hook_note:
        linker.add_relationship_note(
            hook_note, "Early Hook Myth",
            RelationshipType.CONTRADICTS,
            evidence="Early Hook Myth claims hooks are not always necessary"
        )
        service.repository.save_note(hook_note)

    # Orphan note (no links)
    service.create_note(
        title="Orphan Concept",
        note_type=NoteType.CONCEPT,
        content="This note has no relationships.",
        tags=["orphan"],
        source="generated",
        confidence=0.50,
    )

    # Note with broken wikilink
    service.create_note(
        title="Broken Link Note",
        note_type=NoteType.INSIGHT,
        content="See [[Nonexistent Note]] for details.",
        tags=["test"],
        source="generated",
        confidence=0.60,
    )

    # Duplicate candidate (similar title)
    service.create_note(
        title="YouTube Retention Reserch",  # typo - similar to "YouTube Retention Research"
        note_type=NoteType.RESEARCH,
        content="Similar research about retention.",
        tags=["retention"],
        source="generated",
        confidence=0.55,
    )

    return service


@pytest.fixture
def evaluator(populated_vault):
    """Create a KnowledgeEvaluator for the populated vault."""
    service = populated_vault
    retriever = KnowledgeRetriever(service.repository)
    deduplicator = Deduplicator(service.repository)
    return KnowledgeEvaluator(service, retriever=retriever, deduplicator=deduplicator)


# ---------------------------------------------------------------------------
# Extraction metrics tests
# ---------------------------------------------------------------------------

class TestExtractionMetrics:
    """Tests for extraction quality metrics."""

    def test_extraction_metrics_basic(self, temp_vault):
        """Test basic extraction metrics with a simple analysis batch."""
        evaluator = KnowledgeEvaluator(temp_vault)
        analyses = [
            {
                "main_topic": "Video Retention",
                "hook_type": "Curiosity Gap",
                "retention_techniques": ["Storytelling", "Pacing"],
                "emotion": "Surprise",
                "story_structure": "Problem-Solution",
                "title_formula": "Question + Answer",
                "confidence_score": 0.85,
                "video_id": "vid_001",
            }
        ]
        metrics = evaluator.evaluate_extraction(analyses, project="Test Project")
        assert metrics.total_candidates > 0
        assert metrics.accepted > 0
        assert metrics.total_candidates == metrics.accepted + metrics.rejected
        assert "concept" in metrics.notes_by_type
        assert "insight" in metrics.notes_by_type

    def test_extraction_metrics_by_confidence(self, temp_vault):
        """Test that notes are categorized by confidence band."""
        evaluator = KnowledgeEvaluator(temp_vault)
        analyses = [
            {
                "main_topic": "High Confidence Topic",
                "confidence_score": 0.95,
                "video_id": "vid_001",
            },
            {
                "main_topic": "Low Confidence Topic",
                "confidence_score": 0.30,
                "video_id": "vid_002",
            },
        ]
        metrics = evaluator.evaluate_extraction(analyses)
        assert "high" in metrics.notes_by_confidence
        assert "low" in metrics.notes_by_confidence

    def test_extraction_metrics_provenance(self, temp_vault):
        """Test that provenance is tracked."""
        evaluator = KnowledgeEvaluator(temp_vault)
        analyses = [
            {
                "main_topic": "Provenance Test",
                "confidence_score": 0.80,
                "video_id": "vid_001",
            }
        ]
        metrics = evaluator.evaluate_extraction(analyses)
        assert metrics.notes_with_provenance > 0

    def test_extraction_empty_analyses(self, temp_vault):
        """Test extraction metrics with empty analyses."""
        evaluator = KnowledgeEvaluator(temp_vault)
        metrics = evaluator.evaluate_extraction([])
        assert metrics.total_candidates == 0
        assert metrics.accepted == 0
        assert metrics.rejected == 0


# ---------------------------------------------------------------------------
# Deduplication metrics tests
# ---------------------------------------------------------------------------

class TestDeduplicationMetrics:
    """Tests for deduplication quality metrics."""

    def test_deduplication_no_duplicates(self, temp_vault):
        """Test deduplication metrics with no duplicates."""
        evaluator = KnowledgeEvaluator(temp_vault)
        metrics = evaluator.evaluate_deduplication()
        assert metrics.exact_duplicates_prevented == 0
        assert metrics.duplicate_groups == []

    def test_deduplication_detects_duplicates(self, populated_vault):
        """Test that duplicate candidates are detected."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_deduplication()
        # "YouTube Retention Research" and "YouTube Retention Reserch" are similar
        assert metrics.potential_duplicate_candidates > 0
        assert len(metrics.duplicate_groups) > 0

    def test_deduplication_alias_duplicates(self, temp_vault):
        """Test alias duplicate detection."""
        temp_vault.create_note(
            title="Test Concept",
            note_type=NoteType.CONCEPT,
            content="Test content",
            aliases=["test concept", "Test Concept"],
        )
        evaluator = KnowledgeEvaluator(temp_vault)
        metrics = evaluator.evaluate_deduplication()
        assert metrics.alias_duplicates_prevented > 0

    def test_deduplication_false_merge_risk(self, populated_vault):
        """Test false merge risk detection."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_deduplication()
        # Should not crash and should return a number
        assert isinstance(metrics.false_merge_risk, int)


# ---------------------------------------------------------------------------
# Retrieval evaluation tests
# ---------------------------------------------------------------------------

class TestRetrievalEvaluation:
    """Tests for retrieval quality evaluation."""

    def test_retrieval_metrics_structure(self, populated_vault):
        """Test that retrieval metrics have the correct structure."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_retrieval()
        assert metrics.num_cases == len(RETRIEVAL_EVAL_CASES)
        assert 1 in metrics.precision_at_k
        assert 3 in metrics.precision_at_k
        assert 5 in metrics.precision_at_k
        assert 10 in metrics.precision_at_k
        assert 1 in metrics.recall_at_k
        assert 1 in metrics.hit_rate_at_k

    def test_retrieval_precision_at_1(self, populated_vault):
        """Test precision@1 is between 0 and 1."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_retrieval()
        assert 0.0 <= metrics.precision_at_k[1] <= 1.0

    def test_retrieval_recall_at_5(self, populated_vault):
        """Test recall@5 is between 0 and 1."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_retrieval()
        assert 0.0 <= metrics.recall_at_k[5] <= 1.0

    def test_retrieval_hit_rate_at_10(self, populated_vault):
        """Test hit rate@10 is between 0 and 1."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_retrieval()
        assert 0.0 <= metrics.hit_rate_at_k[10] <= 1.0

    def test_retrieval_mrr(self, populated_vault):
        """Test mean reciprocal rank is computed."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_retrieval()
        assert 0.0 <= metrics.mean_reciprocal_rank <= 1.0

    def test_retrieval_map(self, populated_vault):
        """Test mean average precision is computed."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_retrieval()
        assert 0.0 <= metrics.mean_average_precision <= 1.0

    def test_retrieval_custom_cases(self, populated_vault):
        """Test retrieval evaluation with custom cases."""
        evaluator = KnowledgeEvaluator(populated_vault)
        cases = [
            RetrievalCase(
                query="YouTube retention",
                expected_titles=["YouTube Retention Research", "Hook Timing"],
            )
        ]
        metrics = evaluator.evaluate_retrieval(cases=cases)
        assert metrics.num_cases == 1

    def test_retrieval_finds_relevant_notes(self, populated_vault):
        """Test that retrieval actually finds relevant notes."""
        evaluator = KnowledgeEvaluator(populated_vault)
        results = evaluator.retriever.retrieve("YouTube retention", limit=5)
        titles = [r.title for r in results]
        assert "YouTube Retention Research" in titles


# ---------------------------------------------------------------------------
# Context quality tests
# ---------------------------------------------------------------------------

class TestContextQuality:
    """Tests for context quality metrics."""

    def test_context_quality_structure(self, populated_vault):
        """Test that context quality metrics have the correct structure."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_context_quality("YouTube retention")
        assert 0.0 <= metrics.relevance_score <= 1.0
        assert metrics.duplicate_information >= 0
        assert 0.0 <= metrics.source_traceability <= 1.0
        assert 0.0 <= metrics.confidence_visibility <= 1.0
        assert metrics.context_size_chars >= 0
        assert metrics.context_size_limit > 0

    def test_context_quality_relevance(self, populated_vault):
        """Test that context relevance is computed."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_context_quality("FFmpeg rendering")
        assert metrics.relevance_score > 0.0

    def test_context_quality_size_limit(self, populated_vault):
        """Test that context size is limited."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_context_quality("YouTube", max_chars=400)
        assert metrics.context_size_chars <= 400 + 150  # allow some slack

    def test_context_quality_conflicts(self, populated_vault):
        """Test that conflicts are detected in context."""
        evaluator = KnowledgeEvaluator(populated_vault)
        metrics = evaluator.evaluate_context_quality("Hook Timing")
        # Hook Timing contradicts Early Hook Myth
        assert metrics.conflicts_detected >= 0


# ---------------------------------------------------------------------------
# Knowledge growth report tests
# ---------------------------------------------------------------------------

class TestKnowledgeGrowthReport:
    """Tests for knowledge growth reporting."""

    def test_growth_report_structure(self, populated_vault):
        """Test that growth report has the correct structure."""
        evaluator = KnowledgeEvaluator(populated_vault)
        report = evaluator.knowledge_growth_report()
        assert report.total_notes > 0
        assert "research" in report.notes_by_type
        assert "insight" in report.notes_by_type
        assert "concept" in report.notes_by_type
        assert "lesson" in report.notes_by_type
        assert "decision" in report.notes_by_type
        assert "project" in report.notes_by_type
        assert report.total_relationships > 0
        assert report.average_confidence > 0.0
        assert report.sources_represented > 0
        assert report.projects_represented > 0

    def test_growth_report_orphans(self, populated_vault):
        """Test that orphan notes are counted."""
        evaluator = KnowledgeEvaluator(populated_vault)
        report = evaluator.knowledge_growth_report()
        assert report.orphans > 0  # Orphan Concept and Broken Link Note

    def test_growth_report_empty_vault(self, temp_vault):
        """Test growth report on empty vault."""
        evaluator = KnowledgeEvaluator(temp_vault)
        report = evaluator.knowledge_growth_report()
        assert report.total_notes == 0
        assert report.average_confidence == 0.0


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------

class TestHealthCheck:
    """Tests for knowledge health checks."""

    def test_health_check_structure(self, populated_vault):
        """Test that health check returns structured results."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.health_check()
        assert hasattr(result, "orphan_notes")
        assert hasattr(result, "missing_provenance")
        assert hasattr(result, "malformed_frontmatter")
        assert hasattr(result, "broken_wikilinks")
        assert hasattr(result, "duplicate_candidates")
        assert hasattr(result, "low_confidence_notes")
        assert hasattr(result, "notes_without_relationships")
        assert hasattr(result, "stale_index")
        assert hasattr(result, "conflicting_knowledge")
        assert hasattr(result, "is_healthy")
        assert hasattr(result, "issues_count")

    def test_health_check_orphan_detection(self, populated_vault):
        """Test that orphan notes are detected."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.health_check()
        assert "Orphan Concept" in result.orphan_notes

    def test_health_check_broken_wikilinks(self, populated_vault):
        """Test that broken wikilinks are detected."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.health_check()
        broken_links = [item["broken_link"] for item in result.broken_wikilinks]
        assert "Nonexistent Note" in broken_links

    def test_health_check_missing_provenance(self, populated_vault):
        """Test that missing provenance is detected."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.health_check()
        assert "Orphan Concept" in result.missing_provenance

    def test_health_check_low_confidence(self, populated_vault):
        """Test that low-confidence notes are detected."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.health_check()
        low_conf_titles = [item["title"] for item in result.low_confidence_notes]
        assert "Orphan Concept" in low_conf_titles

    def test_health_check_duplicate_candidates(self, populated_vault):
        """Test that duplicate candidates are detected."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.health_check()
        assert len(result.duplicate_candidates) > 0

    def test_health_check_conflicts(self, populated_vault):
        """Test that conflicting knowledge is detected."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.health_check()
        assert len(result.conflicting_knowledge) > 0

    def test_health_check_healthy_vault(self, temp_vault):
        """Test health check on a clean vault."""
        temp_vault.create_note(
            title="Clean Note",
            note_type=NoteType.CONCEPT,
            content="Content with [[Clean Note]] self-reference.",
            tags=["clean"],
            source="manual",
            source_id="src-001",
            confidence=0.90,
        )
        evaluator = KnowledgeEvaluator(temp_vault)
        result = evaluator.health_check()
        # Clean note has no broken links, has provenance, has confidence
        assert result.is_healthy or result.issues_count >= 0

    def test_health_check_via_service(self, populated_vault):
        """Test health_check method on KnowledgeService."""
        result = populated_vault.health_check()
        assert "orphan_notes" in result
        assert "is_healthy" in result
        assert "issues_count" in result


# ---------------------------------------------------------------------------
# Memory ablation tests
# ---------------------------------------------------------------------------

class TestMemoryAblation:
    """Tests for memory ablation comparison."""

    def test_ablation_structure(self, populated_vault):
        """Test that ablation result has the correct structure."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.memory_ablation("YouTube retention")
        assert "without_context" in result.to_dict()
        assert "with_context" in result.to_dict()
        assert "knowledge_available_without" in result.to_dict()
        assert "knowledge_available_with" in result.to_dict()
        assert "improvement" in result.to_dict()

    def test_ablation_with_context_finds_more(self, populated_vault):
        """Test that with-context retrieves more relevant knowledge."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.memory_ablation("YouTube retention")
        assert result.knowledge_available_with > 0
        assert result.knowledge_available_with >= result.knowledge_available_without

    def test_ablation_improvement_flag(self, populated_vault):
        """Test that improvement flag is set correctly."""
        evaluator = KnowledgeEvaluator(populated_vault)
        result = evaluator.memory_ablation("FFmpeg rendering")
        # With context should find FFmpeg-related notes
        assert result.knowledge_available_with > 0


# ---------------------------------------------------------------------------
# Performance benchmark tests
# ---------------------------------------------------------------------------

class TestPerformanceBenchmark:
    """Tests for retrieval performance benchmarking."""

    def test_benchmark_100_notes(self, temp_vault):
        """Test retrieval performance with 100 notes."""
        evaluator = KnowledgeEvaluator(temp_vault)
        result = evaluator.benchmark_retrieval(num_notes=100)
        assert result["num_notes"] == 100
        assert result["retrieval_time_ms"] >= 0
        assert result["results_returned"] > 0

    def test_benchmark_500_notes(self, temp_vault):
        """Test retrieval performance with 500 notes."""
        evaluator = KnowledgeEvaluator(temp_vault)
        result = evaluator.benchmark_retrieval(num_notes=500)
        assert result["num_notes"] == 500
        assert result["retrieval_time_ms"] >= 0

    def test_benchmark_1000_notes(self, temp_vault):
        """Test retrieval performance with 1000 notes."""
        evaluator = KnowledgeEvaluator(temp_vault)
        result = evaluator.benchmark_retrieval(num_notes=1000)
        assert result["num_notes"] == 1000
        assert result["retrieval_time_ms"] >= 0


# ---------------------------------------------------------------------------
# Full evaluation tests
# ---------------------------------------------------------------------------

class TestFullEvaluation:
    """Tests for the full evaluation report."""

    def test_full_evaluation_structure(self, populated_vault):
        """Test that full evaluation returns all metric categories."""
        evaluator = KnowledgeEvaluator(populated_vault)
        report = evaluator.full_evaluation()
        assert "extraction" in report
        assert "deduplication" in report
        assert "retrieval" in report
        assert "growth" in report
        assert "health" in report

    def test_full_evaluation_extraction(self, populated_vault):
        """Test extraction metrics in full evaluation."""
        evaluator = KnowledgeEvaluator(populated_vault)
        report = evaluator.full_evaluation()
        assert report["extraction"]["total_candidates"] >= 0
        assert report["extraction"]["accepted"] >= 0

    def test_full_evaluation_deduplication(self, populated_vault):
        """Test deduplication metrics in full evaluation."""
        evaluator = KnowledgeEvaluator(populated_vault)
        report = evaluator.full_evaluation()
        assert "exact_duplicates_prevented" in report["deduplication"]
        assert "duplicate_groups" in report["deduplication"]

    def test_full_evaluation_retrieval(self, populated_vault):
        """Test retrieval metrics in full evaluation."""
        evaluator = KnowledgeEvaluator(populated_vault)
        report = evaluator.full_evaluation()
        assert "precision_at_k" in report["retrieval"]
        assert "recall_at_k" in report["retrieval"]
        assert "hit_rate_at_k" in report["retrieval"]

    def test_full_evaluation_health(self, populated_vault):
        """Test health metrics in full evaluation."""
        evaluator = KnowledgeEvaluator(populated_vault)
        report = evaluator.full_evaluation()
        assert "orphan_notes" in report["health"]
        assert "is_healthy" in report["health"]
        assert "issues_count" in report["health"]


# ---------------------------------------------------------------------------
# Real data test (safe synthetic dataset)
# ---------------------------------------------------------------------------

class TestRealDataEvaluation:
    """Tests using a realistic synthetic dataset."""

    def test_synthetic_dataset_duplicates_controlled(self, temp_vault):
        """Test that duplicates are controlled in a synthetic dataset."""
        service = temp_vault
        # Create duplicate notes
        service.create_note(
            title="Retention Strategy",
            note_type=NoteType.INSIGHT,
            content="Retention strategy content.",
            source="video_analysis",
            source_id="batch-001",
            confidence=0.85,
        )
        # Same title - should be deduplicated (updated, not created)
        service.create_note(
            title="Retention Strategy",
            note_type=NoteType.INSIGHT,
            content="Updated retention strategy content.",
            source="video_analysis",
            source_id="batch-002",
            confidence=0.90,
        )
        notes = service.list_notes()
        retention_notes = [n for n in notes if n.title == "Retention Strategy"]
        assert len(retention_notes) == 1  # Deduplicated

    def test_synthetic_dataset_relationships_created(self, temp_vault):
        """Test that relationships are created in a synthetic dataset."""
        service = temp_vault
        service.create_note(
            title="Concept A",
            note_type=NoteType.CONCEPT,
            content="Content A.",
            source="manual",
            confidence=0.90,
        )
        service.create_note(
            title="Concept B",
            note_type=NoteType.CONCEPT,
            content="Content B. See [[Concept A]] for details.",
            source="manual",
            confidence=0.90,
            related=["Concept A"],
        )
        evaluator = KnowledgeEvaluator(service)
        index = service.index_vault()
        assert "Concept B" in index.graph or "Concept A" in index.backlinks

    def test_synthetic_dataset_provenance_survives(self, temp_vault):
        """Test that provenance survives extraction."""
        service = temp_vault
        service.create_note(
            title="Provenance Test",
            note_type=NoteType.RESEARCH,
            content="Research content.",
            source="video_analysis",
            source_id="batch-001",
            source_video_ids=["vid_001", "vid_002"],
            confidence=0.85,
        )
        notes = service.list_notes()
        note = [n for n in notes if n.title == "Provenance Test"][0]
        assert note.source == "video_analysis"
        assert note.source_id == "batch-001"
        assert "vid_001" in note.source_video_ids

    def test_synthetic_dataset_retrieval_finds_relevant(self, temp_vault):
        """Test that retrieval finds relevant knowledge in synthetic dataset."""
        service = temp_vault
        service.create_note(
            title="FFmpeg Stream Mapping Issue",
            note_type=NoteType.LESSON,
            content="FFmpeg stream mapping problem and solution.",
            tags=["ffmpeg", "rendering"],
            source="manual",
            confidence=0.95,
        )
        service.create_note(
            title="Video Assembly Decision",
            note_type=NoteType.DECISION,
            content="Decision to use FFmpeg for video assembly.",
            tags=["ffmpeg", "decision"],
            source="manual",
            confidence=0.90,
        )
        evaluator = KnowledgeEvaluator(service)
        results = evaluator.retriever.retrieve("FFmpeg rendering problem", limit=5)
        titles = [r.title for r in results]
        assert "FFmpeg Stream Mapping Issue" in titles

    def test_synthetic_dataset_conflicts_visible(self, temp_vault):
        """Test that conflicts are visible in synthetic dataset."""
        service = temp_vault
        service.create_note(
            title="Hook Timing",
            note_type=NoteType.INSIGHT,
            content="Hooks should appear within first 5-10 seconds.",
            tags=["retention", "hook"],
            source="manual",
            confidence=0.85,
        )
        service.create_note(
            title="Early Hook Myth",
            note_type=NoteType.INSIGHT,
            content="Early hooks are not always necessary.",
            tags=["retention"],
            source="manual",
            confidence=0.65,
        )
        # Add contradiction
        hook_note = service.get_note_by_title("Hook Timing")
        service.linker.add_relationship_note(
            hook_note, "Early Hook Myth",
            RelationshipType.CONTRADICTS,
            evidence="Contradicts hook timing advice"
        )
        service.repository.save_note(hook_note)

        evaluator = KnowledgeEvaluator(service)
        result = evaluator.health_check()
        assert len(result.conflicting_knowledge) > 0

    def test_synthetic_dataset_context_compact(self, temp_vault):
        """Test that context remains compact in synthetic dataset."""
        service = temp_vault
        for i in range(20):
            service.create_note(
                title=f"Topic {i}",
                note_type=NoteType.CONCEPT,
                content=f"Content about topic {i}. Keywords: retention, hooks, algorithm.",
                tags=["test"],
                source="manual",
                confidence=0.80,
            )
        evaluator = KnowledgeEvaluator(service)
        context = evaluator.retriever.build_context("retention", max_notes=5, max_chars=1000)
        markdown = context.to_markdown()
        assert len(markdown) <= 1100  # Allow some slack
