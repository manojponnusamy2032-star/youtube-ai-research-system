"""
Recommendation models for YouTube AI Research System.

This module defines Pydantic models for recommendations generated
by the Recommendation Intelligence Agent.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    """
    Represents a single actionable recommendation.

    Attributes:
        recommendation_id: Unique identifier
        category: Recommendation category (e.g., 'hook_strategy', 'title_strategy')
        title: Short title for the recommendation
        description: Detailed description
        reason: Why this recommendation is being made
        supporting_patterns: List of patterns that support this recommendation
        confidence: Confidence score (0.0-1.0)
        priority: Priority level (high, medium, low)
        expected_impact: Expected impact description
        implementation_steps: List of steps to implement
        example_patterns: Examples from the dataset
        created_at: When the recommendation was generated
    """

    recommendation_id: Optional[int] = Field(default=None, description="Unique identifier")
    category: str = Field(..., description="Recommendation category")
    title: str = Field(..., description="Short title")
    description: str = Field(..., description="Detailed description")
    reason: str = Field(..., description="Reason for recommendation")
    supporting_patterns: List[str] = Field(default_factory=list, description="Supporting patterns")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    priority: str = Field(..., description="Priority level (high/medium/low)")
    expected_impact: str = Field(..., description="Expected impact description")
    implementation_steps: List[str] = Field(default_factory=list, description="Implementation steps")
    example_patterns: List[str] = Field(default_factory=list, description="Example patterns from dataset")
    created_at: Optional[datetime] = Field(default=None, description="Generation timestamp")


class RecommendationReport(BaseModel):
    """
    Represents a complete recommendation report.

    Attributes:
        report_name: Name of the report
        created_at: When the report was generated
        total_recommendations: Total number of recommendations
        high_priority_count: Number of high priority recommendations
        medium_priority_count: Number of medium priority recommendations
        low_priority_count: Number of low priority recommendations
        recommendations: List of recommendations
        json_report: Full JSON report data
    """

    report_name: str = Field(..., description="Name of the report")
    created_at: Optional[datetime] = Field(default=None, description="Report generation time")
    total_recommendations: int = Field(default=0, description="Total recommendations")
    high_priority_count: int = Field(default=0, description="High priority count")
    medium_priority_count: int = Field(default=0, description="Medium priority count")
    low_priority_count: int = Field(default=0, description="Low priority count")
    recommendations: List[Recommendation] = Field(default_factory=list, description="Recommendations list")
    json_report: Dict[str, Any] = Field(default_factory=dict, description="Full JSON report data")


class RecommendationSummary(BaseModel):
    """
    Summary of recommendation results for display.

    Attributes:
        recommendations_generated: Total recommendations generated
        high_priority: High priority count
        medium_priority: Medium priority count
        low_priority: Low priority count
        top_recommendation: Title of top recommendation
        highest_confidence: Highest confidence score
        categories_covered: Number of categories with recommendations
    """

    recommendations_generated: int = Field(default=0, description="Total recommendations")
    high_priority: int = Field(default=0, description="High priority count")
    medium_priority: int = Field(default=0, description="Medium priority count")
    low_priority: int = Field(default=0, description="Low priority count")
    top_recommendation: Optional[str] = Field(default=None, description="Top recommendation title")
    highest_confidence: float = Field(default=0.0, description="Highest confidence score")
    categories_covered: int = Field(default=0, description="Categories covered")
</parameter>
<task_progress>
- [x] Create Recommendation Pydantic models
- [ ] Add recommendations table to DatabaseService
- [ ] Build RecommendationService with pattern-to-recommendation logic
- [ ] Build RecommendationAgent with Rich dashboard
- [ ] Create tests for Recommendation Agent
- [ ] Run tests and verify all pass
</parameter>
</write_to_file>