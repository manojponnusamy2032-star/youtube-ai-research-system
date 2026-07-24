"""
youtube.py

Responsible for searching YouTube and collecting metadata.
"""

from datetime import datetime
from yt_dlp import YoutubeDL


def search_videos(keyword, max_results=10):
    """
    Search YouTube and return video metadata.
    """

    search_query = f"ytsearch{max_results}:{keyword}"

    ydl_opts = {
        "quiet": True,
        "extract_flat": False,
        "skip_download": True,
    }

    videos = []

    with YoutubeDL(ydl_opts) as ydl:

        results = ydl.extract_info(search_query, download=False)

        if "entries" not in results:
            return videos

        for entry in results["entries"]:

            if entry is None:
                continue

            videos.append({

                "youtube_video_id": entry.get("id"),

                "title": entry.get("title"),

                "channel": entry.get("uploader"),

                "channel_id": entry.get("channel_id"),

                "views": entry.get("view_count"),

                "duration": entry.get("duration"),

                "upload_date": entry.get("upload_date"),

                "thumbnail_url": entry.get("thumbnail"),

                "video_url": entry.get("webpage_url"),

                "search_keyword": keyword,

                "collected_at": datetime.now().isoformat()

            })

    return videos