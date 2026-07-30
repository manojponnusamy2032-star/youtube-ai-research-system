"""Manager Agent - Controls all other agents."""

from __future__ import annotations

from typing import Any

from src.core.base_agent import BaseAgent
from src.core.agent_registry import AgentRegistry
from src.core.pipeline import Pipeline
from src.core.tasks import Task


class ManagerAgent(BaseAgent):
    """Coordinates and executes agent tasks."""

    def __init__(self, registry: AgentRegistry):
        super().__init__("ManagerAgent")
        self.registry = registry
        self.pipeline = Pipeline()

    def add_task(self, agent: Any, *args, **kwargs) -> None:
        """Schedule an agent for execution."""

        task = Task(
            agent=agent,
            args=args,
            kwargs=kwargs,
        )

        self.pipeline.add(task)

    def run(self) -> list[Any]:
        """Execute all scheduled tasks."""

        self.start()

        self.log(f"Registered Agents: {len(self.registry.all())}")

        if len(self.registry.all()) == 0:
            self.log("No agents registered.")
            self.finish()
            return []

        self.log("Executing workflow...")

        results = self.pipeline.run()

        self.log("Workflow completed.")

        self.pipeline.clear()

        self.finish()

        return results