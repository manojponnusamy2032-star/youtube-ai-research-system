"""Knowledge and pattern intelligence routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.auth import require_api_key
from src.api.dependencies import get_knowledge_service, get_pattern_service
from src.services.knowledge_service import KnowledgeService
from src.services.pattern_service import PatternService

router = APIRouter(tags=["Intelligence"], dependencies=[Depends(require_api_key)])


@router.get("/knowledge", summary="Get stored knowledge entries")
def get_knowledge(
    query: str | None = Query(default=None, description="Optional search text"),
    limit: int = Query(default=20, ge=1, le=100),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, object]:
    """Return knowledge entries from the knowledge base."""
    if query:
        entries = knowledge_service.search(query, limit=limit)
    else:
        entries = knowledge_service.get_best_patterns(limit=limit)
    payload = [entry.to_dict() for entry in entries]
    return {"count": len(payload), "knowledge": payload}


@router.get("/patterns", summary="Get extracted pattern report")
def get_patterns(pattern_service: PatternService = Depends(get_pattern_service)) -> dict[str, object]:
    """Generate and return latest aggregate pattern report."""
    report = pattern_service.generate_report()
    return {"report": report}
