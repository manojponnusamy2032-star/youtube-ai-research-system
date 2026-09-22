"""Common typed stage-agent interface (Principle 3).

Every pipeline stage is implemented by an agent with a strongly typed
``run(request) -> response`` signature.  Future open-source implementations
only need to implement this interface; the orchestrator never reaches into a
specific implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

InT = TypeVar("InT")
OutT = TypeVar("OutT")


class StageAgent(ABC, Generic[InT, OutT]):
    """Base class for every orchestration pipeline stage.

    Subclasses declare a class-level ``stage`` name (one of the values in
    ``src.orchestration.pipeline.PIPELINE_STAGES``) and implement ``run``.
    """

    stage: str = ""

    @abstractmethod
    def run(self, request: InT) -> OutT:
        """Execute this stage and return the typed result.

        Raises:
            Exception: any exception is caught by the orchestrator, which
                records the failed stage on the VideoJob.
        """
        raise NotImplementedError

    def __call__(self, request: InT) -> OutT:
        """Allow ``agent(request)`` shorthand in addition to ``agent.run(request)``."""
        return self.run(request)

    def describe(self) -> dict[str, str]:
        """Human-readable agent identity used in job state/reports."""
        return {"stage": self.stage, "implementation": type(self).__name__}


class PipelineStageError(RuntimeError):
    """Raised by stages to signal a controlled, reportable failure."""

    def __init__(self, stage: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.details = details or {}