"""
Main Orchestrator.

Runs the complete YouTube research workflow.
"""

from src.core.manager_agent import ManagerAgent
from src.core.agent_registry import AgentRegistry


class Orchestrator:
    """Coordinates the complete research system."""

    def __init__(self):
        self.registry = AgentRegistry()
        self.manager = ManagerAgent(self.registry)

    def register(self, agent):
        """Register an agent."""
        self.registry.register(agent)

    def execute(self):
        """Execute all scheduled tasks."""
        return self.manager.run()