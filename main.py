"""
main.py

Entry point for the YouTube AI Research System.
"""

from config import MAX_RESULTS

from collector.youtube_collector import search_videos

from database.database_manager import (
    create_tables,
    insert_video,
    video_exists,
)

from utils.keyword_loader import load_keywords


def main():

    print("=" * 60)
    print("YouTube AI Research Collector")
    print("=" * 60)

    # Create database tables
    create_tables()

    # Load keywords
    keywords = load_keywords()

    if not keywords:
        print("❌ No keywords found in keywords.txt")
        return

    total_found = 0
    total_saved = 0
    total_duplicates = 0

    # Process each keyword
    for keyword in keywords:

        print("\n" + "=" * 60)
        print(f"Searching: {keyword}")
        print("=" * 60)

        videos = search_videos(keyword, MAX_RESULTS)

        print(f"Found {len(videos)} videos")

        total_found += len(videos)

        saved = 0
        duplicates = 0

        for video in videos:

            if video_exists(video["youtube_video_id"]):
                duplicates += 1
                continue

            insert_video(video)

            saved += 1

            print(f"Saved: {video['title']}")

        total_saved += saved
        total_duplicates += duplicates

        print(f"\nFinished '{keyword}'")
        print(f"New Videos : {saved}")
        print(f"Duplicates : {duplicates}")

    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)

    print(f"Keywords Processed : {len(keywords)}")
    print(f"Videos Found       : {total_found}")
    print(f"New Videos Saved   : {total_saved}")
    print(f"Duplicates Skipped : {total_duplicates}")

    print("=" * 60)


if __name__ == "__main__":
    main()