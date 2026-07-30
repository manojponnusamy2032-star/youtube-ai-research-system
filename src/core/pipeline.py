"""
Pipeline execution engine.
"""

from __future__ import annotations

from src.core.tasks import Task


class Pipeline:
    """Executes tasks in sequence."""

    def __init__(self) -> None:
        self._tasks: list[Task] = []

    def add(self, task: Task) -> None:
        """Add a task to the pipeline."""
        self._tasks.append(task)

    def run(self) -> list:
        """Execute all tasks."""

        results = []

        for task in self._tasks:
            results.append(task.execute())

        return results

    def clear(self) -> None:
        """Clear all tasks."""
        self._tasks.clear()