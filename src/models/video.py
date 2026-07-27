"""
Video model for YouTube AI Research System.

This module defines the Pydantic model for YouTube video metadata,
ensuring type safety and validation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Video(BaseModel):
    """
    Represents a YouTube video with validated metadata.
    
    Attributes:
        video_id: Unique YouTube video identifier
        title: Video title
        description: Video description
        channel: Channel name
        channel_id: Unique channel identifier
        published_at: Publication timestamp
        duration: Video duration in ISO 8601 format
        view_count: Number of views
        like_count: Number of likes
        comment_count: Number of comments
        thumbnail_url: URL to video thumbnail
        video_url: Direct URL to the video
        search_keyword: Keyword used to find this video
    """
    
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    title: str = Field(..., min_length=1, max_length=500, description="Video title")
    description: str = Field(default="", max_length=5000, description="Video description")
    channel: str = Field(..., min_length=1, max_length=200, description="Channel name")
    channel_id: str = Field(..., min_length=1, description="Channel ID")
    published_at: datetime = Field(..., description="Publication timestamp")
    duration: str = Field(..., description="Duration in ISO 8601 format")
    view_count: int = Field(..., ge=0, description="Number of views")
    like_count: int = Field(..., ge=0, description="Number of likes")
    comment_count: int = Field(..., ge=0, description="Number of comments")
    thumbnail_url: HttpUrl = Field(..., description="Thumbnail URL")
    video_url: HttpUrl = Field(..., description="Video URL")
    search_keyword: str = Field(..., min_length=1, description="Search keyword used")
    
    @field_validator('video_id')
    @classmethod
    def validate_video_id(cls, v: str) -> str:
        """Ensure video_id is not empty and properly formatted."""
        if not v or not v.strip():
            raise ValueError("video_id cannot be empty")
        return v.strip()
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Ensure title is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("title cannot be empty")
        return v.strip()
    
    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "video_id": "dQw4w9WgXcQ",
                "title": "Example Video",
                "description": "This is an example video",
                "channel": "Example Channel",
                "channel_id": "UC123456789",
                "published_at": "2024-01-01T00:00:00",
                "duration": "PT3M30S",
                "view_count": 1000000,
                "like_count": 50000,
                "comment_count": 5000,
                "thumbnail_url": "https://example.com/thumb.jpg",
                "video_url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
                "search_keyword": "python"
            }
        }