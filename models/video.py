"""
Video Model
"""

from dataclasses import dataclass


@dataclass
class Video:

    youtube_video_id: str
    title: str

    channel_id: str

    views: int

    duration: int

    upload_date: str

    thumbnail_url: str

    video_url: str

    search_keyword: str

    collected_at: str