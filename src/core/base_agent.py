"""Base class for all agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext


class BaseAgent(ABC):
    """Base class that every agent inherits."""

    def __init__(self, name: str):
        self.name = name

    def log(self, message: str) -> None:
        print(f"[{self.name}] {message}")

    def start(self) -> None:
        self.log("Started")

    def finish(self) -> None:
        self.log("Finished")

    @abstractmethod
    def run(self, context: WorkflowContext) -> AgentResult:
        """
        Execute the agent.
        """
        raise NotImplementedError