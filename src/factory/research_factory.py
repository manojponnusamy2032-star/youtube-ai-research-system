"""
Research Factory.

Runs the complete research pipeline.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ResearchFactory:
    """
    Collector
        ↓
    Transcript
        ↓
    Analysis
        ↓
    Pattern
        ↓
    Idea
        ↓
    Script
    """

    def __init__(
        self,
        collector_agent,
        transcript_agent,
        analysis_agent,
        pattern_agent,
        idea_agent,
        script_agent,
    ):

        self.collector = collector_agent
        self.transcript = transcript_agent
        self.analysis = analysis_agent
        self.pattern = pattern_agent
        self.idea = idea_agent
        self.script = script_agent

    def run(
        self,
        keyword: str,
        max_results: int = 50,
    ) -> None:

        logger.info("========== RESEARCH FACTORY ==========")

        logger.info("Step 1 : Collector")
        self.collector.run(
            keyword=keyword,
            max_results=max_results,
        )

        logger.info("Step 2 : Transcript")
        self.transcript.run()

        logger.info("Step 3 : Analysis")
        self.analysis.run()

        logger.info("Step 4 : Pattern")
        self.pattern.run()

        logger.info("Step 5 : Idea")
        self.idea.run()

        logger.info("Step 6 : Script")
        self.script.run()

        logger.info("Research Factory Finished")