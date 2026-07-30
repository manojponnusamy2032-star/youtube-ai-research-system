"""
Temporary Manager Runner.
"""

import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.core.agent_registry import AgentRegistry
from src.core.manager_agent import ManagerAgent


def main() -> None:
    registry = AgentRegistry()

    manager = ManagerAgent(registry)
    manager.run()


if __name__ == "__main__":
    main()