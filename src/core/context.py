"""
Shared workflow context.

Stores data produced by one agent and consumed by another.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowContext:
    """Shared state between agents."""

    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.data

    def clear(self) -> None:
        self.data.clear()