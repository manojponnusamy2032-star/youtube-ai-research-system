"""Publishing domain models for the YouTube publishing pipeline.

Defines the typed contracts for publishing:
    PublishRequest  – input for the YouTube publisher
    PublishedVideo  – output from a successful (or failed) publish attempt
    PublishVisibility – YouTube privacy setting
    PublishStatus   – publish attempt status
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PublishVisibility(str, Enum):
    """YouTube video privacy visibility."""

    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class PublishStatus(str, Enum):
    """Status of a publish attempt."""

    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Not attempted (e.g., QC failed)


class PublishRequest(BaseModel):
    """Input for the YouTube publisher.

    Maps a completed VideoJob + QC report into a YouTube upload request.
    """

    job_id: str = Field(..., min_length=1)
    video_path: str = Field(..., min_length=1, description="Path to the MP4 video artifact")
    title: str = Field(..., min_length=1, max_length=100, description="YouTube video title")
    description: str = Field(default="", max_length=5000, description="YouTube video description")
    tags: list[str] = Field(default_factory=list, description="YouTube video tags")
    category_id: str = Field(default="22", description="YouTube category ID (default: People & Blogs)")
    visibility: PublishVisibility = Field(default=PublishVisibility.PRIVATE, description="Video privacy status")
    scheduled_publish_time: datetime | None = Field(default=None, description="Optional scheduled publish time")
    thumbnail_path: str | None = Field(default=None, description="Optional custom thumbnail path")
    made_for_kids: bool = Field(default=False, description="Self-declared made for kids")

    # Idempotency / lineage
    artifact_path: str | None = Field(default=None, description="Original artifact path for reference")
    qc_report_path: str | None = Field(default=None, description="Path to the QC report that authorized publish")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be blank")
        return v.strip()

    @field_validator("video_path")
    @classmethod
    def _video_path_must_exist(cls, v: str) -> str:
        if not os.path.exists(v):
            raise ValueError(f"video_path does not exist: {v}")
        return v


class PublishedVideo(BaseModel):
    """Result of a YouTube publish attempt."""

    job_id: str = Field(..., min_length=1)
    video_id: str | None = Field(default=None, description="YouTube video ID if upload succeeded")
    video_url: str | None = Field(default=None, description="YouTube watch URL if upload succeeded")
    title: str = Field(..., min_length=1)
    visibility: PublishVisibility
    status: PublishStatus = PublishStatus.PENDING
    published_at: datetime | None = Field(default=None, description="When the video was published (approx)")
    upload_attempt: int = Field(default=1, ge=1, description="Attempt number for this publish")
    artifact_path: str | None = Field(default=None)
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    category_id: str = Field(default="22")
    thumbnail_result: dict[str, Any] | None = Field(default=None, description="Thumbnail upload result if attempted")
    error: str | None = Field(default=None, description="Error message if publish failed")

    # Raw service response for debugging
    service_response: dict[str, Any] | None = Field(default=None, description="Raw response from YouTubeUploadService")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class PublishGateResult(BaseModel):
    """Result of evaluating the publish gate."""

    job_id: str = Field(..., min_length=1)
    allowed: bool = Field(default=False, description="Whether publishing is allowed")
    publish_ready: bool = Field(default=False, description="QC publish_ready value")
    qc_status: str = Field(default="", description="Overall QC status")
    reason: str = Field(default="", description="Reason for allowing or blocking")
    existing_publish: PublishedVideo | None = Field(default=None, description="Existing publish if idempotent")
