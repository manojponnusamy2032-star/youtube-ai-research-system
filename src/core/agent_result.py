"""
Standard result returned by every agent.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Represents the result of an agent execution."""

    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, **data) -> "AgentResult":
        return cls(
            success=True,
            data=data,
        )

    @classmethod
    def fail(cls, message: str) -> "AgentResult":
        return cls(
            success=False,
            message=message,
        )