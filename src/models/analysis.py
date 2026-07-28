"""
Analysis model for YouTube AI Research System.

This module defines the Pydantic model for video analysis results,
ensuring type safety and validation for structured insights extracted
from transcripts by the LLM.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DifficultyLevel(str, Enum):
    """Enumeration of video difficulty levels."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    ALL_LEVELS = "all_levels"


class Analysis(BaseModel):
    """
    Represents structured analysis results for a video transcript.
    
    Attributes:
        video_id: YouTube video ID
        hook_type: Type of hook used in the opening
        opening_summary: Brief summary of the video opening
        main_topic: Primary topic of the video
        sub_topics: List of subtopics covered
        target_audience: Intended audience for the video
        emotion: Emotional tone of the video
        story_structure: Narrative structure used
        title_formula: Pattern/formula used in the title
        thumbnail_pattern: Visual pattern used in thumbnail
        retention_techniques: List of techniques used to retain viewers
        cta_type: Type of call-to-action used
        keywords: List of key terms and phrases
        psychological_triggers: Psychological triggers identified
        value_proposition: Main value offered to viewers
        difficulty_level: Target difficulty level
        estimated_video_style: Estimated production style
        summary: Overall summary of the video content
        confidence_score: LLM confidence in the analysis (0.0-1.0)
        analysis_model: Name/version of the LLM used
        created_at: When the analysis was performed
    """
    
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    hook_type: str = Field(..., description="Type of hook used in opening")
    opening_summary: str = Field(..., description="Brief summary of video opening")
    main_topic: str = Field(..., description="Primary topic of the video")
    sub_topics: list[str] = Field(default_factory=list, description="List of subtopics covered")
    target_audience: str = Field(..., description="Intended audience for the video")
    emotion: str = Field(..., description="Emotional tone of the video")
    story_structure: str = Field(..., description="Narrative structure used")
    title_formula: str = Field(..., description="Pattern/formula used in the title")
    thumbnail_pattern: str = Field(..., description="Visual pattern used in thumbnail")
    retention_techniques: list[str] = Field(default_factory=list, description="Viewer retention techniques")
    cta_type: str = Field(..., description="Type of call-to-action used")
    keywords: list[str] = Field(default_factory=list, description="Key terms and phrases")
    psychological_triggers: list[str] = Field(default_factory=list, description="Psychological triggers identified")
    value_proposition: str = Field(..., description="Main value offered to viewers")
    difficulty_level: DifficultyLevel = Field(..., description="Target difficulty level")
    estimated_video_style: str = Field(..., description="Estimated production style")
    summary: str = Field(..., description="Overall summary of video content")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="LLM confidence in analysis (0.0-1.0)")
    analysis_model: str = Field(..., description="Name/version of LLM used")
    created_at: Optional[datetime] = Field(default=None, description="When the analysis was performed")
    
    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "example": {
                "video_id": "dQw4w9WgXcQ",
                "hook_type": "question",
                "opening_summary": "Video opens with a surprising statistic about video marketing",
                "main_topic": "YouTube growth strategies",
                "sub_topics": ["algorithm optimization", "thumbnail design", "content planning"],
                "target_audience": "Aspiring YouTubers",
                "emotion": "excited and motivational",
                "story_structure": "problem-solution",
                "title_formula": "Number + Adjective + Topic + Promise",
                "thumbnail_pattern": "face with exaggerated expression + text overlay",
                "retention_techniques": ["pattern interrupts", "storytelling", "visual variety"],
                "cta_type": "direct",
                "keywords": ["YouTube algorithm", "viral video", "subscriber growth"],
                "psychological_triggers": ["social proof", "scarcity", "authority"],
                "value_proposition": "Learn proven strategies to grow your YouTube channel",
                "difficulty_level": "beginner",
                "estimated_video_style": "tutorial with screen recording",
                "summary": "Comprehensive guide to YouTube growth covering algorithm tips, thumbnail best practices, and content strategy",
                "confidence_score": 0.92,
                "analysis_model": "llama3.2:latest"
            }
        }