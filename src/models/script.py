"""
Models for generated YouTube scripts.

This module defines Pydantic models for video scripts generated
by the Script Generator Agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


@dataclass
class Script:
    """Represents a generated YouTube script."""
    idea_id: int | None = None
    title: str = ""
    hook: str = ""
    introduction: str = ""
    body: str = ""
    conclusion: str = ""
    call_to_action: str = ""
    estimated_duration: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "idea_id": self.idea_id,
            "title": self.title,
            "hook": self.hook,
            "introduction": self.introduction,
            "body": self.body,
            "conclusion": self.conclusion,
            "call_to_action": self.call_to_action,
            "estimated_duration": self.estimated_duration,
        }