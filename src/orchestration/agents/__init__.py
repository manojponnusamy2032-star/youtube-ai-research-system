"""Mock pipeline agents for the Day-1 integration foundation.

These agents return deterministic, structurally valid stage outputs so the
full pipeline can be exercised end-to-end before real open-source
implementations are plugged into the adapter layer.
"""

from src.orchestration.agents.factory import build_default_stage_agents
from src.orchestration.agents.research.base import ResearchAgent
from src.orchestration.agents.research.mock import MockResearchAgent
from src.orchestration.agents.script.base import ScriptAgent
from src.orchestration.agents.script.mock import MockScriptAgent
from src.orchestration.agents.strategy.base import StrategyAgent
from src.orchestration.agents.strategy.mock import MockStrategyAgent
from src.orchestration.agents.visual.base import VisualPlannerAgent
from src.orchestration.agents.visual.mock import MockVisualPlannerAgent

__all__ = [
    "MockResearchAgent",
    "MockScriptAgent",
    "MockStrategyAgent",
    "MockVisualPlannerAgent",
    "ResearchAgent",
    "ScriptAgent",
    "StrategyAgent",
    "VisualPlannerAgent",
    "build_default_stage_agents",
]