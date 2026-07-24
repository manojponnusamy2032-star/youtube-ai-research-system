"""
collector_service.py

Coordinates the complete YouTube data collection workflow.
"""

from collector.youtube_collector import search_videos

from database.database_manager import (
    insert_video,
    video_exists,
)

from config import MAX_RESULTS


class CollectorService:

    def collect_keyword(self, keyword):
        """
        Search YouTube and save videos for one keyword.

        Returns:
            found, saved, duplicates
        """

        videos = search_videos(keyword, MAX_RESULTS)

        found = len(videos)
        saved = 0
        duplicates = 0

        print(f"Found {found} videos")

        for video in videos:

            # If you are already using SearchResult objects,
            # uncomment these two lines and comment the next one.
            #
            # result = video
            # video = result.video

            if video_exists(video["youtube_video_id"]):
                duplicates += 1
                continue

            insert_video(video)

            saved += 1

            print(f"Saved: {video['title']}")

        return found, saved, duplicates