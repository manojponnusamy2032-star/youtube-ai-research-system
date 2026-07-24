from datetime import datetime

from collector.database import (
    create_tables,
    insert_video,
    get_all_videos
)


def main():
    create_tables()

    sample_video = {
        "youtube_video_id": "abc123",
        "title": "Why Nice Guys Finish Last",
        "channel": "Better Ideas",
        "channel_id": "UC12345",
        "views": 2300000,
        "duration": 765,
        "upload_date": "2025-06-14",
        "thumbnail_url": "https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "search_keyword": "stickman psychology",
        "collected_at": datetime.now().isoformat()
    }

    insert_video(sample_video)

    print("\n📦 Videos in database:\n")

    videos = get_all_videos()

    for video in videos:
        print(f"• {video['title']} ({video['views']:,} views)")


if __name__ == "__main__":
    main()