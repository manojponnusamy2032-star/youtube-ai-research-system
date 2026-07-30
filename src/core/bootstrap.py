"""Application bootstrap."""

from src.core.agent_registry import AgentRegistry
from src.core.manager_agent import ManagerAgent

from src.agents.collector_agent import CollectorAgent
from src.agents.transcript_agent import TranscriptAgent
from src.agents.analysis_agent import AnalysisAgent
from src.agents.pattern_agent import PatternAgent


def create_manager(
    collector: CollectorAgent,
    transcript: TranscriptAgent,
    analysis: AnalysisAgent,
    pattern: PatternAgent,
) -> ManagerAgent:
    """Create manager and register all agents."""

    registry = AgentRegistry()

    registry.register(collector)
    registry.register(transcript)
    registry.register(analysis)
    registry.register(pattern)

    return ManagerAgent(registry)