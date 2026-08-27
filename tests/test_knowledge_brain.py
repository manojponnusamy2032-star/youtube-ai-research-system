"""Tests for the Knowledge Brain (Obsidian vault) subsystem."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.knowledge.config import KnowledgeConfig
from src.knowledge.indexer import Indexer
from src.knowledge.knowledge_service import KnowledgeService
from src.knowledge.linker import Linker
from src.knowledge.models import KnowledgeNote, NoteType, slugify
from src.knowledge.repository import KnowledgeRepository
from src.knowledge.search import KnowledgeSearch


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


# ============================================================================
# Vault Creation
# ============================================================================

class TestVaultCreation:
    """Test vault directory creation."""

    def test_vault_created(self, config: KnowledgeConfig):
        """Test that vault directories are created."""
        config.ensure_vault()
        assert config.vault_path.exists()
        for folder in KnowledgeConfig.VAULT_FOLDERS:
            assert (config.vault_path / folder).exists()

    def test_vault_created_on_service_init(self, config: KnowledgeConfig):
        """Test that vault is created when service initializes."""
        service = KnowledgeService(config)
        assert config.vault_path.exists()
        assert (config.vault_path / "02_Knowledge").exists()

    def test_path_traversal_prevention(self, config: KnowledgeConfig):
        """Test that path traversal is prevented."""
        with pytest.raises(ValueError):
            config.resolve_path("../outside")


# ============================================================================
# Note Creation
# ============================================================================

class TestNoteCreation:
    """Test knowledge note creation."""

    def test_create_concept_note(self, service: KnowledgeService):
        """Test creating a concept note."""
        note = service.create_note(
            title="Retrieval Augmented Generation",
            note_type=NoteType.CONCEPT,
            content="RAG combines retrieval with generation.",
            tags=["ai", "llm"],
        )
        assert note.id
        assert note.type == NoteType.CONCEPT
        assert note.title == "Retrieval Augmented Generation"
        assert note.slug == "retrieval-augmented-generation"
        assert note.folder == "02_Knowledge"

    def test_create_note_with_string_type(self, service: KnowledgeService):
        """Test creating a note with string type."""
        note = service.create_note(
            title="Test Project",
            note_type="project",
            content="Project content",
        )
        assert note.type == NoteType.PROJECT
        assert note.folder == "01_Projects"

    def test_create_note_idempotent(self, service: KnowledgeService):
        """Test that creating the same note twice doesn't duplicate."""
        note1 = service.create_note(
            title="Same Title",
            note_type=NoteType.CONCEPT,
            content="Content 1",
        )
        note2 = service.create_note(
            title="Same Title",
            note_type=NoteType.CONCEPT,
            content="Content 2",
        )
        assert note1.id == note2.id
        assert note2.content == "Content 2"
        assert len(service.list_notes()) == 1

    def test_create_note_with_related(self, service: KnowledgeService):
        """Test creating a note with related links."""
        note = service.create_note(
            title="Vector Databases",
            note_type=NoteType.CONCEPT,
            content="Vector DBs store embeddings.",
            related=["Embeddings", "RAG"],
        )
        assert "Embeddings" in note.related
        assert "RAG" in note.related


# ============================================================================
# Note Update / Delete
# ============================================================================

class TestNoteUpdateDelete:
    """Test note update and deletion."""

    def test_update_note(self, service: KnowledgeService):
        """Test updating a note."""
        note = service.create_note(
            title="Original Title",
            note_type=NoteType.CONCEPT,
            content="Original content",
        )
        updated = service.update_note(note.id, content="Updated content")
        assert updated is not None
        assert updated.content == "Updated content"
        assert updated.updated_at != note.updated_at

    def test_update_nonexistent_note(self, service: KnowledgeService):
        """Test updating a non-existent note."""
        result = service.update_note("nonexistent", content="test")
        assert result is None

    def test_delete_note(self, service: KnowledgeService):
        """Test deleting a note."""
        note = service.create_note(
            title="To Delete",
            note_type=NoteType.CONCEPT,
            content="Delete me",
        )
        assert service.delete_note(note.id) is True
        assert service.get_note(note.id) is None

    def test_delete_nonexistent_note(self, service: KnowledgeService):
        """Test deleting a non-existent note."""
        assert service.delete_note("nonexistent") is False

    def test_get_note_by_title(self, service: KnowledgeService):
        """Test getting a note by title."""
        service.create_note(
            title="Unique Title",
            note_type=NoteType.CONCEPT,
            content="Content",
        )
        note = service.get_note_by_title("Unique Title")
        assert note is not None
        assert note.title == "Unique Title"


# ============================================================================
# YAML Frontmatter & Markdown
# ============================================================================

class TestMarkdownFormat:
    """Test YAML frontmatter and Markdown validity."""

    def test_frontmatter_generated(self, service: KnowledgeService):
        """Test that notes have valid YAML frontmatter."""
        note = service.create_note(
            title="Frontmatter Test",
            note_type=NoteType.CONCEPT,
            content="Body content",
            tags=["test"],
        )
        markdown = note.to_markdown()
        assert markdown.startswith("---")
        assert "id:" in markdown
        assert "type: concept" in markdown
        assert "title: Frontmatter Test" in markdown
        assert "tags:" in markdown
        assert "  - test" in markdown
        assert "---" in markdown

    def test_markdown_roundtrip(self, service: KnowledgeService):
        """Test that notes can be read back from disk."""
        note = service.create_note(
            title="Roundtrip Test",
            note_type=NoteType.INSIGHT,
            content="Roundtrip content",
            tags=["test"],
        )
        loaded = service.get_note(note.id)
        assert loaded is not None
        assert loaded.title == note.title
        assert loaded.content == note.content
        assert loaded.type == note.type
        assert loaded.tags == note.tags

    def test_markdown_file_exists(self, service: KnowledgeService, config: KnowledgeConfig):
        """Test that the markdown file is written to disk."""
        note = service.create_note(
            title="File Exists Test",
            note_type=NoteType.CONCEPT,
            content="Content",
        )
        file_path = config.folder_for(note.folder) / note.filename
        assert file_path.exists()
        content = file_path.read_text(encoding="utf-8")
        assert "# File Exists Test" in content


# ============================================================================
# Wikilinks & Backlinks
# ============================================================================

class TestWikilinks:
    """Test wikilink extraction and management."""

    def test_extract_wikilinks(self):
        """Test extracting wikilinks from content."""
        linker = Linker()
        note = KnowledgeNote(
            id="test-1",
            type=NoteType.CONCEPT,
            title="Test",
            content="See [[Embeddings]] and [[Vector Databases]] for more.",
            related=["RAG"],
        )
        links = linker.extract_wikilinks(note)
        assert "Embeddings" in links
        assert "Vector Databases" in links
        assert "RAG" in links

    def test_add_related(self):
        """Test adding related notes."""
        linker = Linker()
        note = KnowledgeNote(
            id="test-1",
            type=NoteType.CONCEPT,
            title="Test",
            content="",
            related=["Existing"],
        )
        linker.add_related(note, ["New", "Existing"])
        assert "New" in note.related
        assert note.related.count("Existing") == 1

    def test_remove_related(self):
        """Test removing related notes."""
        linker = Linker()
        note = KnowledgeNote(
            id="test-1",
            type=NoteType.CONCEPT,
            title="Test",
            content="",
            related=["A", "B", "C"],
        )
        linker.remove_related(note, ["B"])
        assert note.related == ["A", "C"]


# ============================================================================
# Search
# ============================================================================

class TestSearch:
    """Test knowledge search."""

    def test_title_search(self, service: KnowledgeService):
        """Test searching by title."""
        service.create_note(
            title="Python Programming",
            note_type=NoteType.CONCEPT,
            content="Python is a language.",
        )
        results = service.search_notes("Python")
        assert len(results) == 1
        assert results[0].title == "Python Programming"

    def test_content_search(self, service: KnowledgeService):
        """Test searching by content."""
        service.create_note(
            title="Test Note",
            note_type=NoteType.CONCEPT,
            content="This contains unique_keyword_xyz.",
        )
        results = service.search_notes("unique_keyword_xyz")
        assert len(results) == 1

    def test_tag_filter(self, service: KnowledgeService):
        """Test filtering by tag."""
        service.create_note(
            title="Tagged Note",
            note_type=NoteType.CONCEPT,
            content="Content",
            tags=["special-tag"],
        )
        service.create_note(
            title="Untagged Note",
            note_type=NoteType.CONCEPT,
            content="Content",
        )
        results = service.search_notes(tag="special-tag")
        assert len(results) == 1
        assert results[0].title == "Tagged Note"

    def test_type_filter(self, service: KnowledgeService):
        """Test filtering by note type."""
        service.create_note(
            title="Concept Note",
            note_type=NoteType.CONCEPT,
            content="Content",
        )
        service.create_note(
            title="Project Note",
            note_type=NoteType.PROJECT,
            content="Content",
        )
        results = service.search_notes(note_type=NoteType.PROJECT)
        assert len(results) == 1
        assert results[0].title == "Project Note"

    def test_project_filter(self, service: KnowledgeService):
        """Test filtering by project."""
        service.create_note(
            title="Project A Note",
            note_type=NoteType.INSIGHT,
            content="Content",
            project="Project A",
        )
        service.create_note(
            title="Project B Note",
            note_type=NoteType.INSIGHT,
            content="Content",
            project="Project B",
        )
        results = service.search_notes(project="Project A")
        assert len(results) == 1
        assert results[0].title == "Project A Note"


# ============================================================================
# Indexing
# ============================================================================

class TestIndexing:
    """Test vault indexing."""

    def test_index_vault(self, service: KnowledgeService):
        """Test building a vault index."""
        service.create_note(
            title="Concept A",
            note_type=NoteType.CONCEPT,
            content="Content",
            tags=["ai"],
        )
        service.create_note(
            title="Concept B",
            note_type=NoteType.CONCEPT,
            content="Content",
            tags=["ai", "ml"],
            related=["Concept A"],
        )
        index = service.index_vault()
        assert len(index.notes) == 2
        assert index.note_types["concept"] == 2
        assert index.tags["ai"] == 2
        assert index.tags["ml"] == 1
        assert "Concept A" in index.wikilinks.get("Concept B", [])
        assert "Concept B" in index.backlinks.get("Concept A", [])

    def test_orphan_notes(self, service: KnowledgeService):
        """Test orphan note detection."""
        service.create_note(
            title="Linked Note",
            note_type=NoteType.CONCEPT,
            content="Content",
        )
        service.create_note(
            title="Orphan Note",
            note_type=NoteType.CONCEPT,
            content="Content",
        )
        index = service.index_vault()
        assert "Orphan Note" in index.orphan_notes


# ============================================================================
# Specialized Capture Methods
# ============================================================================

class TestCaptureMethods:
    """Test specialized capture methods."""

    def test_capture_insight(self, service: KnowledgeService):
        """Test capturing an insight."""
        note = service.capture_insight(
            title="Viral Hook Insight",
            content="Hooks under 3 seconds perform best.",
            confidence=0.85,
        )
        assert note.type == NoteType.INSIGHT
        assert note.confidence == 0.85
        assert "insight" in note.tags

    def test_capture_decision(self, service: KnowledgeService):
        """Test capturing a decision."""
        note = service.capture_decision(
            title="Use FFmpeg for Video Assembly",
            context="Need to assemble video clips.",
            decision="Use FFmpeg with stream mapping.",
            reason="FFmpeg is reliable and free.",
            alternatives=["MoviePy", "OpenCV"],
            consequences=["Faster rendering", "More control"],
        )
        assert note.type == NoteType.DECISION
        assert note.status == "accepted"
        assert "## Context" in note.content
        assert "## Decision" in note.content
        assert "## Reason" in note.content
        assert "MoviePy" in note.content
        assert "Faster rendering" in note.content

    def test_capture_lesson(self, service: KnowledgeService):
        """Test capturing a lesson."""
        note = service.capture_lesson(
            title="FFmpeg Stream Mapping Issue",
            problem="Audio was missing from output.",
            root_cause="Incorrect stream mapping.",
            solution="Use -map 0:a explicitly.",
            prevention="Always verify stream mapping.",
        )
        assert note.type == NoteType.LESSON
        assert "## Problem" in note.content
        assert "## Root Cause" in note.content
        assert "## Solution" in note.content
        assert "## Prevention" in note.content

    def test_capture_research(self, service: KnowledgeService):
        """Test capturing research."""
        note = service.capture_research(
            title="YouTube Algorithm Research",
            topic="How the algorithm recommends videos",
            findings="Watch time is the primary ranking signal.",
            source="youtube-research",
            confidence=0.9,
        )
        assert note.type == NoteType.RESEARCH
        assert note.source == "youtube-research"
        assert "## Topic" in note.content
        assert "## Findings" in note.content

    def test_capture_project(self, service: KnowledgeService):
        """Test capturing a project."""
        note = service.capture_project(
            title="YouTube AI Research System",
            purpose="Automate YouTube content research.",
            status="active",
            architecture="FastAPI + SQLite + Agents",
            decisions=["Use FFmpeg for Video Assembly"],
            related_concepts=["RAG"],
            next_steps=["Add more agents"],
        )
        assert note.type == NoteType.PROJECT
        assert note.status == "active"
        assert "## Purpose" in note.content
        assert "## Architecture" in note.content
        assert "[[Use FFmpeg for Video Assembly]]" in note.content
        assert "[[RAG]]" in note.content


# ============================================================================
# Filename Sanitization
# ============================================================================

class TestFilenameSanitization:
    """Test filename sanitization."""

    def test_slugify_basic(self):
        """Test basic slugification."""
        assert slugify("Hello World") == "hello-world"
        assert slugify("Hello, World!") == "hello-world"
        assert slugify("  Multiple   Spaces  ") == "multiple-spaces"
        assert slugify("UPPER CASE") == "upper-case"

    def test_slugify_special_chars(self):
        """Test slugification with special characters."""
        assert slugify("C++ Programming") == "c-programming"
        assert slugify("Python 3.12") == "python-312"
        assert slugify("") == "untitled"

    def test_safe_filename(self, service: KnowledgeService, config: KnowledgeConfig):
        """Test that notes with special chars get safe filenames."""
        note = service.create_note(
            title="C++ & Python: Advanced!",
            note_type=NoteType.CONCEPT,
            content="Content",
        )
        file_path = config.folder_for(note.folder) / note.filename
        assert file_path.exists()
        assert ".." not in note.filename


# ============================================================================
# Existing System Compatibility
# ============================================================================

class TestExistingSystemCompatibility:
    """Test that the knowledge subsystem doesn't break existing systems."""

    def test_knowledge_base_agent_still_works(self):
        """Test that KnowledgeBaseAgent can be instantiated without obsidian service."""
        from unittest.mock import Mock
        from src.agents.knowledge_base_agent import KnowledgeBaseAgent

        db = Mock()
        ks = Mock()
        agent = KnowledgeBaseAgent(db, ks)
        assert agent.obsidian_knowledge_service is None

    def test_knowledge_base_agent_with_obsidian(self, service: KnowledgeService):
        """Test that KnowledgeBaseAgent works with obsidian service."""
        from unittest.mock import Mock
        from src.agents.knowledge_base_agent import KnowledgeBaseAgent

        db = Mock()
        ks = Mock()
        agent = KnowledgeBaseAgent(db, ks, obsidian_knowledge_service=service)
        assert agent.obsidian_knowledge_service is not None


# ============================================================================
# Deduplication & Extraction & Advanced Brain Capabilities
# ============================================================================

class TestDeduplicationAndExtraction:
    """Test the deduplication, extractor, and linking modules."""

    def test_deduplicator_exact_title(self, service: KnowledgeService):
        """Test exact title match deduplication."""
        from src.knowledge.deduplicator import Deduplicator
        from src.knowledge.models import KnowledgeNote, NoteType
        
        note1 = service.create_note(title="FastAPI Routing", note_type="concept", content="Basic routing")
        dedup = Deduplicator(service.repository)
        
        candidate = KnowledgeNote(id="", type=NoteType.CONCEPT, title="FastAPI Routing", content="")
        match = dedup.find_match(candidate)
        assert match is not None
        assert match.id == note1.id

    def test_deduplicator_alias_match(self, service: KnowledgeService):
        """Test alias match deduplication."""
        from src.knowledge.deduplicator import Deduplicator
        from src.knowledge.models import KnowledgeNote, NoteType
        
        note = service.create_note(title="FastAPI", note_type="concept", content="Framework", tags=["api"])
        service.update_note(note.id, aliases=["Fast API", "fastapi-framework"])

        dedup = Deduplicator(service.repository)
        candidate = KnowledgeNote(id="", type=NoteType.CONCEPT, title="Fast API", content="")
        match = dedup.find_match(candidate)
        assert match is not None
        assert match.id == note.id

    def test_deduplicator_similarity_match(self, service: KnowledgeService):
        """Test similarity/ratio deduplication."""
        from src.knowledge.deduplicator import Deduplicator
        from src.knowledge.models import KnowledgeNote, NoteType
        
        note = service.create_note(title="LLM Fine-Tuning Techniques", note_type="concept", content="Fine tuning models")
        dedup = Deduplicator(service.repository)
        
        # Test 95%+ match
        candidate = KnowledgeNote(id="", type=NoteType.CONCEPT, title="LLM Fine-Tuning Technique", content="")
        match = dedup.find_match(candidate)
        assert match is not None
        assert match.id == note.id

    def test_knowledge_extractor(self, service: KnowledgeService):
        """Test batch extraction from analysis results using top-level properties."""
        from src.knowledge.extractor import KnowledgeExtractor
        from src.knowledge.deduplicator import Deduplicator

        analyses = [
            {
                "video_id": "vid123",
                "main_topic": "Thumbnails Visual Weight",
                "hook_type": "Curiosity Gap",
                "story_structure": "Three Act Structure",
            }
        ]

        dedup = Deduplicator(service.repository)
        extractor = KnowledgeExtractor(service, dedup)
        
        # Ensure project exists
        service.create_note(title="Thumbnail Optimizations", note_type="project", content="Optimizing thumbnails")

        summary = extractor.extract_from_analysis_batch(analyses, project="Thumbnail Optimizations")

        assert summary["created"] >= 2
        
        # Verify note properties
        note = service.get_note_by_title("Thumbnails Visual Weight")
        assert note is not None
        assert note.project == "Thumbnail Optimizations"
        assert "vid123" in note.source_video_ids

    def test_advanced_linking_relationship_types(self, service: KnowledgeService):
        """Test linking with explicit relationship types."""
        note_a = service.create_note(title="FFmpeg Video Processing", note_type="concept", content="Video processing")
        note_b = service.create_note(title="GPU Acceleration", note_type="concept", content="GPU processing acceleration")

        service.linker.add_relationship_note(note_b, note_a.title, rel_type="supports")
        service.repository.save_note(note_b)
        
        reloaded = service.get_note(note_b.id)
        assert reloaded is not None
        assert "supports" in reloaded.content
        assert "FFmpeg Video Processing" in reloaded.related

    def test_indexer_graph_serialization(self, service: KnowledgeService):
        """Test index graph serialization."""
        note_a = service.create_note(title="A", note_type="concept", content="A content")
        note_b = service.create_note(title="B", note_type="concept", content="B content")
        
        service.linker.add_relationship_note(note_a, note_b.title, rel_type="depends_on")
        service.repository.save_note(note_a)

        idx = service.index_vault()
        assert note_a.id in idx.graph
        relations = idx.graph[note_a.id]
        assert len(relations) == 1
        assert relations[0]["target"] == note_b.title
        assert relations[0]["type"] == "depends_on"
