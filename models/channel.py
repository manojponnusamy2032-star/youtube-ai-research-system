"""
Channel Model
"""

from dataclasses import dataclass


@dataclass
class Channel:

    channel_id: str
    name: str