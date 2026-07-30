"""Agent registry."""

from typing import Dict

from src.core.base_agent import BaseAgent


class AgentRegistry:
    """Stores and retrieves all agents."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent."""
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        """Get an agent by name."""
        return self._agents[name]

    def all(self) -> Dict[str, BaseAgent]:
        """Return all registered agents."""
        return self._agents