"""
Idea Generation Service.

Generates new YouTube video ideas from extracted patterns.
"""

from __future__ import annotations

import json

from src.models.idea import Idea
from src.services.analysis_service import AnalysisService


class IdeaService:
    """Generates new ideas using the configured LLM."""

    def __init__(self, analysis_service: AnalysisService):
        self.analysis_service = analysis_service

    def generate(
        self,
        pattern_summary: str,
    ) -> list[Idea]:
        """
        Generate ideas from pattern summaries.

        Args:
            pattern_summary: Summary produced by the Pattern Agent.

        Returns:
            List of generated ideas.
        """

        prompt = f"""
You are one of the world's best YouTube strategists.

Based on these successful patterns:

{pattern_summary}

Generate 10 NEW YouTube video ideas.

Return ONLY valid JSON.

Format:

[
  {{
    "title": "...",
    "hook": "...",
    "emotion": "...",
    "topic": "...",
    "virality_score": 9.5,
    "confidence_score": 8.8
  }}
]
"""

        response = self.analysis_service.generate(prompt)

        ideas_json = json.loads(response)

        return [
            Idea.model_validate(item)
            for item in ideas_json
        ]