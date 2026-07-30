"""
Task definition for the Manager pipeline.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    """Represents one agent execution."""

    agent: Any
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)

    def execute(self) -> Any:
        """Execute the task."""
        return self.agent.run(*self.args, **self.kwargs)