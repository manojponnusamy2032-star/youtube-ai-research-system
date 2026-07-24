"""
youtube.py

Responsible for searching YouTube and collecting metadata.
"""

from datetime import datetime

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


def search_videos(keyword, max_results=10):
    """
    Search YouTube and return video metadata.

    Automatically skips videos that cannot be processed
    (premieres, private videos, deleted videos, etc.).
    """

    search_query = f"ytsearch{max_results}:{keyword}"

    ydl_opts = {
        "quiet": True,
        "skip_download": True,

        # IMPORTANT
        "extract_flat": "in_playlist",

        # Never stop because one video failed
        "ignoreerrors": True,

        # Ignore unavailable videos
        "skip_unavailable_fragments": True,

        "noplaylist": False,
    }

    videos = []

    try:

        with YoutubeDL(ydl_opts) as ydl:

            results = ydl.extract_info(search_query, download=False)

            if not results:
                return videos

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

    except DownloadError as e:
        print(f"⚠ yt-dlp error while searching '{keyword}': {e}")

    except Exception as e:
        print(f"⚠ Unexpected error while searching '{keyword}': {e}")

    return videos