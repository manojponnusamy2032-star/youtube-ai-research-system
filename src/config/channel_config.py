"""
Channel configuration.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelConfig:
    """Configuration for one YouTube channel."""

    name: str
    niche: str
    search_query: str
    videos_per_day: int
    max_results: int
    language: str = "en"