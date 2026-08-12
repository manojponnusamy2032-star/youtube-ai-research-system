"""
Script Generation Service.

Generates YouTube scripts from an Idea.
"""

from __future__ import annotations

import json

from src.models.idea import Idea
from src.models.script import Script
from src.services.analysis_service import AnalysisService


class ScriptService:
    """Generates complete YouTube scripts."""

    def __init__(
        self,
        analysis_service: AnalysisService,
    ):
        self.analysis_service = analysis_service

    def generate(
        self,
        idea: Idea,
    ) -> Script:
        """
        Generate a script from an idea.
        """

        prompt = f"""
You are one of the world's best YouTube scriptwriters.

Write a highly engaging script.

TITLE:
{idea.title}

HOOK:
{idea.hook}

EMOTION:
{idea.emotion}

TOPIC:
{idea.topic}

Return ONLY valid JSON.

{{
    "title":"",
    "hook":"",
    "introduction":"",
    "body":"",
    "conclusion":"",
    "call_to_action":"",
    "estimated_duration":180
}}
"""

        response = self.analysis_service.generate(prompt)

        data = json.loads(response)

        return Script(
            idea_id=idea.id or 0,
            title=data["title"],
            hook=data["hook"],
            introduction=data["introduction"],
            body=data["body"],
            conclusion=data["conclusion"],
            call_to_action=data["call_to_action"],
            estimated_duration=data["estimated_duration"],
        )