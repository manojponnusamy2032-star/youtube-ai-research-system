"""
youtube.py

Responsible for searching YouTube and collecting metadata.
"""

from datetime import datetime

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from models import Video, Channel, SearchResult

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


                channel = Channel(
                     channel_id=entry.get("channel_id") or "",
                     name=entry.get("uploader") or "Unknown"
                )

                video = Video(
                    youtube_video_id=entry.get("id") or "",
                    title=entry.get("title") or "Untitled",
                    channel_id=channel.channel_id,
                    views=entry.get("view_count") or 0,
                    duration=entry.get("duration") or 0,
                    upload_date=entry.get("upload_date") or "",
                    thumbnail_url=entry.get("thumbnail") or "",
                    video_url=entry.get("webpage_url") or "",
                    search_keyword=keyword,
                    collected_at=datetime.now().isoformat()
                )

               
                videos.append(

                    SearchResult(

                        video=video,

                        channel=channel

                    )

                )

    except DownloadError as e:
        print(f"⚠ yt-dlp error while searching '{keyword}': {e}")

    except Exception as e:
        print(f"⚠ Unexpected error while searching '{keyword}': {e}")

    return videos