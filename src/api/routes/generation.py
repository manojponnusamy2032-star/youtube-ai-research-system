"""Generation routes for titles and content assets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import require_api_key
from src.api.dependencies import (
    get_content_generation_manager,
    get_content_generation_service,
    get_title_generation_service,
)
import json
from src.api.schemas.generation import (
    ContentPackageResponse,
    GenerationBaseRequest,
    HookResponse,
    ScriptResponse,
    SeoResponse,
    ThumbnailResponse,
    TitlesRequest,
    TitlesResponse,
)
from src.api.schemas.content import ContentListResponse, ContentItem, ContentListResponse, GeneratedListResponse
from src.api.schemas.content import GeneratedItem, WorkflowLogsResponse
from src.api.dependencies import get_database_service
from src.core.context import WorkflowContext
from src.services.content_generation_service import ContentGenerationService
from src.services.title_generation_service import TitleGenerationService

router = APIRouter(tags=["Generation"], dependencies=[Depends(require_api_key)])


@router.post("/titles", response_model=TitlesResponse, summary="Generate titles")
def generate_titles(
    payload: TitlesRequest,
    title_service: TitleGenerationService = Depends(get_title_generation_service),
) -> TitlesResponse:
    """Generate ranked title candidates."""
    titles = title_service.generate_titles(
        topic=payload.topic,
        niche=payload.niche,
        audience=payload.audience,
        trend_data=payload.trend_info,
        count=payload.count,
    )
    output = [item.to_dict() for item in titles]
    return TitlesResponse(count=len(output), titles=output)


@router.post("/content", response_model=ContentPackageResponse, summary="Generate complete content package")
def generate_content_package(
    payload: GenerationBaseRequest,
    content_service: ContentGenerationService = Depends(get_content_generation_service),
) -> ContentPackageResponse:
    """Generate complete content package with hook, thumbnail, script, and SEO."""
    package = content_service.generate_content_package(payload.model_dump())
    return ContentPackageResponse(content_package=package.to_dict())


@router.post("/script", response_model=ScriptResponse, summary="Generate script only")
def generate_script(
    payload: GenerationBaseRequest,
    content_service: ContentGenerationService = Depends(get_content_generation_service),
) -> ScriptResponse:
    """Generate script plan only."""
    data = content_service.extract_generation_inputs(payload.model_dump())
    best_title = content_service.select_best_title(data["generated_titles"], data["topic"])
    hook = content_service.generate_hook(**data)
    script = content_service.generate_script(best_title=best_title, hook=hook, **data)
    return ScriptResponse(script=script)


@router.post("/thumbnail", response_model=ThumbnailResponse, summary="Generate thumbnail concept")
def generate_thumbnail(
    payload: GenerationBaseRequest,
    content_service: ContentGenerationService = Depends(get_content_generation_service),
) -> ThumbnailResponse:
    """Generate thumbnail concept and prompt only."""
    data = content_service.extract_generation_inputs(payload.model_dump())
    best_title = content_service.select_best_title(data["generated_titles"], data["topic"])
    thumbnail = content_service.generate_thumbnail(best_title=best_title, **data)
    return ThumbnailResponse(thumbnail=thumbnail)


@router.post("/seo", response_model=SeoResponse, summary="Generate SEO package")
def generate_seo(
    payload: GenerationBaseRequest,
    content_service: ContentGenerationService = Depends(get_content_generation_service),
) -> SeoResponse:
    """Generate SEO metadata only."""
    data = content_service.extract_generation_inputs(payload.model_dump())
    best_title = content_service.select_best_title(data["generated_titles"], data["topic"])
    script = content_service.generate_script(
        best_title=best_title,
        hook=content_service.generate_hook(**data),
        **data,
    )
    seo = content_service.generate_seo(best_title=best_title, script=script, **data)
    return SeoResponse(seo=seo)


# --------------------------------------------------
# Content retrieval endpoints
# --------------------------------------------------

@router.get("/content", response_model=ContentListResponse, summary="List generated content packages")
def list_content_packages(
    topic: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("desc", regex="^(asc|desc)$", description="Sort by created_at asc/desc"),
    db: object = Depends(get_database_service),
) -> ContentListResponse:
    """List content packages with optional topic filter, pagination and sorting."""
    packages = db.get_content_packages(topic=topic, limit=limit, offset=offset, sort=sort)
    total = db.get_content_package_count()
    items = [ContentItem(**p) for p in packages]
    return ContentListResponse(total=total, items=items)


@router.get("/content/{package_id}", response_model=ContentItem, summary="Get content package by id")
def get_content_package(package_id: int, db: object = Depends(get_database_service)) -> ContentItem:
    pkg = db.get_content_package_by_id(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Content package not found")
    return ContentItem(**pkg)


# --------------------------------------------------
# Generated assets listing endpoints
# --------------------------------------------------

@router.get("/generated/scripts", response_model=GeneratedListResponse, summary="List generated scripts")
def list_generated_scripts(
    topic: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: object = Depends(get_database_service),
) -> GeneratedListResponse:
    rows = db.get_generated_scripts(topic=topic, start_date=start_date, end_date=end_date, limit=limit, offset=offset)
    items = [GeneratedItem(id=r.get("id"), topic=r.get("topic"), created_at=r.get("created_at"), payload=json.loads(r.get("script_json") or "{}")) for r in rows]
    total = len(items)
    return GeneratedListResponse(total=total, items=items)


@router.get("/generated/titles", response_model=GeneratedListResponse, summary="List generated titles")
def list_generated_titles(
    topic: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: object = Depends(get_database_service),
) -> GeneratedListResponse:
    rows = db.get_generated_titles(topic=topic, start_date=start_date, end_date=end_date, limit=limit, offset=offset)
    items = [GeneratedItem(id=r.get("id"), topic=r.get("topic"), created_at=r.get("created_at"), payload={"title": r.get("title"), "confidence": r.get("confidence")}) for r in rows]
    total = len(items)
    return GeneratedListResponse(total=total, items=items)


@router.get("/generated/hooks", response_model=GeneratedListResponse, summary="List generated hooks")
def list_generated_hooks(
    topic: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: object = Depends(get_database_service),
) -> GeneratedListResponse:
    rows = db.get_generated_hooks(topic=topic, start_date=start_date, end_date=end_date, limit=limit, offset=offset)
    items = [GeneratedItem(id=r.get("id"), topic=r.get("topic"), created_at=r.get("created_at"), payload={"hook_type": r.get("hook_type"), "script": r.get("script")}) for r in rows]
    total = len(items)
    return GeneratedListResponse(total=total, items=items)


@router.get("/generated/thumbnails", response_model=GeneratedListResponse, summary="List generated thumbnails")
def list_generated_thumbnails(
    topic: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: object = Depends(get_database_service),
) -> GeneratedListResponse:
    rows = db.get_generated_thumbnails(topic=topic, start_date=start_date, end_date=end_date, limit=limit, offset=offset)
    items = [GeneratedItem(id=r.get("id"), topic=r.get("topic"), created_at=r.get("created_at"), payload=json.loads(r.get("thumbnail_json") or "{}")) for r in rows]
    total = len(items)
    return GeneratedListResponse(total=total, items=items)


@router.get("/generated/seo", response_model=GeneratedListResponse, summary="List generated seo entries")
def list_generated_seo(
    topic: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: object = Depends(get_database_service),
) -> GeneratedListResponse:
    rows = db.get_generated_seo(topic=topic, start_date=start_date, end_date=end_date, limit=limit, offset=offset)
    items = [GeneratedItem(id=r.get("id"), topic=r.get("topic"), created_at=r.get("created_at"), payload=json.loads(r.get("seo_json") or "{}")) for r in rows]
    total = len(items)
    return GeneratedListResponse(total=total, items=items)
