"""Tests for the Knowledge Retrieval layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.knowledge.config import KnowledgeConfig
from src.knowledge.knowledge_service import KnowledgeService
from src.knowledge.models import NoteType
from src.knowledge.retriever import KnowledgeRetriever, KnowledgeContext


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    """Create a temporary vault directory."""
    return tmp_path / "vault"


@pytest.fixture
def config(vault_path: Path) -> KnowledgeConfig:
    """Create a KnowledgeConfig pointing to the temp vault."""
    return KnowledgeConfig(vault_path)


@pytest.fixture
def service(config: KnowledgeConfig) -> KnowledgeService:
    """Create a KnowledgeService with the temp vault."""
    return KnowledgeService(config)


@pytest.fixture
def retriever(service: KnowledgeService) -> KnowledgeRetriever:
    """Create a KnowledgeRetriever with the temp vault."""
    return KnowledgeRetriever(service.repository)


@pytest.fixture
def populated_service(service: KnowledgeService) -> KnowledgeService:
    """Create a service populated with diverse notes for retrieval tests."""
    # Concept notes
    service.create_note(
        title="YouTube Retention Research",
        note_type=NoteType.RESEARCH,
        content="Watch time is the primary ranking signal. Retention over 50% correlates with viral reach.",
        tags=["retention", "algorithm", "research"],
        confidence=0.92,
        source="youtube-research",
        source_video_ids=["vid1", "vid2"],
        project="YouTube AI Research System",
    )
    service.create_note(
        title="Curiosity Gap",
        note_type=NoteType.CONCEPT,
        content="Curiosity gaps create information asymmetry that drives clicks and retention.",
        tags=["hook", "psychology"],
        confidence=0.85,
        source="youtube-research",
        project="YouTube AI Research System",
    )
    service.create_note(
        title="Hook Timing",
        note_type=NoteType.INSIGHT,
        content="Hooks under 3 seconds perform best. The first 3 seconds decide if viewers stay.",
        tags=["hook", "retention"],
        confidence=0.78,
        project="YouTube AI Research System",
    )
    # Project note
    service.create_note(
        title="YouTube AI Research System",
        note_type=NoteType.PROJECT,
        content="Automated YouTube content research with AI agents.",
        tags=["project"],
        status="active",
    )
    # Lesson note
    service.create_note(
        title="Failed Hook Experiment",
        note_type=NoteType.LESSON,
        content="Using 10-second intros killed retention. Solution: cut to value immediately.",
        tags=["hook", "lesson"],
        confidence=0.72,
        project="YouTube AI Research System",
    )
    # Decision note
    service.create_note(
        title="Use FFmpeg for Video Assembly",
        note_type=NoteType.DECISION,
        content="FFmpeg selected over MoviePy for reliability.",
        tags=["infrastructure"],
        status="accepted",
        project="YouTube AI Research System",
    )
    # Unrelated note
    service.create_note(
        title="Cooking Pasta",
        note_type=NoteType.CONCEPT,
        content="Boil water, add salt, cook pasta for 8-10 minutes.",
        tags=["cooking"],
        confidence=0.5,
    )
    return service


# ============================================================================
# Basic Retrieval
# ============================================================================


class TestBasicRetrieval:
    """Test basic retrieval operations."""

    def test_exact_title_retrieval(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test exact title match retrieval."""
        results = retriever.retrieve("YouTube Retention Research")
        assert len(results) >= 1
        assert results[0].title == "YouTube Retention Research"
        assert "exact_title" in results[0].match_reasons

    def test_partial_title_retrieval(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test partial title token match retrieval."""
        results = retriever.retrieve("Retention Research")
        assert len(results) >= 1
        assert results[0].title == "YouTube Retention Research"

    def test_content_retrieval(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test content-based retrieval."""
        results = retriever.retrieve("primary ranking signal")
        assert len(results) >= 1
        assert results[0].title == "YouTube Retention Research"

    def test_tag_retrieval(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test tag-based retrieval."""
        results = retriever.retrieve("hook psychology")
        assert len(results) >= 2
        titles = [r.title for r in results]
        # Both notes match via tags - Curiosity Gap matches "psychology" tag,
        # Hook Timing matches "hook" tag. Both should be recovered.
        assert "Curiosity Gap" in titles
        assert "Hook Timing" in titles

    def test_type_filter(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test filtering by note type."""
        results = retriever.retrieve(note_type=NoteType.LESSON)
        assert len(results) == 1
        assert results[0].title == "Failed Hook Experiment"

    def test_project_filter(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test filtering by project."""
        results = retriever.retrieve(project="YouTube AI Research System")
        assert len(results) >= 5  # Most notes are in this project

    def test_empty_query(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test retrieval with no query returns all notes."""
        results = retriever.retrieve(limit=10)
        assert len(results) >= 1

    def test_no_result_query(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test retrieval with no matching notes."""
        results = retriever.retrieve("nonexistent_xyz_123_nothing")
        assert len(results) == 0

    def test_limit(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test limit is respected."""
        results = retriever.retrieve("YouTube", limit=2)
        assert len(results) <= 2


# ============================================================================
# Confidence & Ranking
# ============================================================================


class TestConfidenceRanking:
    """Test confidence-aware ranking."""

    def test_high_confidence_ranks_higher(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test that high confidence notes rank above low confidence when scores are similar."""
        # Create two similar notes with different confidence
        populated_service.create_note(
            title="Retention Tips Guide",
            note_type=NoteType.CONCEPT,
            content="Retention tips for YouTube videos.",
            confidence=0.95,
            source="youtube-research",
        )
        populated_service.create_note(
            title="Retention Tips Unverified",
            note_type=NoteType.CONCEPT,
            content="Retention tips for YouTube videos without sources.",
            confidence=0.4,
        )
        results = retriever.retrieve("Retention Tips")
        assert len(results) >= 2
        # High confidence + source should rank first
        assert results[0].confidence >= 0.90

    def test_min_confidence_filter(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test minimum confidence filtering."""
        results = retriever.retrieve(min_confidence=0.9)
        assert all(r.confidence is None or r.confidence >= 0.9 for r in results)

    def test_source_traceability(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test that results preserve source provenance."""
        results = retriever.retrieve("Retention Research")
        item = results[0]
        assert item.note_id
        assert item.title
        assert item.note_type == NoteType.RESEARCH
        assert item.confidence == 0.92
        assert item.source == "youtube-research"
        assert "vid1" in item.source_video_ids
        assert item.project == "YouTube AI Research System"


# ============================================================================
# Graph Expansion & Related Notes
# ============================================================================


class TestGraphExpansion:
    """Test graph expansion and related note retrieval."""

    def test_related_notes(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test retrieving related notes."""
        # Link Hook Timing to Curiosity Gap
        populated_service.link_notes("Hook Timing", ["Curiosity Gap"])
        
        hook_note = populated_service.get_note_by_title("Hook Timing")
        related = retriever.retrieve_related(hook_note.id)
        assert len(related) >= 1
        assert any(r.title == "Curiosity Gap" for r in related)

    def test_backlinks(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test retrieving backlinks."""
        # Make Hook Timing link to Curiosity Gap
        populated_service.link_notes("Hook Timing", ["Curiosity Gap"])
        
        curiosity_note = populated_service.get_note_by_title("Curiosity Gap")
        backlinks = retriever.retrieve_backlinks(curiosity_note.id)
        assert len(backlinks) >= 1
        assert any(r.title == "Hook Timing" for r in backlinks)

    def test_graph_expansion(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test that graph expansion adds related notes."""
        # Link concepts together
        populated_service.link_notes("Hook Timing", ["Curiosity Gap", "YouTube Retention Research"])
        
        results = retriever.retrieve("Hook Timing", limit=5, expand_graph=True)
        titles = [r.title for r in results]
        assert "Hook Timing" in titles
        # Related notes should be included via graph expansion
        assert any(r.expanded_from is not None for r in results)

    def test_graph_expansion_limited(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test that graph expansion is limited."""
        # Create many links
        for i in range(20):
            populated_service.create_note(
                title=f"Related Note {i}",
                note_type=NoteType.CONCEPT,
                content="Links to main",
                related=["YouTube Retention Research"],
            )
        
        results = retriever.retrieve("YouTube Retention Research", limit=3, expand_graph=True)
        # Should not explode - max expansion is 5 additional notes
        assert len(results) <= 8


# ============================================================================
# Context Builder
# ============================================================================


class TestContextBuilder:
    """Test the context builder."""

    def test_build_context(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test building a context bundle."""
        context = retriever.build_context("How should I improve YouTube retention?", max_notes=5)
        assert isinstance(context, KnowledgeContext)
        assert context.query == "How should I improve YouTube retention?"
        assert len(context.relevant_knowledge) >= 1

    def test_context_categorization(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test that context categorizes knowledge by type."""
        context = retriever.build_context("YouTube retention hooks", max_notes=10)
        assert context.relevant_knowledge
        # Should categorize research as evidence
        assert any(r.note_type == NoteType.RESEARCH for r in context.evidence)
        # Should categorize lessons
        assert any(r.note_type == NoteType.LESSON for r in context.lessons)

    def test_context_markdown(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test that context can be rendered as Markdown."""
        context = retriever.build_context("retention")
        markdown = context.to_markdown()
        assert "## Knowledge Context" in markdown
        assert markdown.strip()

    def test_context_size_limit(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test context size limits."""
        # Create many notes
        for i in range(15):
            populated_service.create_note(
                title=f"Hook Pattern {i}",
                note_type=NoteType.INSIGHT,
                content=f"Retention technique {i} for YouTube videos that keeps viewers watching.",
                confidence=0.8,
            )
        context = retriever.build_context("retention", max_notes=20, max_chars=1000)
        rendered = context.to_markdown()
        assert len(rendered) <= 5000  # Generous bound for truncation

    def test_projected_context(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test building context scoped to a project."""
        context = retriever.build_context("retention", project="YouTube AI Research System")
        assert context.relevant_knowledge
        # Project-scoped results should all be in that project
        for item in context.relevant_knowledge:
            if item.project:
                assert item.project == "YouTube AI Research System"


# ============================================================================
# Conflict Detection
# ============================================================================


class TestConflictDetection:
    """Test conflict detection in retrieval."""

    def test_conflict_detection(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test detection of contradicting notes."""
        # Create two conflicting notes
        note_a = populated_service.create_note(
            title="Hooks Must Be Under 3 Seconds",
            note_type=NoteType.INSIGHT,
            content="Research shows hooks under 3 seconds always perform best.",
            confidence=0.85,
            tags=["hook"],
        )
        note_b = populated_service.create_note(
            title="Long Hooks Can Work",
            note_type=NoteType.INSIGHT,
            content="Some highly successful videos use 10+ second hooks when context requires it.",
            confidence=0.76,
            tags=["hook"],
        )
        
        # Add contradicts relationship
        populated_service.linker.add_relationship_note(
            note_a, note_b.title, rel_type="contradicts"
        )
        populated_service.repository.save_note(note_a)
        
        # Build context that retrieves both
        context = retriever.build_context("hook timing", max_notes=10, detect_conflicts=True)
        assert len(context.conflicts) >= 1
        conflict = context.conflicts[0]
        assert conflict["source_title"] == "Hooks Must Be Under 3 Seconds"
        assert conflict["target_title"] == "Long Hooks Can Work"
        assert conflict["relationship"] == "contradicts"


# ============================================================================
# Retrieval by Type / Tags / Project
# ============================================================================


class TestSpecializedRetrieval:
    """Test specialized retrieval methods."""

    def test_retrieve_by_tags(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test retrieving by tags."""
        results = retriever.retrieve_by_tags(["hook"])
        assert len(results) >= 3
        titles = [r.title for r in results]
        assert "Curiosity Gap" in titles
        assert "Hook Timing" in titles

    def test_retrieve_project(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test retrieving project knowledge."""
        results = retriever.retrieve_project("YouTube AI Research System")
        assert len(results) >= 5

    def test_retrieve_by_type(self, retriever: KnowledgeRetriever, populated_service: KnowledgeService):
        """Test retrieving by type."""
        results = retriever.retrieve_by_type(NoteType.DECISION)
        assert len(results) == 1
        assert results[0].title == "Use FFmpeg for Video Assembly"