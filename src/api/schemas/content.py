from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ContentItem(BaseModel):
    id: int
    topic: str
    best_title: Optional[dict[str, Any]] = None
    created_at: str
    package_json: dict[str, Any]


class ContentListResponse(BaseModel):
    total: int
    items: List[ContentItem]


class GeneratedItem(BaseModel):
    id: int
    topic: str
    created_at: str
    payload: dict[str, Any]


class GeneratedListResponse(BaseModel):
    total: int
    items: List[GeneratedItem]


class WorkflowLogEntry(BaseModel):
    created_at: str
    stage: Optional[str] = None
    status: Optional[str] = None
    message: str
    error_text: Optional[str] = None


class WorkflowLogsResponse(BaseModel):
    workflow_id: str
    retry_count: Optional[int] = 0
    logs: List[WorkflowLogEntry]
