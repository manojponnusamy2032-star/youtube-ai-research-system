"""
Search Result Model
"""

from dataclasses import dataclass

from .video import Video
from .channel import Channel


@dataclass
class SearchResult:

    video: Video
    channel: Channel