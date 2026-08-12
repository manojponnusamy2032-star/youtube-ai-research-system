"""Health and system metrics routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_database_service, get_workflow_store
from src.api.schemas.common import HealthResponse, MetricsResponse
from src.database.database_service import DatabaseService

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health_check() -> HealthResponse:
    """Return basic health status."""
    return HealthResponse()


@router.get("/metrics", response_model=MetricsResponse, summary="System metrics")
def metrics(database: DatabaseService = Depends(get_database_service)) -> MetricsResponse:
    """Return system counters and workflow runtime metrics."""
    workflow_metrics = get_workflow_store().metrics()
    return MetricsResponse(
        videos=database.get_video_count(),
        transcripts=database.get_transcript_count(),
        analyses=database.get_analysis_count(),
        scripts=database.get_script_count(),
        content_packages=database.get_content_package_count(),
        **workflow_metrics,
    )


@router.get("/videos", summary="List stored videos")
def list_videos(
    q: str | None = Query(default=None, description="Search videos by title or channel"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    database: DatabaseService = Depends(get_database_service),
) -> dict[str, object]:
    """Return a paginated list of stored videos."""
    query = "SELECT video_id, title, description, channel, channel_id, published_at, duration, view_count, like_count, comment_count, thumbnail_url, video_url FROM videos"
    params: list[object] = []
    if q:
        query += " WHERE title LIKE ? OR channel LIKE ?"
        like = f"%{q}%"
        params.extend([like, like])
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = database.connection.cursor()
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    return {"total": database.get_video_count(), "items": [dict(row) for row in rows]}


@router.get("/analysis", summary="List stored analysis results")
def list_analysis(
    q: str | None = Query(default=None, description="Search analysis by video title or channel"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    database: DatabaseService = Depends(get_database_service),
) -> dict[str, object]:
    """Return a paginated list of stored analysis results."""
    query = """
        SELECT
            a.video_id,
            a.hook_type,
            a.opening_summary,
            a.main_topic,
            a.sub_topics,
            a.target_audience,
            a.emotion,
            a.story_structure,
            a.title_formula,
            a.thumbnail_pattern,
            a.retention_techniques,
            a.cta_type,
            a.keywords,
            a.psychological_triggers,
            a.value_proposition,
            a.difficulty_level,
            a.estimated_video_style,
            a.summary,
            a.confidence_score,
            a.analysis_model,
            v.title AS video_title,
            v.channel AS video_channel,
            v.view_count,
            v.like_count,
            v.comment_count,
            v.duration
        FROM analysis a
        JOIN videos v ON a.video_id = v.video_id
    """
    params: list[object] = []
    if q:
        query += " WHERE v.title LIKE ? OR v.channel LIKE ? OR a.hook_type LIKE ?"
        like = f"%{q}%"
        params.extend([like, like, like])
    query += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor = database.connection.cursor()
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    return {"total": database.get_analysis_count(), "items": [dict(row) for row in rows]}
