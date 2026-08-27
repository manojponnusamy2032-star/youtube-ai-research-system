"""Knowledge Brain API routes for Obsidian vault management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any

from src.api.auth import require_api_key
from src.api.dependencies import get_knowledge_retriever, get_obsidian_knowledge_service
from src.knowledge.knowledge_service import KnowledgeService
from src.knowledge.models import NoteType
from src.knowledge.extractor import KnowledgeExtractor
from src.knowledge.deduplicator import Deduplicator
from src.knowledge.retriever import KnowledgeRetriever
from src.knowledge.evaluation import KnowledgeEvaluator

router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge Brain"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/notes", summary="Create a knowledge note")
def create_note(
    title: str,
    note_type: str,
    content: str,
    tags: list[str] | None = None,
    source: str = "generated",
    status: str | None = None,
    confidence: float | None = None,
    project: str | None = None,
    related: list[str] | None = None,
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Create a new knowledge note in the Obsidian vault."""
    try:
        note = knowledge_service.create_note(
            title=title,
            note_type=note_type,
            content=content,
            tags=tags,
            source=source,
            status=status,
            confidence=confidence,
            project=project,
            related=related,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"note": note.to_dict()}


@router.get("/notes/{note_id}", summary="Get a knowledge note")
def get_note(
    note_id: str,
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Get a knowledge note by ID."""
    note = knowledge_service.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": note.to_dict()}


@router.put("/notes/{note_id}", summary="Update a knowledge note")
def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    confidence: float | None = None,
    project: str | None = None,
    related: list[str] | None = None,
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Update an existing knowledge note."""
    changes: dict[str, object] = {}
    if title is not None:
        changes["title"] = title
    if content is not None:
        changes["content"] = content
    if tags is not None:
        changes["tags"] = tags
    if status is not None:
        changes["status"] = status
    if confidence is not None:
        changes["confidence"] = confidence
    if project is not None:
        changes["project"] = project
    if related is not None:
        changes["related"] = related
    note = knowledge_service.update_note(note_id, **changes)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": note.to_dict()}


@router.delete("/notes/{note_id}", summary="Delete a knowledge note")
def delete_note(
    note_id: str,
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Delete a knowledge note by ID."""
    deleted = knowledge_service.delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": True, "note_id": note_id}


@router.get("/search", summary="Search knowledge notes")
def search_notes(
    query: str | None = Query(default=None, description="Free-text search"),
    note_type: str | None = Query(default=None, description="Filter by note type"),
    tag: str | None = Query(default=None, description="Filter by tag"),
    project: str | None = Query(default=None, description="Filter by project"),
    limit: int = Query(default=20, ge=1, le=100),
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Search notes with optional filters."""
    try:
        results = knowledge_service.search_notes(
            query,
            note_type=note_type,
            tag=tag,
            project=project,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(results), "results": [r.to_dict() for r in results]}


@router.post("/index", summary="Index the vault")
def index_vault(
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Build and return a complete index of the vault."""
    index = knowledge_service.index_vault()
    return {"index": index.to_dict()}


@router.post("/insights", summary="Capture an insight")
def capture_insight(
    title: str,
    content: str,
    tags: list[str] | None = None,
    confidence: float | None = None,
    project: str | None = None,
    related: list[str] | None = None,
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Capture a reusable insight as a knowledge note."""
    note = knowledge_service.capture_insight(
        title=title,
        content=content,
        tags=tags,
        confidence=confidence,
        project=project,
        related=related,
    )
    return {"note": note.to_dict()}


@router.post("/decisions", summary="Capture a decision")
def capture_decision(
    title: str,
    context: str,
    decision: str,
    reason: str,
    alternatives: list[str] | None = None,
    consequences: list[str] | None = None,
    status: str = "accepted",
    tags: list[str] | None = None,
    project: str | None = None,
    related: list[str] | None = None,
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Capture an architecture/technical decision."""
    note = knowledge_service.capture_decision(
        title=title,
        context=context,
        decision=decision,
        reason=reason,
        alternatives=alternatives,
        consequences=consequences,
        status=status,
        tags=tags,
        project=project,
        related=related,
    )
    return {"note": note.to_dict()}


@router.post("/lessons", summary="Capture a lesson learned")
def capture_lesson(
    title: str,
    problem: str,
    root_cause: str,
    solution: str,
    prevention: str | None = None,
    tags: list[str] | None = None,
    project: str | None = None,
    related: list[str] | None = None,
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Capture a lesson learned as a knowledge note."""
    note = knowledge_service.capture_lesson(
        title=title,
        problem=problem,
        root_cause=root_cause,
        solution=solution,
        prevention=prevention,
        tags=tags,
        project=project,
        related=related,
    )
    return {"note": note.to_dict()}


@router.post("/extract", summary="Extract knowledge from analysis batch")
def extract_knowledge(
    analyses: list[dict[str, Any]],
    project: str | None = None,
    source_type: str = "research_analysis",
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Extract structured knowledge from a batch of analysis results.

    Processes structured analysis data from the research pipeline and identifies
    reusable knowledge entities (concepts, insights, patterns, lessons) with
    deduplication and provenance tracking.

    Args:
        analyses: List of analysis dicts from the research pipeline.
        project: Optional project name to associate notes with.
        source_type: Type label for provenance tracking.

    Returns:
        Summary dict with created, updated, skipped counts.
    """
    deduplicator = Deduplicator(knowledge_service.repository)
    extractor = KnowledgeExtractor(knowledge_service, deduplicator)
    result = extractor.extract_from_analysis_batch(
        analyses=analyses,
        project=project,
        source_type=source_type,
    )
    return {"result": result}


# ============================================================================
# Knowledge Retrieval Endpoints
# ============================================================================


@router.get("/retrieve", summary="Retrieve relevant knowledge")
def retrieve_knowledge(
    query: str | None = Query(default=None, description="Free-text query"),
    note_type: str | None = Query(default=None, description="Filter by note type"),
    tag: str | None = Query(default=None, description="Filter by tag"),
    project: str | None = Query(default=None, description="Filter by project"),
    limit: int = Query(default=10, ge=1, le=50),
    expand_graph: bool = Query(default=True, description="Expand through relationships"),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0, description="Minimum confidence"),
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> dict[str, object]:
    """Retrieve relevant knowledge notes with ranked scoring.

    Uses deterministic local retrieval with transparent scoring:
    - exact title match: +100
    - title token match: +40 per token
    - alias match: +25
    - tag match: +30
    - content match: +20
    - same project: +15
    - high confidence: +10
    - source available: +10
    """
    try:
        results = knowledge_retriever.retrieve(
            query,
            note_type=note_type,
            tag=tag,
            project=project,
            limit=limit,
            expand_graph=expand_graph,
            min_confidence=min_confidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(results), "results": [r.to_dict() for r in results]}


@router.get("/notes/{note_id}/related", summary="Get related notes")
def get_related_notes(
    note_id: str,
    limit: int = Query(default=5, ge=1, le=20),
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> dict[str, object]:
    """Retrieve notes related to a given note via wikilinks, backlinks, and relationships."""
    results = knowledge_retriever.retrieve_related(note_id, limit=limit)
    return {"count": len(results), "results": [r.to_dict() for r in results]}


@router.get("/notes/{note_id}/backlinks", summary="Get backlinks for a note")
def get_backlinks(
    note_id: str,
    limit: int = Query(default=5, ge=1, le=20),
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> dict[str, object]:
    """Retrieve notes that link to a given note."""
    results = knowledge_retriever.retrieve_backlinks(note_id, limit=limit)
    return {"count": len(results), "results": [r.to_dict() for r in results]}


@router.post("/context", summary="Build knowledge context for an AI agent")
def build_context(
    query: str,
    project: str | None = None,
    max_notes: int = Query(default=10, ge=1, le=20),
    include_evidence: bool = True,
    include_lessons: bool = True,
    include_decisions: bool = True,
    include_project: bool = True,
    detect_conflicts: bool = True,
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> dict[str, object]:
    """Build a categorized context bundle for an AI agent.

    Returns relevant knowledge, evidence, lessons, decisions, project context,
    and detected conflicts. The context is concise - not full Markdown files.
    """
    context = knowledge_retriever.build_context(
        query,
        project=project,
        max_notes=max_notes,
        include_evidence=include_evidence,
        include_lessons=include_lessons,
        include_decisions=include_decisions,
        include_project=include_project,
        detect_conflicts=detect_conflicts,
    )
    return {
        "context": context.to_dict(),
        "markdown": context.to_markdown(),
    }

# ============================================================================
# Knowledge Health & Evaluation Endpoints
# ============================================================================


@router.get("/health", summary="Run knowledge brain health check")
def health_check(
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Run a comprehensive health check on the knowledge vault."""
    evaluator = KnowledgeEvaluator(knowledge_service)
    result = evaluator.health_check()
    return result.to_dict()


@router.get("/evaluation", summary="Run full knowledge quality evaluation")
def run_evaluation(
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> dict[str, object]:
    """Run a complete knowledge quality evaluation."""
    evaluator = KnowledgeEvaluator(knowledge_service, retriever=knowledge_retriever)
    return evaluator.full_evaluation()


@router.get("/evaluation/retrieval", summary="Evaluate retrieval quality")
def evaluate_retrieval(
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> dict[str, object]:
    """Evaluate retrieval quality using Precision@K, Recall@K, Hit Rate@K."""
    evaluator = KnowledgeEvaluator(knowledge_service, retriever=knowledge_retriever)
    return evaluator.evaluate_retrieval().to_dict()


@router.get("/evaluation/growth", summary="Get knowledge growth report")
def growth_report(
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
) -> dict[str, object]:
    """Get a report on knowledge base growth and health."""
    evaluator = KnowledgeEvaluator(knowledge_service)
    return evaluator.knowledge_growth_report().to_dict()


@router.get("/evaluation/ablation", summary="Run memory ablation test")
def memory_ablation(
    query: str = Query(default="How can I improve YouTube retention?"),
    knowledge_service: KnowledgeService = Depends(get_obsidian_knowledge_service),
    knowledge_retriever: KnowledgeRetriever = Depends(get_knowledge_retriever),
) -> dict[str, object]:
    """Compare agent knowledge availability with and without context."""
    evaluator = KnowledgeEvaluator(knowledge_service, retriever=knowledge_retriever)
    return evaluator.memory_ablation(query).to_dict()
