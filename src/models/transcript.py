"""
Transcript model for YouTube AI Research System.

This module defines the Pydantic model for video transcripts,
ensuring type safety and validation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class TranscriptMethod(str, Enum):
    """Enumeration of transcript retrieval methods."""
    YOUTUBE_API = "youtube_api"
    YTDLP_CAPTIONS = "ytdlp_captions"
    WHISPER = "whisper"


class TranscriptStatus(str, Enum):
    """Enumeration of transcript processing statuses."""
    COMPLETED = "completed"
    FAILED = "failed"


class Transcript(BaseModel):
    """
    Represents a video transcript with retrieval metadata.
    
    Attributes:
        video_id: YouTube video ID
        language: Language code of the transcript (e.g., 'en')
        transcript: Full transcript text
        method: Method used to retrieve the transcript
        status: Processing status
        created_at: When the transcript was stored
    """
    
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    language: str = Field(default="en", min_length=2, max_length=10, description="Language code")
    transcript: str = Field(..., description="Full transcript text")
    method: TranscriptMethod = Field(..., description="Retrieval method used")
    status: TranscriptStatus = Field(default=TranscriptStatus.COMPLETED, description="Processing status")
    created_at: Optional[datetime] = Field(default=None, description="When the transcript was stored")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_id": "dQw4w9WgXcQ",
                "language": "en",
                "transcript": "Never gonna give you up...",
                "method": "youtube_api",
                "status": "completed"
            }
        }
    )